import argparse
import asyncio
from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional
from sqlmodel.ext.asyncio.session import AsyncSession

from app.agents.reminder_agent import generate_case_reminder
from app.core.config import get_settings
from app.db.session import async_session_maker, init_db
from app.models.agent import InterventionStatus
from app.services.digivaluer_client import get_digivaluer_client
from app.services.notifier import get_notification_dispatcher
from app.services.sla_evaluator import ActionableOverdueCase, evaluate_active_cases

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("worker.sentinel")
settings = get_settings()

STAGE_DEFAULT_MISSING_ITEMS = {
    "document_verification": "Property title deed, legal description, and borrower income verification uploads",
    "site_inspection": "Exterior front & street scene photos, roof condition notes, and property access confirmation",
    "comparable_analysis": "Market comparables adjustment grid and local zoning verification",
    "final_assessment": "Senior review sign-off, final valuation reconciliation, and QA sign-off",
}


async def run_sentinel_scan(
    session: Optional[AsyncSession] = None,
    force_dispatch: Optional[bool] = None,
    cooling_off_hours: float = 12.0,
) -> Dict[str, Any]:
    """Execute the core DigiValuer Sentinel workflow cycle:

    1. Fetch active cases from DigiValuer core
    2. Evaluate stage SLAs and cooling-off windows
    3. Generate context-aware reminder drafts via Gemini Reminder Agent
    4. Respect HUMAN_IN_THE_LOOP flag:
       - If True: Persist as DRAFTED for dashboard approval
       - If False: Dispatch immediately across configured channels (Email, SMS, Webhook)
    """
    scan_start = datetime.now(timezone.utc)
    logger.info("=" * 70)
    logger.info("Starting DigiValuer Sentinel Scan at %s", scan_start.isoformat())

    # Resolve Human-in-the-Loop flag
    hitl_enabled = (not force_dispatch) if force_dispatch is not None else settings.HUMAN_IN_THE_LOOP
    logger.info("Human-in-the-Loop policy: %s", "ENABLED (Drafts held for review)" if hitl_enabled else "DISABLED (Immediate auto-dispatch)")

    client = get_digivaluer_client()
    dispatcher = get_notification_dispatcher()

    async def _execute_scan(db_sess: AsyncSession) -> Dict[str, Any]:
        # 1. Fetch active cases
        cases = await client.get_active_cases()
        logger.info("Fetched %d active cases from DigiValuer core.", len(cases))

        # 2. Evaluate SLAs and identify actionable overdue cases
        actionable_cases: List[ActionableOverdueCase] = await evaluate_active_cases(
            cases=cases,
            session=db_sess,
            cooling_off_hours=cooling_off_hours,
            reference_time=scan_start,
        )
        logger.info("Identified %d actionable overdue cases requiring attention.", len(actionable_cases))

        drafts_created: List[Dict[str, Any]] = []
        dispatched_list: List[Dict[str, Any]] = []
        held_list: List[Dict[str, Any]] = []
        failed_list: List[Dict[str, Any]] = []

        # 3. Process each overdue case through the Reminder Agent
        for item in actionable_cases:
            case = item.case
            missing_desc = STAGE_DEFAULT_MISSING_ITEMS.get(
                item.stage_id,
                "Required valuation documentation and stage completion tasks",
            )

            logger.info(
                "Processing Case %s (%s) | Elapsed: %.1fh / Target: %.1fh | Reminder #%d | Escalated: %s",
                case.case_id,
                item.stage_name,
                item.elapsed_hours,
                item.target_duration_hours,
                item.next_reminder_count,
                item.should_escalate,
            )

            # Generate reminder draft and save to database with status 'DRAFTED'
            draft, intervention = await generate_case_reminder(
                case_data=case,
                sla_data=item,
                missing_items=missing_desc,
                is_external=False,
                target_recipient=(
                    item.target_recipient_id,
                    item.target_recipient_name,
                    item.target_recipient_role,
                ),
                session=db_sess,
            )

            case_detail = {
                "case_id": case.case_id,
                "property_address": case.property_address,
                "stage": item.stage_name,
                "elapsed_hours": item.elapsed_hours,
                "reminder_count": item.next_reminder_count,
                "tone": draft.tone_level.value,
                "channel": draft.suggested_channel.value,
                "recipient": f"{item.target_recipient_name} <{item.target_recipient_id}> ({item.target_recipient_role})",
                "subject": draft.subject,
                "intervention_id": intervention.id if intervention else None,
            }
            drafts_created.append(case_detail)

            # 4. Respect HUMAN_IN_THE_LOOP flag
            if hitl_enabled:
                logger.info(
                    "[HITL] Case %s intervention #%s held in 'DRAFTED' status for operator approval.",
                    case.case_id,
                    intervention.id if intervention else "N/A",
                )
                held_list.append(case_detail)
            else:
                logger.info(
                    "[AUTO-DISPATCH] Dispatching intervention #%s via channel '%s' to '%s'...",
                    intervention.id if intervention else "N/A",
                    draft.suggested_channel.value,
                    item.target_recipient_id,
                )
                try:
                    dispatch_res = await dispatcher.dispatch(
                        channel=draft.suggested_channel,
                        recipient_id=item.target_recipient_id,
                        subject=draft.subject,
                        message=draft.body,
                        case_id=case.case_id,
                        metadata={
                            "stage": item.stage_id,
                            "reminder_count": item.next_reminder_count,
                            "intervention_id": intervention.id if intervention else None,
                        },
                    )

                    if dispatch_res.get("success") and intervention:
                        intervention.status = InterventionStatus.SENT.value
                        intervention.sent_at = datetime.now(timezone.utc)
                        db_sess.add(intervention)
                        await db_sess.commit()
                        await db_sess.refresh(intervention)
                        logger.info(
                            "[DISPATCH SUCCESS] Case %s intervention updated to SENT.",
                            case.case_id,
                        )
                        dispatched_list.append(case_detail)
                    else:
                        if intervention:
                            intervention.status = InterventionStatus.FAILED.value
                            db_sess.add(intervention)
                            await db_sess.commit()
                        failed_list.append(case_detail)
                except Exception as dispatch_err:
                    logger.error("[DISPATCH ERROR] Failed to dispatch for case %s: %s", case.case_id, dispatch_err)
                    if intervention:
                        intervention.status = InterventionStatus.FAILED.value
                        db_sess.add(intervention)
                        await db_sess.commit()
                    failed_list.append(case_detail)

        summary = {
            "status": "success",
            "scan_started_at": scan_start.isoformat(),
            "scan_finished_at": datetime.now(timezone.utc).isoformat(),
            "human_in_the_loop": hitl_enabled,
            "total_cases_scanned": len(cases),
            "actionable_overdue_cases": len(actionable_cases),
            "drafts_created": len(drafts_created),
            "held_for_review_count": len(held_list),
            "dispatched_count": len(dispatched_list),
            "failed_count": len(failed_list),
            "items": drafts_created,
        }
        logger.info(
            "Sentinel Scan Completed: %d cases scanned, %d overdue, %d drafted, %d dispatched, %d held.",
            summary["total_cases_scanned"],
            summary["actionable_overdue_cases"],
            summary["drafts_created"],
            summary["dispatched_count"],
            summary["held_for_review_count"],
        )
        logger.info("=" * 70)
        return summary

    if session is not None:
        return await _execute_scan(session)
    else:
        async with async_session_maker() as new_session:
            return await _execute_scan(new_session)


async def start_periodic_sentinel_worker(interval_seconds: Optional[int] = None) -> None:
    """Run sentinel scan on a recurring background loop (default: every 30 minutes)."""
    interval = interval_seconds or (settings.SCAN_INTERVAL_MINUTES * 60)
    logger.info("Starting Sentinel Worker Loop (Running every %d seconds / %d minutes)...", interval, interval // 60)

    await init_db()

    while True:
        try:
            await run_sentinel_scan()
        except Exception as exc:
            logger.error("Error during scheduled Sentinel scan: %s", exc, exc_info=True)

        logger.info("Sleeping for %d seconds until next scheduled scan...", interval)
        await asyncio.sleep(interval)


def main():
    """CLI entrypoint for running Sentinel scans manually or as a background service."""
    parser = argparse.ArgumentParser(description="DigiValuer Sentinel Worker")
    parser.add_argument(
        "--dispatch",
        action="store_true",
        help="Bypass HUMAN_IN_THE_LOOP and dispatch messages immediately",
    )
    parser.add_argument(
        "--loop",
        action="store_true",
        help="Run continuously on recurring schedule (every 30 mins)",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=None,
        help="Interval in seconds for continuous loop (default: 1800s / 30m)",
    )
    args = parser.parse_args()

    if args.loop:
        asyncio.run(start_periodic_sentinel_worker(interval_seconds=args.interval))
    else:
        force_dispatch = True if args.dispatch else None
        result = asyncio.run(run_sentinel_scan(force_dispatch=force_dispatch))
        print(f"\nScan Result: {result['status']}")
        print(f"Total Scanned: {result['total_cases_scanned']}")
        print(f"Overdue: {result['actionable_overdue_cases']}")
        print(f"Drafted: {result['drafts_created']}")
        print(f"Dispatched: {result['dispatched_count']}")
        print(f"Held for Review: {result['held_for_review_count']}")


if __name__ == "__main__":
    main()

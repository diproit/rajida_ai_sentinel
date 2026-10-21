from datetime import datetime, timezone
import logging
from typing import Any, Dict, Optional
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import get_settings
from app.core.redis import broadcast_sentinel_event
from app.models.agent import (
    AgentIntervention,
    CommunicationChannel,
    InterventionStatus,
    RecipientRole,
)
from app.models.valuation import AgentActionLog, ValuationCase, WorkflowBottleneck
from app.schemas.webhook import DigiValuerWebhookPayload, WebhookEventType, WebhookSeverity
from app.services.notifier import get_notification_dispatcher

logger = logging.getLogger("services.webhook_processor")
settings = get_settings()


async def process_webhook_payload(
    payload: DigiValuerWebhookPayload,
    session: AsyncSession,
) -> Dict[str, Any]:
    """Process incoming validated DigiValuer webhook payload based on event_type."""
    event_type = payload.event_type.upper()
    app_no = payload.application.application_no
    logger.info("Processing webhook event %s for case %s (Type: %s)", payload.event_id, app_no, event_type)

    if event_type == WebhookEventType.STATUS_CHANGED.value:
        return await _handle_status_changed(payload, session)
    elif event_type in (WebhookEventType.UNRESPONSIVE_PARTY.value, WebhookEventType.SLA_DELAY_WARNING.value):
        return await _handle_unresponsive_or_sla_warning(payload, session)
    else:
        logger.info("Default handling for unspecialized event_type: %s", event_type)
        return await _handle_generic_event(payload, session)


async def _get_or_create_valuation_case(
    payload: DigiValuerWebhookPayload,
    session: AsyncSession,
) -> ValuationCase:
    """Find existing ValuationCase by case_number or create a new one."""
    app_no = payload.application.application_no
    stmt = select(ValuationCase).where(ValuationCase.case_number == app_no)
    res = await session.exec(stmt)
    case = res.first()

    now = datetime.now(timezone.utc)
    if not case:
        branch_name = payload.application.branch_name or "Main Branch"
        case = ValuationCase(
            case_number=app_no,
            property_address=f"{branch_name} - App #{app_no}",
            property_type="Residential",
            status=payload.details.new_status or payload.application.status,
            assigned_appraiser=payload.assigned_party.name,
            is_stalled=False,
            created_at=payload.application.created_at or now,
            updated_at=payload.application.updated_at or now,
        )
        session.add(case)
        await session.flush()
        logger.info("Created new ValuationCase record for %s (id=%s)", app_no, case.id)
    return case


async def _handle_status_changed(
    payload: DigiValuerWebhookPayload,
    session: AsyncSession,
) -> Dict[str, Any]:
    """Handle STATUS_CHANGED event:

    1. Synchronize ValuationCase record status
    2. Auto-resolve bottlenecks from previous stage
    3. Dismiss obsolete reminder drafts for prior stage
    4. Log action and broadcast update
    """
    app_no = payload.application.application_no
    new_status = payload.details.new_status or payload.application.status
    prev_status = payload.details.previous_status

    case = await _get_or_create_valuation_case(payload, session)
    case.status = new_status
    case.assigned_appraiser = payload.assigned_party.name
    case.is_stalled = False
    case.updated_at = payload.application.updated_at or datetime.now(timezone.utc)
    session.add(case)

    # 1. Resolve prior bottlenecks
    resolved_count = 0
    if case.id is not None:
        bn_stmt = select(WorkflowBottleneck).where(
            WorkflowBottleneck.case_id == case.id,
            WorkflowBottleneck.resolved == False,
        )
        bn_res = await session.exec(bn_stmt)
        bottlenecks = bn_res.all()
        for bn in bottlenecks:
            bn.resolved = True
            resolved_count += 1
            session.add(bn)

    # 2. Dismiss obsolete drafted interventions for previous stage
    dismissed_count = 0
    inv_stmt = select(AgentIntervention).where(
        AgentIntervention.case_id == app_no,
        AgentIntervention.status == InterventionStatus.DRAFTED.value,
    )
    inv_res = await session.exec(inv_stmt)
    interventions = inv_res.all()
    for inv in interventions:
        inv.status = InterventionStatus.DISMISSED.value
        inv.updated_at = datetime.now(timezone.utc)
        session.add(inv)
        dismissed_count += 1

    # 3. Log audit event
    action_log = AgentActionLog(
        case_id=case.id,
        agent_name="DigiValuerWebhook",
        action_type="STATUS_CHANGED",
        details=f"Transitioned from '{prev_status}' to '{new_status}' by {payload.details.trigger_actor or 'system'}",
        timestamp=datetime.now(timezone.utc),
    )
    session.add(action_log)

    await session.commit()

    # 4. Broadcast live update to Redis Pub/Sub
    broadcast_data = {
        "event_id": payload.event_id,
        "case_number": app_no,
        "previous_status": prev_status,
        "new_status": new_status,
        "resolved_bottlenecks": resolved_count,
        "dismissed_drafts": dismissed_count,
    }
    await broadcast_sentinel_event("STATUS_CHANGED", broadcast_data)

    return {
        "status": "success",
        "action": "status_synchronized",
        "case_number": app_no,
        "new_status": new_status,
        "resolved_bottlenecks": resolved_count,
        "dismissed_drafts": dismissed_count,
    }


async def _handle_unresponsive_or_sla_warning(
    payload: DigiValuerWebhookPayload,
    session: AsyncSession,
) -> Dict[str, Any]:
    """Handle UNRESPONSIVE_PARTY or SLA_DELAY_WARNING:

    1. Mark ValuationCase as stalled
    2. Record WorkflowBottleneck
    3. Generate and stage an AgentIntervention (DRAFTED or auto-dispatched)
    4. Log action and broadcast update
    """
    app_no = payload.application.application_no
    case = await _get_or_create_valuation_case(payload, session)
    case.is_stalled = True
    case.assigned_appraiser = payload.assigned_party.name
    case.updated_at = datetime.now(timezone.utc)
    session.add(case)

    # 1. Record Bottleneck
    message_text = payload.details.message or f"SLA breach/delay of {payload.metrics.delay_seconds:.0f}s in stage {payload.application.status}"
    bottleneck = WorkflowBottleneck(
        case_id=case.id or 0,
        bottleneck_type=payload.category,
        severity=payload.severity.lower(),
        description=message_text,
        ai_recommendation=f"Nudge {payload.assigned_party.name} ({payload.assigned_party.role}) via phone {payload.assigned_party.phone}",
        detected_at=payload.timestamp,
        resolved=False,
    )
    session.add(bottleneck)
    await session.flush()

    # 2. Determine communication channel & tone
    channel = CommunicationChannel.SMS.value if payload.assigned_party.phone else CommunicationChannel.EMAIL.value
    role = payload.assigned_party.role
    name = payload.assigned_party.name
    recipient_target = payload.assigned_party.phone or payload.assigned_party.user_id

    # Formulate context-aware drafted message
    subject = f"[{payload.severity.upper()} SLA NOTICE] Case {app_no} Attention Required"
    delay_min = round(payload.metrics.delay_seconds / 60.0)
    body = (
        f"Subject: {subject}\n\n"
        f"Dear {name} ({role}),\n\n"
        f"{message_text}\n\n"
        f"Delay recorded: {delay_min} minutes past threshold. Please finalize and submit your pending report "
        f"via the portal immediately to prevent further escalation:\n"
        f"https://portal.digivaluer.example.com/cases/{app_no}/workflow\n\n"
        f"— DigiValuer Sentinel Operations Watchdog"
    )

    intervention = AgentIntervention(
        case_id=app_no,
        recipient_id=recipient_target,
        recipient_role=role,
        stage=payload.application.status,
        reminder_count=1,
        drafted_message=body,
        channel=channel,
        status=InterventionStatus.DRAFTED.value,
        sent_at=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    session.add(intervention)
    await session.flush()

    # Respect Human-in-the-Loop policy
    dispatched = False
    if not settings.HUMAN_IN_THE_LOOP:
        dispatcher = get_notification_dispatcher()
        dispatch_res = await dispatcher.dispatch(
            channel=channel,
            recipient_id=recipient_target,
            subject=subject,
            message=body,
            case_id=app_no,
        )
        if dispatch_res.get("success"):
            intervention.status = InterventionStatus.SENT.value
            intervention.sent_at = datetime.now(timezone.utc)
            dispatched = True
        else:
            intervention.status = InterventionStatus.FAILED.value
        session.add(intervention)

    # 3. Log audit event
    action_log = AgentActionLog(
        case_id=case.id,
        agent_name="DigiValuerWebhook",
        action_type=payload.event_type.upper(),
        details=f"Recorded bottleneck '{payload.category}' (Severity: {payload.severity}). Intervention #{intervention.id} created.",
        timestamp=datetime.now(timezone.utc),
    )
    session.add(action_log)

    await session.commit()

    # 4. Broadcast live update to Redis Pub/Sub
    broadcast_data = {
        "event_id": payload.event_id,
        "case_number": app_no,
        "category": payload.category,
        "severity": payload.severity,
        "bottleneck_id": bottleneck.id,
        "intervention_id": intervention.id,
        "status": intervention.status,
    }
    await broadcast_sentinel_event(payload.event_type.upper(), broadcast_data)

    return {
        "status": "success",
        "action": "bottleneck_and_intervention_created",
        "case_number": app_no,
        "bottleneck_id": bottleneck.id,
        "intervention_id": intervention.id,
        "intervention_status": intervention.status,
        "auto_dispatched": dispatched,
    }


async def _handle_generic_event(
    payload: DigiValuerWebhookPayload,
    session: AsyncSession,
) -> Dict[str, Any]:
    """Handle generic or unrecognized event types with state sync and logging."""
    case = await _get_or_create_valuation_case(payload, session)
    action_log = AgentActionLog(
        case_id=case.id,
        agent_name="DigiValuerWebhook",
        action_type=payload.event_type.upper(),
        details=payload.details.message or f"Generic webhook event {payload.event_type} processed",
        timestamp=datetime.now(timezone.utc),
    )
    session.add(action_log)
    await session.commit()
    return {"status": "success", "action": "logged_generic_event", "case_number": payload.application.application_no}

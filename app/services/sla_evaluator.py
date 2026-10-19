from datetime import datetime, timezone
import logging
from typing import Dict, List, Optional
from pydantic import BaseModel
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.agent import (
    AgentIntervention,
    CaseSLAConfig,
    EscalationRule,
    InterventionStatus,
    RecipientRole,
)
from app.services.digivaluer_client import DigiValuerCase

logger = logging.getLogger("services.evaluator")


class ActionableOverdueCase(BaseModel):
    """Represents a valuation case that has breached or is nearing its stage SLA

    and is eligible for an agentic intervention (cooling-off period respected).
    """

    case: DigiValuerCase
    stage_id: str
    stage_name: str
    elapsed_hours: float
    target_duration_hours: float
    critical_warning_threshold_hours: float
    is_breached: bool
    is_warning: bool
    previous_reminder_count: int
    next_reminder_count: int
    should_escalate: bool
    escalate_to_role: Optional[str] = None
    target_recipient_id: str
    target_recipient_name: str
    target_recipient_role: str


def ensure_utc(dt: datetime) -> datetime:
    """Ensure datetime object is timezone-aware in UTC."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


async def evaluate_active_cases(
    cases: List[DigiValuerCase],
    session: AsyncSession,
    cooling_off_hours: float = 12.0,
    reference_time: Optional[datetime] = None,
) -> List[ActionableOverdueCase]:
    """Evaluate active valuation cases against SLA stage configs and intervention history.

    Filters and returns only actionable overdue cases that are not in a cooling-off window.
    """
    now = ensure_utc(reference_time) if reference_time else datetime.now(timezone.utc)

    # 1. Preload all SLA configurations
    sla_result = await session.exec(select(CaseSLAConfig))
    sla_configs: Dict[str, CaseSLAConfig] = {cfg.stage_id: cfg for cfg in sla_result.all()}

    # 2. Preload all Escalation Rules
    esc_result = await session.exec(select(EscalationRule))
    escalation_rules: Dict[str, EscalationRule] = {rule.stage_id: rule for rule in esc_result.all()}

    actionable_cases: List[ActionableOverdueCase] = []

    for case in cases:
        stage_cfg = sla_configs.get(case.current_stage)
        if not stage_cfg:
            logger.debug(
                "No SLA config defined for stage '%s' (Case ID: %s). Skipping.",
                case.current_stage,
                case.case_id,
            )
            continue

        # Calculate elapsed time in current stage
        entered_at = ensure_utc(case.stage_entered_at)
        elapsed_seconds = (now - entered_at).total_seconds()
        elapsed_hours = round(max(0.0, elapsed_seconds / 3600.0), 2)

        is_breached = elapsed_hours >= stage_cfg.target_duration_hours
        is_warning = elapsed_hours >= stage_cfg.critical_warning_threshold_hours

        # If neither warning threshold nor breach target has been met, the case is on track
        if not (is_breached or is_warning):
            continue

        # 3. Query existing interventions for this case and current stage
        statement = (
            select(AgentIntervention)
            .where(
                AgentIntervention.case_id == case.case_id,
                AgentIntervention.stage == case.current_stage,
            )
            .order_by(AgentIntervention.created_at.desc())
        )
        history_result = await session.exec(statement)
        interventions = history_result.all()

        # Check cooling-off period against any sent or approved interventions
        in_cooling_off = False
        sent_interventions = [
            inv for inv in interventions
            if inv.status in (InterventionStatus.SENT.value, InterventionStatus.APPROVED.value)
        ]

        for inv in sent_interventions:
            inv_time = ensure_utc(inv.sent_at or inv.created_at)
            hours_since_sent = (now - inv_time).total_seconds() / 3600.0
            if hours_since_sent < cooling_off_hours:
                logger.info(
                    "Case %s (stage %s) is overdue but in cooling-off window (sent %.1fh ago, cooling %.1fh).",
                    case.case_id,
                    case.current_stage,
                    hours_since_sent,
                    cooling_off_hours,
                )
                in_cooling_off = True
                break

        if in_cooling_off:
            continue

        previous_reminder_count = len(sent_interventions)
        next_reminder_count = previous_reminder_count + 1

        # Check escalation rule
        esc_rule = escalation_rules.get(case.current_stage)
        should_escalate = False
        escalate_to_role = None

        if esc_rule and next_reminder_count > esc_rule.max_reminders:
            should_escalate = True
            escalate_to_role = esc_rule.escalation_target_role

        # Default recipient is the assigned owner; escalations will target the escalation role
        recipient_id = case.assigned_owner.email
        recipient_name = case.assigned_owner.name
        recipient_role = (
            escalate_to_role if should_escalate and escalate_to_role else RecipientRole.CASE_OWNER.value
        )

        actionable_cases.append(
            ActionableOverdueCase(
                case=case,
                stage_id=stage_cfg.stage_id,
                stage_name=stage_cfg.stage_name,
                elapsed_hours=elapsed_hours,
                target_duration_hours=stage_cfg.target_duration_hours,
                critical_warning_threshold_hours=stage_cfg.critical_warning_threshold_hours,
                is_breached=is_breached,
                is_warning=is_warning,
                previous_reminder_count=previous_reminder_count,
                next_reminder_count=next_reminder_count,
                should_escalate=should_escalate,
                escalate_to_role=escalate_to_role,
                target_recipient_id=recipient_id,
                target_recipient_name=recipient_name,
                target_recipient_role=recipient_role,
            )
        )

    logger.info("Identified %d actionable overdue cases out of %d active cases.", len(actionable_cases), len(cases))
    return actionable_cases

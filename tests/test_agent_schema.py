from datetime import datetime, timezone
import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.seed import seed_database
from app.models.agent import (
    AgentIntervention,
    AgentMetrics,
    CaseSLAConfig,
    CommunicationChannel,
    EscalationRule,
    InterventionStatus,
    RecipientRole,
)


@pytest.mark.asyncio
async def test_seed_and_query_sla_configs(db_session: AsyncSession):
    """Verify that seed script populates and can query CaseSLAConfig records."""
    await seed_database()

    result = await db_session.exec(select(CaseSLAConfig))
    configs = result.all()
    assert len(configs) >= 4

    stage_ids = {cfg.stage_id for cfg in configs}
    assert "document_verification" in stage_ids
    assert "site_inspection" in stage_ids
    assert "final_assessment" in stage_ids

    # Verify inspection SLA config specifically
    insp = next(c for c in configs if c.stage_id == "site_inspection")
    assert insp.target_duration_hours == 48.0
    assert insp.critical_warning_threshold_hours == 36.0


@pytest.mark.asyncio
async def test_escalation_rules(db_session: AsyncSession):
    """Verify that EscalationRule records exist and have valid attributes."""
    result = await db_session.exec(
        select(EscalationRule).where(EscalationRule.stage_id == "final_assessment")
    )
    rule = result.first()
    assert rule is not None
    assert rule.max_reminders == 2
    assert rule.escalation_target_role == "Chief Appraiser"


@pytest.mark.asyncio
async def test_agent_intervention_lifecycle(db_session: AsyncSession):
    """Verify full CRUD lifecycle for AgentIntervention model."""
    intervention = AgentIntervention(
        case_id="DV-CASE-101",
        recipient_id="appraiser.smith@example.com",
        recipient_role=RecipientRole.CASE_OWNER.value,
        stage="site_inspection",
        reminder_count=1,
        drafted_message="Reminder: Site inspection report for 742 Evergreen Terrace is pending.",
        channel=CommunicationChannel.EMAIL.value,
        status=InterventionStatus.DRAFTED.value,
    )
    db_session.add(intervention)
    await db_session.commit()
    await db_session.refresh(intervention)

    assert intervention.id is not None
    assert intervention.status == InterventionStatus.DRAFTED.value

    # Update to SENT
    intervention.status = InterventionStatus.SENT.value
    intervention.sent_at = datetime.now(timezone.utc)
    db_session.add(intervention)
    await db_session.commit()
    await db_session.refresh(intervention)

    assert intervention.status == InterventionStatus.SENT.value
    assert intervention.sent_at is not None


@pytest.mark.asyncio
async def test_agent_metrics_recording(db_session: AsyncSession):
    """Verify storing and querying AgentMetrics model."""
    metrics = AgentMetrics(
        case_id="DV-CASE-101",
        duration_saved=14.5,
        response_time_hours=2.5,
        completed_after_reminder=True,
    )
    db_session.add(metrics)
    await db_session.commit()
    await db_session.refresh(metrics)

    assert metrics.id is not None
    assert metrics.duration_saved == 14.5
    assert metrics.completed_after_reminder is True

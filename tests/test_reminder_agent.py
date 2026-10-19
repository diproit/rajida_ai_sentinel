from datetime import datetime, timezone
import uuid
import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.agents.reminder_agent import (
    DraftedReminderOutput,
    ToneLevel,
    determine_tone_level,
    generate_case_reminder,
)
from app.models.agent import (
    AgentIntervention,
    CommunicationChannel,
    InterventionStatus,
    RecipientRole,
)
from app.services.digivaluer_client import AssignedOwner, DigiValuerCase, StakeholderContact
from app.services.sla_evaluator import ActionableOverdueCase


def build_sample_case(case_id: str, current_stage: str = "site_inspection") -> DigiValuerCase:
    now = datetime.now(timezone.utc)
    return DigiValuerCase(
        case_id=case_id,
        property_address="742 Evergreen Terrace, Springfield, IL",
        property_type="Single Family Residence",
        current_stage=current_stage,
        stage_entered_at=now,
        last_updated_at=now,
        assigned_owner=AssignedOwner(
            owner_id="appr_01",
            name="Alice Smith",
            email="alice.smith@digivaluer.example.com",
            role="Case Owner",
        ),
        stakeholder_contacts=[
            StakeholderContact(
                contact_id="stk_01",
                name="Homer Simpson",
                email="homer@springfield.net",
                role="Borrower",
            )
        ],
        status="OPEN",
    )


@pytest.mark.asyncio
async def test_tone_level_progression():
    """Verify that tone level scales from Gentle -> Firm -> Escalated."""
    assert determine_tone_level(reminder_count=1) == ToneLevel.GENTLE
    assert determine_tone_level(reminder_count=2) == ToneLevel.FIRM
    assert determine_tone_level(reminder_count=3) == ToneLevel.ESCALATED
    assert determine_tone_level(reminder_count=4) == ToneLevel.ESCALATED
    assert determine_tone_level(reminder_count=1, should_escalate=True) == ToneLevel.ESCALATED


@pytest.mark.asyncio
async def test_internal_case_owner_reminder_gentle():
    """Verify drafting a 1st reminder for an internal case owner (Gentle tone)."""
    case = build_sample_case(case_id="DV-CASE-PHOTO-01", current_stage="site_inspection")
    sla_info = {
        "stage_id": "site_inspection",
        "stage_name": "Site Inspection",
        "elapsed_hours": 50.0,
        "target_duration_hours": 48.0,
        "critical_warning_threshold_hours": 36.0,
    }

    draft, intervention = await generate_case_reminder(
        case_data=case,
        sla_data=sla_info,
        previous_interventions=[],
        missing_items="Missing exterior front & street scene photo upload",
        is_external=False,
    )

    assert isinstance(draft, DraftedReminderOutput)
    assert draft.tone_level == ToneLevel.GENTLE
    assert "photo" in draft.body.lower()
    assert "https://portal.digivaluer.example.com/cases/DV-CASE-PHOTO-01/workflow" in draft.body
    assert draft.suggested_channel in (CommunicationChannel.EMAIL, CommunicationChannel.SLACK)
    assert intervention is None  # No db session passed


@pytest.mark.asyncio
async def test_internal_case_owner_reminder_firm():
    """Verify drafting a 2nd reminder for an internal case owner (Firm tone)."""
    case = build_sample_case(case_id="DV-CASE-PHOTO-02", current_stage="site_inspection")
    sla_info = {
        "stage_id": "site_inspection",
        "stage_name": "Site Inspection",
        "elapsed_hours": 58.0,
        "target_duration_hours": 48.0,
        "critical_warning_threshold_hours": 36.0,
    }

    # Simulate 1 previously sent intervention
    inv1 = AgentIntervention(
        case_id="DV-CASE-PHOTO-02",
        recipient_id="alice.smith@digivaluer.example.com",
        recipient_role=RecipientRole.CASE_OWNER.value,
        stage="site_inspection",
        reminder_count=1,
        drafted_message="First reminder",
        channel=CommunicationChannel.EMAIL.value,
        status=InterventionStatus.SENT.value,
    )

    draft, _ = await generate_case_reminder(
        case_data=case,
        sla_data=sla_info,
        previous_interventions=[inv1],
        missing_items=["exterior front photo upload", "roof condition notes"],
        is_external=False,
    )

    assert draft.tone_level == ToneLevel.FIRM
    assert "photo" in draft.body.lower()
    assert "roof" in draft.body.lower()


@pytest.mark.asyncio
async def test_external_stakeholder_courteous_reminder():
    """Verify drafting consumer-friendly message for external stakeholders without technical jargon."""
    case = build_sample_case(case_id="DV-CASE-EXT-01", current_stage="site_inspection")
    sla_info = {
        "stage_id": "site_inspection",
        "stage_name": "Site Inspection",
        "elapsed_hours": 40.0,
        "target_duration_hours": 48.0,
        "critical_warning_threshold_hours": 36.0,
    }

    draft, _ = await generate_case_reminder(
        case_data=case,
        sla_data=sla_info,
        previous_interventions=[],
        missing_items="Confirmation of property access date and time",
        is_external=True,
        target_recipient=("homer@springfield.net", "Homer Simpson", "Borrower"),
    )

    assert draft.tone_level == ToneLevel.GENTLE
    assert "Homer" in draft.body
    assert any(term in draft.body.lower() for term in ["access", "visit", "inspection"])
    assert "SLA breach" not in draft.body  # Non-technical, courteous language
    assert "workflow stage ID" not in draft.body


@pytest.mark.asyncio
async def test_save_drafted_intervention_to_database(db_session: AsyncSession):
    """Verify that generate_case_reminder saves to agent_interventions with status 'DRAFTED'."""
    case_uid = f"DV-CASE-{uuid.uuid4().hex[:6]}"
    case = build_sample_case(case_id=case_uid, current_stage="document_verification")
    sla_info = {
        "stage_id": "document_verification",
        "stage_name": "Document Verification",
        "elapsed_hours": 26.0,
        "target_duration_hours": 24.0,
        "critical_warning_threshold_hours": 18.0,
    }

    draft, intervention = await generate_case_reminder(
        case_data=case,
        sla_data=sla_info,
        previous_interventions=[],
        missing_items="Missing high-resolution front elevation photo upload",
        is_external=False,
        session=db_session,
    )

    assert intervention is not None
    assert intervention.id is not None
    assert intervention.case_id == case_uid
    assert intervention.status == InterventionStatus.DRAFTED.value
    assert intervention.sent_at is None
    assert intervention.reminder_count == 1
    assert "front elevation photo" in intervention.drafted_message

    # Query from database to verify persistence
    result = await db_session.exec(
        select(AgentIntervention).where(AgentIntervention.id == intervention.id)
    )
    saved = result.first()
    assert saved is not None
    assert saved.status == "DRAFTED"
    assert saved.recipient_id == "alice.smith@digivaluer.example.com"

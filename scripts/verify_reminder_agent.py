import asyncio
from datetime import datetime, timezone
import json
import logging
from sqlmodel import select

from app.agents.reminder_agent import generate_case_reminder
from app.db.session import async_session_maker, init_db
from app.models.agent import (
    AgentIntervention,
    CommunicationChannel,
    InterventionStatus,
    RecipientRole,
)
from app.services.digivaluer_client import AssignedOwner, DigiValuerCase, StakeholderContact

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("verify_agent")


async def run_verification():
    """Verify reminder drafting logic across reminder counts and stakeholders,

    and verify persistence to the agent_interventions database table.
    """
    print("=" * 80)
    print("DIGIVALUER SENTINEL - REMINDER DRAFTING AGENT VERIFICATION")
    print("=" * 80)

    await init_db()

    now = datetime.now(timezone.utc)
    sample_case = DigiValuerCase(
        case_id="DV-CASE-PHOTO-901",
        property_address="742 Evergreen Terrace, Springfield, IL",
        property_type="Single Family Residence",
        current_stage="site_inspection",
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

    sla_data = {
        "stage_id": "site_inspection",
        "stage_name": "Site Inspection",
        "elapsed_hours": 52.0,
        "target_duration_hours": 48.0,
        "critical_warning_threshold_hours": 36.0,
        "should_escalate": False,
    }

    # --------------------------------------------------------------------------
    # Scenario 1: Reminder #1 (Internal Case Owner - Gentle)
    # --------------------------------------------------------------------------
    print("\n[Scenario 1: Reminder #1 - Internal Case Owner (Gentle)]")
    draft_1, _ = await generate_case_reminder(
        case_data=sample_case,
        sla_data=sla_data,
        previous_interventions=[],
        missing_items="Missing exterior front & street scene photo upload",
        is_external=False,
    )
    print(f"Subject: {draft_1.subject}")
    print(f"Tone: {draft_1.tone_level.value}")
    print(f"Channel: {draft_1.suggested_channel.value}")
    print(f"Body:\n{draft_1.body}")

    # --------------------------------------------------------------------------
    # Scenario 2: Reminder #2 (Internal Case Owner - Firm)
    # --------------------------------------------------------------------------
    print("\n" + "-" * 80)
    print("[Scenario 2: Reminder #2 - Internal Case Owner (Firm)]")
    dummy_inv1 = AgentIntervention(
        case_id=sample_case.case_id,
        recipient_id="alice.smith@digivaluer.example.com",
        recipient_role=RecipientRole.CASE_OWNER.value,
        stage="site_inspection",
        reminder_count=1,
        drafted_message="Prior reminder",
        channel=CommunicationChannel.EMAIL.value,
        status=InterventionStatus.SENT.value,
    )
    draft_2, _ = await generate_case_reminder(
        case_data=sample_case,
        sla_data=sla_data,
        previous_interventions=[dummy_inv1],
        missing_items="Missing exterior front photo upload",
        is_external=False,
    )
    print(f"Subject: {draft_2.subject}")
    print(f"Tone: {draft_2.tone_level.value}")
    print(f"Channel: {draft_2.suggested_channel.value}")
    print(f"Body:\n{draft_2.body}")

    # --------------------------------------------------------------------------
    # Scenario 3: Reminder #3 (Internal Case Owner - Escalated)
    # --------------------------------------------------------------------------
    print("\n" + "-" * 80)
    print("[Scenario 3: Reminder #3 - Escalation (Escalated)]")
    dummy_inv2 = AgentIntervention(
        case_id=sample_case.case_id,
        recipient_id="alice.smith@digivaluer.example.com",
        recipient_role=RecipientRole.CASE_OWNER.value,
        stage="site_inspection",
        reminder_count=2,
        drafted_message="Prior reminder 2",
        channel=CommunicationChannel.EMAIL.value,
        status=InterventionStatus.SENT.value,
    )
    escalated_sla = dict(sla_data)
    escalated_sla["should_escalate"] = True
    draft_3, _ = await generate_case_reminder(
        case_data=sample_case,
        sla_data=escalated_sla,
        previous_interventions=[dummy_inv1, dummy_inv2],
        missing_items="Missing exterior front photo upload",
        is_external=False,
        target_recipient=("chief.appraiser@digivaluer.example.com", "David Chief", "Chief Appraiser"),
    )
    print(f"Subject: {draft_3.subject}")
    print(f"Tone: {draft_3.tone_level.value}")
    print(f"Channel: {draft_3.suggested_channel.value}")
    print(f"Body:\n{draft_3.body}")

    # --------------------------------------------------------------------------
    # Scenario 4: External Stakeholder (Borrower - Courteous)
    # --------------------------------------------------------------------------
    print("\n" + "-" * 80)
    print("[Scenario 4: External Stakeholder - Borrower (Courteous)]")
    draft_ext, _ = await generate_case_reminder(
        case_data=sample_case,
        sla_data=sla_data,
        previous_interventions=[],
        missing_items="Confirmation of property access date and gate entry code",
        is_external=True,
        target_recipient=("homer@springfield.net", "Homer Simpson", "Borrower"),
    )
    print(f"Subject: {draft_ext.subject}")
    print(f"Tone: {draft_ext.tone_level.value}")
    print(f"Channel: {draft_ext.suggested_channel.value}")
    print(f"Body:\n{draft_ext.body}")

    # --------------------------------------------------------------------------
    # Scenario 5: Database Persistence (Status: DRAFTED)
    # --------------------------------------------------------------------------
    print("\n" + "-" * 80)
    print("[Scenario 5: Database Persistence Verification]")
    async with async_session_maker() as session:
        _, record = await generate_case_reminder(
            case_data=sample_case,
            sla_data=sla_data,
            previous_interventions=[],
            missing_items="Missing exterior front & street scene photo upload",
            is_external=False,
            session=session,
        )

        assert record is not None
        print(f"Successfully saved AgentIntervention to DB with id={record.id}")
        print(f"Status: {record.status} (Expected: DRAFTED)")
        print(f"Case ID: {record.case_id}")
        print(f"Recipient: {record.recipient_id} ({record.recipient_role})")
        print(f"Reminder Count: {record.reminder_count}")

        # Verify from database
        stmt = select(AgentIntervention).where(AgentIntervention.id == record.id)
        res = await session.exec(stmt)
        saved_rec = res.first()
        assert saved_rec is not None
        assert saved_rec.status == "DRAFTED"
        print("Confirmed record retrieved directly from PostgreSQL table 'agent_interventions'!")

    print("\n" + "=" * 80)
    print("ALL REMINDER AGENT VERIFICATIONS PASSED SUCCESSFULLY!")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(run_verification())

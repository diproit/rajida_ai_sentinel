from datetime import datetime, timedelta, timezone
import uuid
import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.seed import seed_database
from app.models.agent import (
    AgentIntervention,
    CommunicationChannel,
    InterventionStatus,
    RecipientRole,
)
from app.services.digivaluer_client import (
    AssignedOwner,
    DigiValuerCase,
    DigiValuerClient,
    StakeholderContact,
)
from app.services.sla_evaluator import evaluate_active_cases


@pytest.fixture(autouse=True)
async def setup_seed_data():
    """Ensure SLA configurations and escalation rules are seeded for evaluator tests."""
    await seed_database()


def build_case(
    case_id: str,
    stage: str,
    hours_ago: float,
    now: datetime,
) -> DigiValuerCase:
    return DigiValuerCase(
        case_id=case_id,
        property_address=f"Property for {case_id}",
        current_stage=stage,
        stage_entered_at=now - timedelta(hours=hours_ago),
        last_updated_at=now - timedelta(hours=hours_ago),
        assigned_owner=AssignedOwner(
            owner_id="appr_01",
            name="Alice Smith",
            email="alice.smith@example.com",
        ),
        stakeholder_contacts=[
            StakeholderContact(
                contact_id="stk_01",
                name="Bob Jones",
                email="bob.jones@example.com",
                role="Borrower",
            )
        ],
        status="OPEN",
    )


@pytest.mark.asyncio
async def test_sla_evaluator_filtering(db_session: AsyncSession):
    """Test core requirement: only stagnant cases pass evaluator;

    active and recently reminded cases are excluded.
    """
    now = datetime(2026, 10, 19, 12, 0, 0, tzinfo=timezone.utc)
    tag = uuid.uuid4().hex[:6]

    # 1. Stagnant case (28 hours in document_verification, SLA target is 24h)
    stagnant_id = f"DV-STAGNANT-{tag}"
    stagnant_case = build_case(stagnant_id, "document_verification", 28.0, now)

    # 2. Active case (12 hours in site_inspection, SLA target is 48h, warning is 36h)
    active_id = f"DV-ACTIVE-{tag}"
    active_case = build_case(active_id, "site_inspection", 12.0, now)

    # 3. Recently reminded case (30 hours in document_verification, but reminded 4 hours ago)
    recent_id = f"DV-RECENT-REMINDED-{tag}"
    recently_reminded_case = build_case(recent_id, "document_verification", 30.0, now)

    # Insert a recent intervention for case 3 (4 hours before now)
    recent_intervention = AgentIntervention(
        case_id=recent_id,
        recipient_id="alice.smith@example.com",
        recipient_role=RecipientRole.CASE_OWNER.value,
        stage="document_verification",
        reminder_count=1,
        drafted_message="First reminder sent.",
        channel=CommunicationChannel.EMAIL.value,
        status=InterventionStatus.SENT.value,
        sent_at=now - timedelta(hours=4),
        created_at=now - timedelta(hours=4),
    )
    db_session.add(recent_intervention)
    await db_session.commit()

    # Run evaluator on the three cases
    cases = [stagnant_case, active_case, recently_reminded_case]
    actionable_results = await evaluate_active_cases(
        cases=cases,
        session=db_session,
        cooling_off_hours=12.0,
        reference_time=now,
    )

    # VERIFY: Exactly 1 case passes the evaluator (the stagnant case)
    assert len(actionable_results) == 1
    result = actionable_results[0]

    assert result.case.case_id == stagnant_id
    assert result.stage_id == "document_verification"
    assert result.elapsed_hours == 28.0
    assert result.is_breached is True
    assert result.previous_reminder_count == 0
    assert result.next_reminder_count == 1
    assert result.should_escalate is False
    assert result.target_recipient_id == "alice.smith@example.com"


@pytest.mark.asyncio
async def test_cooling_off_expiration_and_escalation(db_session: AsyncSession):
    """Verify that after cooling-off expires, the case is actionable again,

    and triggers escalation once max_reminders threshold is exceeded.
    """
    now = datetime(2026, 10, 19, 12, 0, 0, tzinfo=timezone.utc)

    case_uid = f"DV-MOCK-ESCALATE-{uuid.uuid4().hex[:6]}"
    # Document verification config: max_reminders = 2, target = 24h, warning = 18h
    escalating_case = build_case(case_uid, "document_verification", 45.0, now)

    # Add 2 historical reminders: 30 hours ago and 15 hours ago (> 12h cooling-off)
    inv1 = AgentIntervention(
        case_id=case_uid,
        recipient_id="alice.smith@example.com",
        recipient_role=RecipientRole.CASE_OWNER.value,
        stage="document_verification",
        reminder_count=1,
        drafted_message="Reminder 1",
        channel=CommunicationChannel.EMAIL.value,
        status=InterventionStatus.SENT.value,
        sent_at=now - timedelta(hours=30),
        created_at=now - timedelta(hours=30),
    )
    inv2 = AgentIntervention(
        case_id=case_uid,
        recipient_id="alice.smith@example.com",
        recipient_role=RecipientRole.CASE_OWNER.value,
        stage="document_verification",
        reminder_count=2,
        drafted_message="Reminder 2",
        channel=CommunicationChannel.EMAIL.value,
        status=InterventionStatus.SENT.value,
        sent_at=now - timedelta(hours=15),  # 15h > 12h cooling-off
        created_at=now - timedelta(hours=15),
    )
    db_session.add(inv1)
    db_session.add(inv2)
    await db_session.commit()

    results = await evaluate_active_cases(
        cases=[escalating_case],
        session=db_session,
        cooling_off_hours=12.0,
        reference_time=now,
    )

    assert len(results) == 1
    res = results[0]
    assert res.case.case_id == case_uid
    assert res.previous_reminder_count == 2
    assert res.next_reminder_count == 3
    # document_verification has max_reminders = 2; next reminder is 3, so should_escalate = True
    assert res.should_escalate is True
    assert res.escalate_to_role == "Senior Reviewer"
    assert res.target_recipient_role == "Senior Reviewer"


@pytest.mark.asyncio
async def test_digivaluer_client_active_cases(db_session: AsyncSession):
    """Verify DigiValuerClient fetches cases and feeds seamlessly into the evaluator."""
    client = DigiValuerClient(use_mock=True)
    cases = await client.get_active_cases()

    assert len(cases) >= 3
    case_ids = [c.case_id for c in cases]
    assert "DV-CASE-001" in case_ids
    assert "DV-CASE-002" in case_ids

    # Run evaluator on the client's fetched cases (setting cooling_off_hours=0.0 to evaluate raw SLA criteria)
    actionable = await evaluate_active_cases(cases=cases, session=db_session, cooling_off_hours=0.0)
    # DV-CASE-001 (doc verification 32h) and DV-CASE-003 (final assessment 28h) should be actionable
    actionable_ids = [a.case.case_id for a in actionable]
    assert "DV-CASE-001" in actionable_ids
    assert "DV-CASE-003" in actionable_ids
    assert "DV-CASE-002" not in actionable_ids  # On-track (only 8h in site inspection)


@pytest.mark.asyncio
async def test_api_overdue_cases_endpoint(async_client):
    """Verify HTTP GET /api/v1/workflows/overdue-cases returns actionable cases."""
    response = await async_client.get("/api/v1/workflows/overdue-cases?cooling_off_hours=0")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 2
    case_ids = [item["case"]["case_id"] for item in data]
    assert "DV-CASE-001" in case_ids
    assert "DV-CASE-003" in case_ids

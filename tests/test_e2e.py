from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch
import uuid
import pytest
from httpx import AsyncClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.seed import seed_database
from app.models.agent import AgentIntervention, InterventionStatus
from app.services.digivaluer_client import AssignedOwner, DigiValuerCase, StakeholderContact
from app.worker import run_sentinel_scan


@pytest.fixture(autouse=True)
async def setup_seed_data():
    """Ensure SLA configurations and escalation rules are seeded in PostgreSQL."""
    await seed_database()


def build_e2e_case(
    case_id: str,
    stage: str,
    elapsed_hours: float,
    owner_name: str,
    owner_email: str,
    status: str = "OPEN",
) -> DigiValuerCase:
    """Helper to construct synthetic DigiValuer valuation cases."""
    now = datetime.now(timezone.utc)
    stage_entered = now - timedelta(hours=elapsed_hours)
    return DigiValuerCase(
        case_id=case_id,
        property_address=f"Property {case_id}, Metro District",
        property_type="Single Family Residence",
        current_stage=stage,
        stage_entered_at=stage_entered,
        last_updated_at=stage_entered,
        assigned_owner=AssignedOwner(
            owner_id=f"usr_{case_id.lower()}",
            name=owner_name,
            email=owner_email,
            role="Case Owner",
        ),
        stakeholder_contacts=[
            StakeholderContact(
                contact_id=f"stk_{case_id.lower()}",
                name=f"Borrower for {case_id}",
                email=f"borrower_{case_id.lower()}@example.com",
                role="Borrower",
            )
        ],
        status=status,
    )


@pytest.mark.asyncio
async def test_end_to_end_sentinel_pipeline(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """End-to-End Integration Test:

    1. Injects mock cases with elapsed times exceeding SLA limits into DigiValuer client.
    2. Triggers the worker scan.
    3. Asserts that intervention records are created in PostgreSQL with status DRAFTED.
    4. Simulates admin approval via the API endpoint.
    5. Verifies notification dispatch functions are called with expected parameters.
    6. Confirms PostgreSQL records transition to SENT with sent_at timestamps.
    """
    uid = uuid.uuid4().hex[:6]
    case_stalled_1 = f"DV-E2E-DOC-{uid}"
    case_stalled_2 = f"DV-E2E-FINAL-{uid}"
    case_active_ontrack = f"DV-E2E-OK-{uid}"

    # Document Verification SLA: 24h (warning 18h). Elapsed: 32h -> STALLED
    stalled_case_1 = build_e2e_case(
        case_id=case_stalled_1,
        stage="document_verification",
        elapsed_hours=32.0,
        owner_name="Sarah Jenkins",
        owner_email="sarah.jenkins@digivaluer.example.com",
    )

    # Final Assessment SLA: 24h (warning 20h). Elapsed: 28h -> STALLED
    stalled_case_2 = build_e2e_case(
        case_id=case_stalled_2,
        stage="final_assessment",
        elapsed_hours=28.0,
        owner_name="John Watson",
        owner_email="john.watson@digivaluer.example.com",
    )

    # Site Inspection SLA: 48h (warning 36h). Elapsed: 10h -> ON TRACK
    ontrack_case = build_e2e_case(
        case_id=case_active_ontrack,
        stage="site_inspection",
        elapsed_hours=10.0,
        owner_name="Edward Tentacles",
        owner_email="edward.tentacles@digivaluer.example.com",
    )

    mock_cases = [stalled_case_1, stalled_case_2, ontrack_case]

    # Step 1 & 2: Inject mock cases into client and trigger worker scan
    with patch("app.services.digivaluer_client.DigiValuerClient.get_active_cases", return_value=mock_cases):
        scan_result = await run_sentinel_scan(
            session=db_session,
            force_dispatch=False,  # Human-in-the-Loop enabled
            cooling_off_hours=0.0,
        )

    assert scan_result["status"] == "success"
    assert scan_result["total_cases_scanned"] == 3
    assert scan_result["actionable_overdue_cases"] == 2
    assert scan_result["drafts_created"] == 2
    assert scan_result["held_for_review_count"] == 2
    assert scan_result["dispatched_count"] == 0

    # Step 3: Assert intervention records are created in PostgreSQL
    stmt_1 = select(AgentIntervention).where(AgentIntervention.case_id == case_stalled_1)
    res_1 = await db_session.exec(stmt_1)
    record_1 = res_1.first()
    assert record_1 is not None, f"Intervention record for {case_stalled_1} was not created in PostgreSQL"
    inv_id_1 = record_1.id
    recipient_1 = record_1.recipient_id
    assert inv_id_1 is not None
    assert record_1.status == InterventionStatus.DRAFTED.value
    assert recipient_1 == "sarah.jenkins@digivaluer.example.com"
    assert record_1.stage == "document_verification"
    assert record_1.reminder_count == 1
    assert record_1.sent_at is None
    assert "document" in record_1.drafted_message.lower() or "verification" in record_1.drafted_message.lower()

    stmt_2 = select(AgentIntervention).where(AgentIntervention.case_id == case_stalled_2)
    res_2 = await db_session.exec(stmt_2)
    record_2 = res_2.first()
    assert record_2 is not None, f"Intervention record for {case_stalled_2} was not created in PostgreSQL"
    inv_id_2 = record_2.id
    recipient_2 = record_2.recipient_id
    assert inv_id_2 is not None
    assert record_2.status == InterventionStatus.DRAFTED.value
    assert recipient_2 == "john.watson@digivaluer.example.com"
    assert record_2.stage == "final_assessment"
    assert record_2.sent_at is None

    # Verify on-track case has NO interventions
    stmt_ontrack = select(AgentIntervention).where(AgentIntervention.case_id == case_active_ontrack)
    res_ontrack = await db_session.exec(stmt_ontrack)
    assert res_ontrack.first() is None, f"On-track case {case_active_ontrack} should not have generated interventions"

    # Step 4 & 5: Simulate admin approval via the Dashboard API endpoint and verify dispatcher calls
    with patch("app.services.notifier.EmailDispatcher.send_email", new_callable=AsyncMock) as mock_send_email:
        mock_send_email.return_value = {
            "success": True,
            "channel": "EMAIL",
            "provider": "sendgrid_smtp",
            "message_id": f"msg_e2e_{uuid.uuid4().hex[:8]}",
            "recipient": recipient_1,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # Admin clicks "Approve & Send" on Dashboard for record 1
        approve_resp = await async_client.post(f"/api/dashboard/interventions/{inv_id_1}/approve")
        assert approve_resp.status_code == 200
        approve_payload = approve_resp.json()
        assert approve_payload["success"] is True
        assert approve_payload["intervention"]["status"] == "SENT"

        # Verify notification dispatch was called with expected parameters
        mock_send_email.assert_awaited_once()
        call_kwargs = mock_send_email.call_args.kwargs
        assert call_kwargs["to_email"] == "sarah.jenkins@digivaluer.example.com"
        assert len(call_kwargs["subject"]) > 0
        assert len(call_kwargs["body"]) > 0

    # Step 6: Verify PostgreSQL record 1 updated to SENT with timestamp
    await db_session.refresh(record_1)
    assert record_1.status == InterventionStatus.SENT.value
    assert record_1.sent_at is not None

    # Also test approving record 2 via the workflows API endpoint
    with patch("app.services.notifier.EmailDispatcher.send_email", new_callable=AsyncMock) as mock_send_email_2:
        mock_send_email_2.return_value = {
            "success": True,
            "channel": "EMAIL",
            "provider": "sendgrid_smtp",
            "message_id": f"msg_e2e_{uuid.uuid4().hex[:8]}",
            "recipient": recipient_2,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        approve_resp_2 = await async_client.post(f"/api/v1/workflows/interventions/{inv_id_2}/approve")
        assert approve_resp_2.status_code == 200
        assert approve_resp_2.json()["status"] == "SENT"

        mock_send_email_2.assert_awaited_once()
        call_kwargs_2 = mock_send_email_2.call_args.kwargs
        assert call_kwargs_2["to_email"] == "john.watson@digivaluer.example.com"

    # Verify PostgreSQL record 2 is updated to SENT in database
    await db_session.refresh(record_2)
    assert record_2.status == InterventionStatus.SENT.value
    assert record_2.sent_at is not None

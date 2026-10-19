from datetime import datetime, timezone
from unittest.mock import patch
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
    """Ensure SLA configurations and escalation rules are seeded."""
    await seed_database()


def create_test_case(case_id: str, stage: str, hours_ago: float) -> DigiValuerCase:
    from datetime import timedelta
    now = datetime.now(timezone.utc)
    return DigiValuerCase(
        case_id=case_id,
        property_address=f"Test Address for {case_id}",
        current_stage=stage,
        stage_entered_at=now - timedelta(hours=hours_ago),
        last_updated_at=now - timedelta(hours=hours_ago),
        assigned_owner=AssignedOwner(
            owner_id="usr_test",
            name="Test Reviewer",
            email="test.reviewer@example.com",
        ),
        stakeholder_contacts=[
            StakeholderContact(
                contact_id="stk_test",
                name="Borrower Test",
                email="borrower.test@example.com",
            )
        ],
        status="OPEN",
    )


@pytest.mark.asyncio
async def test_sentinel_scan_hitl_enabled(db_session: AsyncSession):
    """Verify that when HUMAN_IN_THE_LOOP is True, interventions remain in DRAFTED status."""
    case_uid = f"DV-HITL-{uuid.uuid4().hex[:6]}"
    test_case = create_test_case(case_uid, "document_verification", hours_ago=30.0)

    with patch("app.services.digivaluer_client.DigiValuerClient.get_active_cases", return_value=[test_case]):
        result = await run_sentinel_scan(
            session=db_session,
            force_dispatch=False,  # HITL enabled
            cooling_off_hours=0.0,
        )

        assert result["status"] == "success"
        assert result["human_in_the_loop"] is True
        assert result["drafts_created"] == 1
        assert result["held_for_review_count"] == 1
        assert result["dispatched_count"] == 0

        # Verify DB state
        stmt = select(AgentIntervention).where(AgentIntervention.case_id == case_uid)
        res = await db_session.exec(stmt)
        record = res.first()
        assert record is not None
        assert record.status == InterventionStatus.DRAFTED.value
        assert record.sent_at is None


@pytest.mark.asyncio
async def test_sentinel_scan_auto_dispatch(db_session: AsyncSession):
    """Verify that when HUMAN_IN_THE_LOOP is False (force_dispatch=True),

    interventions are automatically dispatched and updated to SENT.
    """
    case_uid = f"DV-AUTODISPATCH-{uuid.uuid4().hex[:6]}"
    test_case = create_test_case(case_uid, "document_verification", hours_ago=35.0)

    with patch("app.services.digivaluer_client.DigiValuerClient.get_active_cases", return_value=[test_case]):
        result = await run_sentinel_scan(
            session=db_session,
            force_dispatch=True,  # HITL disabled -> auto-dispatch
            cooling_off_hours=0.0,
        )

        assert result["status"] == "success"
        assert result["human_in_the_loop"] is False
        assert result["drafts_created"] == 1
        assert result["dispatched_count"] == 1
        assert result["held_for_review_count"] == 0

        # Verify DB state
        stmt = select(AgentIntervention).where(AgentIntervention.case_id == case_uid)
        res = await db_session.exec(stmt)
        record = res.first()
        assert record is not None
        assert record.status == InterventionStatus.SENT.value
        assert record.sent_at is not None


@pytest.mark.asyncio
async def test_api_scan_and_approve_workflow(async_client: AsyncClient, db_session: AsyncSession):
    """Test full API integration: trigger scan-now, then approve the drafted intervention."""
    case_uid = f"DV-API-APPROVE-{uuid.uuid4().hex[:6]}"
    test_case = create_test_case(case_uid, "final_assessment", hours_ago=30.0)

    with patch("app.services.digivaluer_client.DigiValuerClient.get_active_cases", return_value=[test_case]):
        # 1. Trigger scan via API with HITL enabled
        scan_resp = await async_client.post("/api/v1/workflows/scan-now?force_dispatch=false")
        assert scan_resp.status_code == 200
        scan_data = scan_resp.json()
        assert scan_data["status"] == "success"
        assert scan_data["held_for_review_count"] >= 1

        # Find the intervention ID created
        intervention_item = next(
            item for item in scan_data["items"] if item["case_id"] == case_uid
        )
        inv_id = intervention_item["intervention_id"]
        assert inv_id is not None

        # 2. Approve and dispatch the intervention via API
        approve_resp = await async_client.post(f"/api/v1/workflows/interventions/{inv_id}/approve")
        assert approve_resp.status_code == 200
        approve_data = approve_resp.json()
        assert approve_data["status"] == "SENT"
        assert approve_data["dispatch_details"]["success"] is True

        # 3. Verify status in database
        stmt = select(AgentIntervention).where(AgentIntervention.id == inv_id)
        res = await db_session.exec(stmt)
        db_rec = res.first()
        assert db_rec.status == "SENT"
        assert db_rec.sent_at is not None

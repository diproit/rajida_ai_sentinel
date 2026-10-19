from datetime import datetime, timezone
import uuid
import pytest
from httpx import AsyncClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.seed import seed_database
from app.models.agent import (
    AgentIntervention,
    CommunicationChannel,
    InterventionStatus,
    RecipientRole,
)


@pytest.fixture(autouse=True)
async def setup_seed_data():
    """Ensure SLA configurations and escalation rules are seeded."""
    await seed_database()


@pytest.mark.asyncio
async def test_dashboard_bottlenecks_endpoint(async_client: AsyncClient):
    """Verify GET /api/dashboard/bottlenecks aggregates cases by stage and officer."""
    response = await async_client.get("/api/dashboard/bottlenecks?cooling_off_hours=0")
    assert response.status_code == 200
    data = response.json()

    assert "summary" in data
    assert "by_stage" in data
    assert "by_officer" in data
    assert "cases" in data

    assert data["summary"]["total_active_cases"] >= 3
    assert data["summary"]["total_bottlenecks"] >= 2
    assert "document_verification" in data["by_stage"]
    assert "final_assessment" in data["by_stage"]


@pytest.mark.asyncio
async def test_dashboard_interventions_endpoint(async_client: AsyncClient, db_session: AsyncSession):
    """Verify GET /api/dashboard/interventions returns list and summary breakdown."""
    case_uid = f"DV-INT-{uuid.uuid4().hex[:6]}"
    inv = AgentIntervention(
        case_id=case_uid,
        recipient_id="officer@example.com",
        recipient_role=RecipientRole.CASE_OWNER.value,
        stage="document_verification",
        reminder_count=1,
        drafted_message="Drafted content",
        channel=CommunicationChannel.EMAIL.value,
        status=InterventionStatus.DRAFTED.value,
    )
    db_session.add(inv)
    await db_session.commit()

    # Query all interventions
    response = await async_client.get("/api/dashboard/interventions")
    assert response.status_code == 200
    data = response.json()
    assert "summary" in data
    assert "interventions" in data
    assert data["summary"]["drafted"] >= 1

    # Query with status filter
    filter_resp = await async_client.get("/api/dashboard/interventions?status=DRAFTED")
    assert filter_resp.status_code == 200
    filtered_data = filter_resp.json()
    for item in filtered_data["interventions"]:
        assert item["status"] == "DRAFTED"


@pytest.mark.asyncio
async def test_dashboard_approve_intervention(async_client: AsyncClient, db_session: AsyncSession):
    """Verify POST /api/dashboard/interventions/{id}/approve dispatches and updates status to SENT."""
    case_uid = f"DV-APPROVE-{uuid.uuid4().hex[:6]}"
    inv = AgentIntervention(
        case_id=case_uid,
        recipient_id="appraiser.approval@example.com",
        recipient_role=RecipientRole.CASE_OWNER.value,
        stage="site_inspection",
        reminder_count=1,
        drafted_message="Subject: Please upload photos\n\nHello, please upload front photos.",
        channel=CommunicationChannel.EMAIL.value,
        status=InterventionStatus.DRAFTED.value,
    )
    db_session.add(inv)
    await db_session.commit()
    await db_session.refresh(inv)

    # Approve intervention
    response = await async_client.post(f"/api/dashboard/interventions/{inv.id}/approve")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["intervention"]["status"] == "SENT"
    assert data["intervention"]["sent_at"] is not None

    # Verify directly in DB
    db_session.expire_all()
    await db_session.refresh(inv)
    assert inv.status == "SENT"
    assert inv.sent_at is not None


@pytest.mark.asyncio
async def test_dashboard_update_intervention(async_client: AsyncClient, db_session: AsyncSession):
    """Verify PUT /api/dashboard/interventions/{id} edits the drafted reminder."""
    case_uid = f"DV-EDIT-{uuid.uuid4().hex[:6]}"
    inv = AgentIntervention(
        case_id=case_uid,
        recipient_id="editor@example.com",
        recipient_role=RecipientRole.CASE_OWNER.value,
        stage="document_verification",
        reminder_count=1,
        drafted_message="Original draft",
        channel=CommunicationChannel.EMAIL.value,
        status=InterventionStatus.DRAFTED.value,
    )
    db_session.add(inv)
    await db_session.commit()
    await db_session.refresh(inv)

    # Update draft
    new_text = "Updated and personalized message for review."
    edit_resp = await async_client.put(
        f"/api/dashboard/interventions/{inv.id}",
        json={"drafted_message": new_text},
    )
    assert edit_resp.status_code == 200
    assert edit_resp.json()["intervention"]["drafted_message"] == new_text

    # Verify in DB
    await db_session.refresh(inv)
    assert inv.drafted_message == new_text


@pytest.mark.asyncio
async def test_dashboard_toggle_pause_agent(async_client: AsyncClient):
    """Verify POST /api/dashboard/cases/{id}/pause-agent toggles monitoring pause state."""
    test_case_id = f"DV-CASE-PAUSE-{uuid.uuid4().hex[:6]}"

    # 1. Pause
    resp1 = await async_client.post(f"/api/dashboard/cases/{test_case_id}/pause-agent")
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert data1["case_id"] == test_case_id
    assert data1["is_paused"] is True

    # 2. Unpause (Resume)
    resp2 = await async_client.post(f"/api/dashboard/cases/{test_case_id}/pause-agent")
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["case_id"] == test_case_id
    assert data2["is_paused"] is False


@pytest.mark.asyncio
async def test_dashboard_metrics_endpoint(async_client: AsyncClient):
    """Verify GET /api/dashboard/metrics returns KPI summary data."""
    response = await async_client.get("/api/dashboard/metrics")
    assert response.status_code == 200
    data = response.json()
    assert "total_reminders_sent" in data
    assert "average_response_time_hours" in data
    assert "duration_saved_hours" in data
    assert "completion_rate_percentage" in data

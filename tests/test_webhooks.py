from datetime import datetime, timezone
import pytest
from httpx import AsyncClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import get_settings
from app.models.agent import AgentIntervention, InterventionStatus
from app.models.valuation import ValuationCase, WorkflowBottleneck

settings = get_settings()

VALID_TOKEN = settings.DIGIVALUER_WEBHOOK_SECRET
AUTH_HEADER = {"Authorization": f"Bearer {VALID_TOKEN}"}


def sample_payload(
    event_id: str = "7f9a2b10-6c3e-4d89-9a11-e63f5891d4e0",
    event_type: str = "STATUS_CHANGED",
    severity: str = "MEDIUM",
    category: str = "STATUS_TRANSITION",
    app_no: str = "MK-88A9C12E",
    prev_status: str = "DRAFT",
    new_status: str = "VALUATION_AND_INVESTIGATION_PROCESSING",
) -> dict:
    return {
        "event_id": event_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source_system": "mekamu_mowheel",
        "environment": "production",
        "event_type": event_type,
        "severity": severity,
        "category": category,
        "application": {
            "id": "c88f9e20-7214-41bd-8c43-4c919d6756ec",
            "application_no": app_no,
            "status": new_status,
            "branch_id": "b3e945c2-192a-44e2-bca4-d19e9841f71a",
            "branch_name": "Kandy Branch",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
        "assigned_party": {
            "role": "VALUER",
            "user_id": "d14f2e50-99c1-4011-82a1-12c8a98b4ef2",
            "name": "Sunil Perera",
            "phone": "0771234567",
            "company_name": "Lanka Valuers Ltd",
            "assigned_at": datetime.now(timezone.utc).isoformat(),
        },
        "metrics": {
            "elapsed_seconds": 7800,
            "sla_threshold_seconds": 7200,
            "delay_seconds": 600,
        },
        "details": {
            "previous_status": prev_status,
            "new_status": new_status,
            "trigger_actor": "fo@mekamu.com",
            "message": "Valuer Sunil Perera has not submitted a valuation report within the 2-hour SLA window.",
        },
    }


@pytest.mark.asyncio
async def test_webhook_unauthorized_missing_token(async_client: AsyncClient):
    """Webhook rejected with 401 when Authorization header is missing."""
    payload = sample_payload()
    response = await async_client.post("/api/v1/webhooks/digivaluer", json=payload)
    assert response.status_code == 401
    assert "Missing Authorization" in response.json()["detail"]


@pytest.mark.asyncio
async def test_webhook_unauthorized_invalid_token(async_client: AsyncClient):
    """Webhook rejected with 401 when Bearer token is incorrect."""
    payload = sample_payload()
    headers = {"Authorization": "Bearer wrong_token_value_xyz"}
    response = await async_client.post("/api/v1/webhooks/digivaluer", json=payload, headers=headers)
    assert response.status_code == 401
    assert "Invalid webhook authorization" in response.json()["detail"]


@pytest.mark.asyncio
async def test_webhook_status_changed_processing(async_client: AsyncClient, db_session: AsyncSession):
    """Valid STATUS_CHANGED webhook synchronizes case and returns 202."""
    app_no = "MK-TEST-SC-01"
    payload = sample_payload(
        event_id="evt_test_sc_001",
        event_type="STATUS_CHANGED",
        app_no=app_no,
        prev_status="DRAFT",
        new_status="VALUATION_AND_INVESTIGATION_PROCESSING",
    )

    response = await async_client.post(
        "/api/v1/webhooks/digivaluer",
        json=payload,
        headers=AUTH_HEADER,
    )
    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "accepted"
    assert data["event_id"] == "evt_test_sc_001"

    # Verify case synced in database
    stmt = select(ValuationCase).where(ValuationCase.case_number == app_no)
    res = await db_session.exec(stmt)
    case = res.first()
    assert case is not None
    assert case.status == "VALUATION_AND_INVESTIGATION_PROCESSING"
    assert case.assigned_appraiser == "Sunil Perera"
    assert case.is_stalled is False


@pytest.mark.asyncio
async def test_webhook_idempotency_duplicate_event(async_client: AsyncClient):
    """Duplicate event_id returns 200 OK with duplicate status."""
    dedup_event_id = "evt_dedup_test_999"
    payload = sample_payload(event_id=dedup_event_id, app_no="MK-DEDUP-01")

    # First delivery
    res1 = await async_client.post(
        "/api/v1/webhooks/digivaluer",
        json=payload,
        headers=AUTH_HEADER,
    )
    assert res1.status_code in (200, 202)

    # Second delivery with identical event_id
    res2 = await async_client.post(
        "/api/v1/webhooks/digivaluer",
        json=payload,
        headers=AUTH_HEADER,
    )
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["status"] == "duplicate"
    assert data2["action_taken"] == "skipped"


@pytest.mark.asyncio
async def test_webhook_unresponsive_party_creates_bottleneck_and_draft(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """UNRESPONSIVE_PARTY webhook generates WorkflowBottleneck and AgentIntervention draft."""
    app_no = "MK-TEST-UNRESP-01"
    payload = sample_payload(
        event_id="evt_unresp_test_002",
        event_type="UNRESPONSIVE_PARTY",
        severity="CRITICAL",
        category="VALUER_UNRESPONSIVE",
        app_no=app_no,
    )

    response = await async_client.post(
        "/api/v1/webhooks/digivaluer",
        json=payload,
        headers=AUTH_HEADER,
    )
    assert response.status_code == 202

    # Verify bottleneck recorded
    stmt_case = select(ValuationCase).where(ValuationCase.case_number == app_no)
    case_res = await db_session.exec(stmt_case)
    case = case_res.first()
    assert case is not None
    assert case.is_stalled is True

    stmt_bn = select(WorkflowBottleneck).where(WorkflowBottleneck.case_id == case.id)
    bn_res = await db_session.exec(stmt_bn)
    bottleneck = bn_res.first()
    assert bottleneck is not None
    assert bottleneck.bottleneck_type == "VALUER_UNRESPONSIVE"
    assert bottleneck.severity == "critical"

    # Verify intervention drafted
    stmt_inv = select(AgentIntervention).where(AgentIntervention.case_id == app_no)
    inv_res = await db_session.exec(stmt_inv)
    intervention = inv_res.first()
    assert intervention is not None
    assert intervention.channel == "SMS"
    assert intervention.recipient_id == "0771234567"
    assert intervention.recipient_role == "VALUER"
    assert intervention.status == InterventionStatus.DRAFTED.value
    assert "Sunil Perera" in intervention.drafted_message

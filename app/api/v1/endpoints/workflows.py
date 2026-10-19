from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.session import get_async_session
from app.models.agent import AgentIntervention, InterventionStatus
from app.models.valuation import WorkflowBottleneck
from app.services.digivaluer_client import DigiValuerClient, get_digivaluer_client
from app.services.notifier import get_notification_dispatcher
from app.services.sla_evaluator import ActionableOverdueCase, evaluate_active_cases
from app.worker import run_sentinel_scan

router = APIRouter()


class BottleneckResponse(BaseModel):
    id: int
    case_id: int
    bottleneck_type: str
    severity: str
    description: str
    ai_recommendation: str | None = None
    resolved: bool


@router.get("/bottlenecks", response_model=List[BottleneckResponse])
async def list_bottlenecks(session: AsyncSession = Depends(get_async_session)):
    """List detected workflow bottlenecks."""
    statement = select(WorkflowBottleneck).where(WorkflowBottleneck.resolved == False)
    result = await session.exec(statement)
    return result.all()


@router.get("/overdue-cases", response_model=List[ActionableOverdueCase])
async def get_actionable_overdue_cases(
    cooling_off_hours: float = Query(default=12.0, ge=0.0, description="Cooling-off window in hours"),
    client: DigiValuerClient = Depends(get_digivaluer_client),
    session: AsyncSession = Depends(get_async_session),
):
    """Fetch active cases from DigiValuer and evaluate overdue/stalled workflows."""
    cases = await client.get_active_cases()
    return await evaluate_active_cases(
        cases=cases,
        session=session,
        cooling_off_hours=cooling_off_hours,
    )


@router.get("/interventions", response_model=List[AgentIntervention])
async def list_interventions(
    status_filter: Optional[str] = Query(default=None, description="Filter by status (DRAFTED, SENT, APPROVED, FAILED)"),
    session: AsyncSession = Depends(get_async_session),
):
    """List drafted and dispatched agent interventions."""
    statement = select(AgentIntervention).order_by(AgentIntervention.created_at.desc())
    if status_filter:
        statement = statement.where(AgentIntervention.status == status_filter.upper())
    result = await session.exec(statement)
    return result.all()


@router.post("/interventions/{intervention_id}/approve", status_code=status.HTTP_200_OK)
async def approve_and_dispatch_intervention(
    intervention_id: int,
    session: AsyncSession = Depends(get_async_session),
):
    """Approve a DRAFTED intervention (Human-in-the-Loop) and dispatch it immediately."""
    statement = select(AgentIntervention).where(AgentIntervention.id == intervention_id)
    result = await session.exec(statement)
    intervention = result.first()

    if not intervention:
        raise HTTPException(status_code=404, detail=f"Intervention #{intervention_id} not found.")

    dispatcher = get_notification_dispatcher()
    lines = intervention.drafted_message.split("\n\n", 1)
    subject = lines[0].replace("Subject: ", "") if lines else "DigiValuer Valuation Notification"
    body = lines[1] if len(lines) > 1 else intervention.drafted_message

    dispatch_res = await dispatcher.dispatch(
        channel=intervention.channel,
        recipient_id=intervention.recipient_id,
        subject=subject,
        message=body,
        case_id=intervention.case_id,
    )

    if dispatch_res.get("success"):
        intervention.status = InterventionStatus.SENT.value
        intervention.sent_at = datetime.now(timezone.utc)
    else:
        intervention.status = InterventionStatus.FAILED.value

    session.add(intervention)
    await session.commit()
    await session.refresh(intervention)

    return {
        "message": "Intervention approved and dispatched",
        "intervention_id": intervention.id,
        "status": intervention.status,
        "dispatch_details": dispatch_res,
    }


@router.post("/scan-now")
async def trigger_immediate_sentinel_scan(
    force_dispatch: Optional[bool] = Query(
        default=None,
        description="Override HUMAN_IN_THE_LOOP flag: set true to force immediate dispatch",
    ),
    session: AsyncSession = Depends(get_async_session),
) -> Dict[str, Any]:
    """Execute Sentinel scan immediately and return detailed report."""
    return await run_sentinel_scan(session=session, force_dispatch=force_dispatch)


@router.post("/scan", status_code=status.HTTP_202_ACCEPTED)
async def queue_workflow_scan():
    """Enqueue scheduled background AI agent scan in Celery."""
    from app.workers.celery_app import run_sentinel_scan_task

    task = run_sentinel_scan_task.delay()
    return {"message": "Agentic scan queued in Celery", "task_id": task.id}

from datetime import datetime, timezone
from typing import Optional
from sqlmodel import Field, SQLModel


class ValuationCase(SQLModel, table=True):
    __tablename__ = "valuation_cases"

    id: Optional[int] = Field(default=None, primary_key=True)
    case_number: str = Field(index=True, unique=True, max_length=64)
    property_address: str = Field(max_length=255)
    property_type: str = Field(default="residential", max_length=50)
    status: str = Field(default="pending_review", max_length=50)
    assigned_appraiser: Optional[str] = Field(default=None, max_length=100)
    is_stalled: bool = Field(default=False)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class WorkflowBottleneck(SQLModel, table=True):
    __tablename__ = "workflow_bottlenecks"

    id: Optional[int] = Field(default=None, primary_key=True)
    case_id: int = Field(index=True)
    bottleneck_type: str = Field(max_length=64)  # missing_docs, sla_breach, discrepancy, stall
    severity: str = Field(default="medium", max_length=20)  # low, medium, high, critical
    description: str
    ai_recommendation: Optional[str] = Field(default=None)
    detected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    resolved: bool = Field(default=False)


class AgentActionLog(SQLModel, table=True):
    __tablename__ = "agent_action_logs"

    id: Optional[int] = Field(default=None, primary_key=True)
    case_id: Optional[int] = Field(default=None, index=True)
    agent_name: str = Field(max_length=64)
    action_type: str = Field(max_length=64)
    details: Optional[str] = Field(default=None)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

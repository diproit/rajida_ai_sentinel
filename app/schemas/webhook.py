from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class WebhookEventType(str, Enum):
    STATUS_CHANGED = "STATUS_CHANGED"
    UNRESPONSIVE_PARTY = "UNRESPONSIVE_PARTY"
    SLA_DELAY_WARNING = "SLA_DELAY_WARNING"


class WebhookSeverity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class WebhookCategory(str, Enum):
    VALUER_UNRESPONSIVE = "VALUER_UNRESPONSIVE"
    BROKER_UNRESPONSIVE = "BROKER_UNRESPONSIVE"
    STATUS_TRANSITION = "STATUS_TRANSITION"
    UNDERWRITING_DELAY = "UNDERWRITING_DELAY"
    DRAFT_STAGNATION = "DRAFT_STAGNATION"


class ApplicationData(BaseModel):
    id: str = Field(description="Unique application ID (UUID)")
    application_no: str = Field(description="Human-readable application/case number e.g. MK-88A9C12E")
    status: str = Field(description="Current application workflow status")
    branch_id: Optional[str] = Field(default=None, description="Originating branch UUID")
    branch_name: Optional[str] = Field(default=None, description="Branch name e.g. Kandy Branch")
    created_at: datetime
    updated_at: datetime


class AssignedPartyData(BaseModel):
    role: str = Field(description="Role: VALUER, INSURANCE_BROKER, FIELD_OFFICER, BRANCH_MANAGER")
    user_id: str = Field(description="Assigned user ID")
    name: str = Field(description="Assigned party name")
    phone: str = Field(description="Contact phone number")
    company_name: Optional[str] = Field(default=None, description="Company or firm name")
    assigned_at: Optional[datetime] = Field(default=None, description="Timestamp assigned")


class WebhookMetrics(BaseModel):
    elapsed_seconds: float = Field(default=0.0, description="Elapsed seconds in current stage/task")
    sla_threshold_seconds: float = Field(default=0.0, description="Allowed SLA seconds threshold")
    delay_seconds: float = Field(default=0.0, description="Seconds delayed beyond SLA")


class WebhookDetails(BaseModel):
    previous_status: Optional[str] = Field(default=None, description="Previous status before transition")
    new_status: Optional[str] = Field(default=None, description="New status after transition")
    trigger_actor: Optional[str] = Field(default=None, description="User or system initiating event")
    message: Optional[str] = Field(default=None, description="Descriptive context or SLA alert message")


class DigiValuerWebhookPayload(BaseModel):
    event_id: str = Field(description="Unique webhook delivery event UUID for idempotency")
    timestamp: datetime = Field(description="Event creation timestamp in ISO UTC")
    source_system: str = Field(default="mekamu_mowheel", description="Source platform identifier")
    environment: str = Field(default="production", description="Environment: production, staging, dev")
    event_type: str = Field(description="STATUS_CHANGED, UNRESPONSIVE_PARTY, SLA_DELAY_WARNING")
    severity: str = Field(default=WebhookSeverity.MEDIUM.value, description="CRITICAL, HIGH, MEDIUM, LOW")
    category: str = Field(default=WebhookCategory.STATUS_TRANSITION.value, description="Event classification")
    application: ApplicationData
    assigned_party: AssignedPartyData
    metrics: WebhookMetrics = Field(default_factory=WebhookMetrics)
    details: WebhookDetails = Field(default_factory=WebhookDetails)


class WebhookResponse(BaseModel):
    status: str
    event_id: str
    message: str
    task_id: Optional[str] = None
    action_taken: Optional[str] = None

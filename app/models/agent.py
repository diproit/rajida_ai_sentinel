from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from sqlmodel import Field, SQLModel


class RecipientRole(str, Enum):
    CASE_OWNER = "Case Owner"
    EXTERNAL_STAKEHOLDER = "External Stakeholder"


class InterventionStatus(str, Enum):
    DRAFTED = "DRAFTED"
    APPROVED = "APPROVED"
    SENT = "SENT"
    FAILED = "FAILED"


class CommunicationChannel(str, Enum):
    EMAIL = "EMAIL"
    SMS = "SMS"
    SLACK = "SLACK"
    WEBHOOK = "WEBHOOK"
    PORTAL = "PORTAL"


class CaseSLAConfig(SQLModel, table=True):
    __tablename__ = "case_sla_configs"

    id: Optional[int] = Field(default=None, primary_key=True)
    stage_id: str = Field(
        index=True,
        unique=True,
        max_length=64,
        description="Unique identifier for valuation stage (e.g., document_verification)",
    )
    stage_name: str = Field(
        max_length=128,
        description="Human-readable display name for valuation stage",
    )
    target_duration_hours: float = Field(
        description="Target completion duration in hours",
    )
    critical_warning_threshold_hours: float = Field(
        description="Critical warning threshold hours before SLA breach",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )


class EscalationRule(SQLModel, table=True):
    __tablename__ = "escalation_rules"

    id: Optional[int] = Field(default=None, primary_key=True)
    stage_id: str = Field(
        index=True,
        max_length=64,
        description="Valuation stage associated with this escalation rule",
    )
    max_reminders: int = Field(
        default=3,
        description="Maximum reminders allowed before escalating",
    )
    escalation_target_role: str = Field(
        max_length=100,
        description="Role or team targeted for escalation (e.g., Chief Appraiser, Team Lead)",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )


class AgentIntervention(SQLModel, table=True):
    __tablename__ = "agent_interventions"

    id: Optional[int] = Field(default=None, primary_key=True)
    case_id: str = Field(
        index=True,
        max_length=64,
        description="Valuation case identifier (e.g. DV-2024-001)",
    )
    recipient_id: str = Field(
        max_length=128,
        description="Recipient identifier (email address or user ID)",
    )
    recipient_role: str = Field(
        default=RecipientRole.CASE_OWNER.value,
        max_length=64,
        description="Recipient role: 'Case Owner' or 'External Stakeholder'",
    )
    stage: str = Field(
        index=True,
        max_length=64,
        description="Valuation stage during which the intervention occurred",
    )
    reminder_count: int = Field(
        default=1,
        description="Count of reminders dispatched for this stage",
    )
    drafted_message: str = Field(
        description="AI-drafted message or notification content",
    )
    channel: str = Field(
        default=CommunicationChannel.EMAIL.value,
        max_length=32,
        description="Delivery channel: EMAIL, SMS, SLACK, PORTAL",
    )
    status: str = Field(
        default=InterventionStatus.DRAFTED.value,
        max_length=32,
        index=True,
        description="Status: DRAFTED, APPROVED, SENT, FAILED",
    )
    sent_at: Optional[datetime] = Field(
        default=None,
        description="Timestamp when message was successfully sent",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )


class AgentMetrics(SQLModel, table=True):
    __tablename__ = "agent_metrics"

    id: Optional[int] = Field(default=None, primary_key=True)
    case_id: str = Field(
        index=True,
        max_length=64,
        description="Valuation case identifier",
    )
    duration_saved: float = Field(
        default=0.0,
        description="Estimated duration saved in hours by the agent intervention",
    )
    response_time_hours: float = Field(
        default=0.0,
        description="Time taken by the recipient to respond after intervention",
    )
    completed_after_reminder: bool = Field(
        default=False,
        description="Flag indicating if stage was completed following the reminder",
    )
    recorded_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )

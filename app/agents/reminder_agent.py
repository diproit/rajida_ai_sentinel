from datetime import datetime, timezone
from enum import Enum
import logging
from typing import Any, List, Optional, Tuple, Union
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field
from sqlmodel.ext.asyncio.session import AsyncSession

from app.agents.base import get_llm
from app.core.config import get_settings
from app.models.agent import (
    AgentIntervention,
    CaseSLAConfig,
    CommunicationChannel,
    InterventionStatus,
    RecipientRole,
)
from app.services.digivaluer_client import DigiValuerCase
from app.services.sla_evaluator import ActionableOverdueCase

logger = logging.getLogger("agents.reminder")
settings = get_settings()


class ToneLevel(str, Enum):
    GENTLE = "Gentle"
    FIRM = "Firm"
    ESCALATED = "Escalated"


class DraftedReminderOutput(BaseModel):
    """Structured Pydantic schema for AI-generated valuation reminders."""

    subject: str = Field(
        description="Clear, context-specific subject line for the reminder email or notification.",
    )
    body: str = Field(
        description="Full context-aware message body with actionable guidance.",
    )
    tone_level: ToneLevel = Field(
        description="The tone urgency: Gentle, Firm, or Escalated.",
    )
    suggested_channel: CommunicationChannel = Field(
        default=CommunicationChannel.EMAIL,
        description="Recommended channel for delivery: EMAIL, SLACK, SMS, or PORTAL.",
    )


# ------------------------------------------------------------------------------
# Prompt Templates
# ------------------------------------------------------------------------------

INTERNAL_CASE_OWNER_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        "You are DigiValuer Sentinel AI, an autonomous workflow optimization agent. "
        "Your objective is to unblock stalled valuation workflows by drafting clear, professional, "
        "and actionable internal reminders to Case Owners and Appraisers. "
        "You must output structured JSON conforming to the requested schema.",
    ),
    (
        "human",
        """Please draft an internal reminder for the following stalled valuation case:

- Case ID: {case_id}
- Property Address: {property_address}
- Valuation Stage: {stage_name} ({stage_id})
- Time Elapsed in Stage: {elapsed_hours:.1f} hours
- Stage SLA Target: {target_duration_hours:.1f} hours (Warning threshold: {critical_warning_threshold_hours:.1f} hours)
- Reminder Sequence: Reminder #{reminder_count}
- Tone Urgency: {tone_level}
- Target Recipient: {recipient_name} ({recipient_email}, Role: {recipient_role})
- Specific Missing Items / Tasks: {missing_items}
- Direct Workflow Review Link: {workflow_url}

Instructions:
1. Calibrate the tone precisely to '{tone_level}':
   - Gentle (1st reminder): Polite, helpful check-in to see if assistance or additional resources are needed.
   - Firm (2nd reminder): Direct and professional emphasis on the SLA deadline and operational risk.
   - Escalated (3rd+ reminder): High-urgency alert notifying of SLA violation and executive/supervisory escalation.
2. Explicitly cite the specific missing items: {missing_items}.
3. Always include the direct link {workflow_url} for one-click action.
4. Select the most effective communication channel (EMAIL or SLACK for internal staff).
""",
    ),
])

EXTERNAL_STAKEHOLDER_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        "You are the DigiValuer Customer Support AI Assistant. "
        "Your objective is to help borrowers, property owners, and realtors by drafting courteous, "
        "accessible, and crystal-clear messages requesting necessary documentation or property access. "
        "Never use internal technical jargon like 'SLA breach', 'pipeline metrics', or 'stage IDs'. "
        "You must output structured JSON conforming to the requested schema.",
    ),
    (
        "human",
        """Please draft a consumer-facing message for the following property valuation:

- Property Address: {property_address}
- Stakeholder Name: {recipient_name} (Role: {recipient_role})
- Valuation Stage: {stage_name}
- Pending Requirement: {missing_items}
- Reminder Sequence: Reminder #{reminder_count}
- Tone Urgency: {tone_level}
- Secure Portal Link: {workflow_url}

Instructions:
1. Use courteous, reassuring, and completely non-technical language.
2. Clearly describe what is needed from them: {missing_items}.
3. Explain that providing this promptly ensures their valuation report finishes on schedule.
4. Calibrate tone to '{tone_level}':
   - Gentle: Friendly reminder and check-in.
   - Firm: Polite reminder that the valuation process is waiting on their input.
   - Escalated: Urgent notice that report generation is currently paused until this item is received.
5. Provide the secure link {workflow_url} and invite them to reply if they have any questions.
6. Suggest the most effective channel (EMAIL, SMS, or PORTAL).
""",
    ),
])


def determine_tone_level(reminder_count: int, should_escalate: bool = False) -> ToneLevel:
    """Determine the reminder urgency tone based on reminder sequence count and escalation status."""
    if should_escalate or reminder_count >= 3:
        return ToneLevel.ESCALATED
    if reminder_count == 2:
        return ToneLevel.FIRM
    return ToneLevel.GENTLE


def _generate_fallback_draft(
    case_id: str,
    property_address: str,
    stage_name: str,
    elapsed_hours: float,
    target_hours: float,
    reminder_count: int,
    tone_level: ToneLevel,
    is_external: bool,
    recipient_name: str,
    recipient_role: str,
    missing_items: str,
    workflow_url: str,
) -> DraftedReminderOutput:
    """Generate high-fidelity structured reminder draft when external LLM API is unavailable."""
    if is_external:
        channel = CommunicationChannel.SMS if tone_level == ToneLevel.ESCALATED else CommunicationChannel.EMAIL
        if tone_level == ToneLevel.GENTLE:
            subject = f"Friendly update regarding your property valuation - {property_address}"
            body = (
                f"Hello {recipient_name},\n\n"
                f"We hope you are doing well! We are currently working on the valuation report for {property_address}. "
                f"To keep the process moving forward smoothly, we kindly request the following item: {missing_items}.\n\n"
                f"You can quickly upload this or confirm details through our secure portal:\n{workflow_url}\n\n"
                f"Please let us know if you have any questions. Thank you for your time!\n\n"
                f"Best regards,\nDigiValuer Support Team"
            )
        elif tone_level == ToneLevel.FIRM:
            subject = f"Action needed: Missing information for valuation of {property_address}"
            body = (
                f"Dear {recipient_name},\n\n"
                f"This is a follow-up regarding the valuation for {property_address}. "
                f"Our appraisal team is currently waiting on: {missing_items}.\n\n"
                f"To prevent any further delays with your report, please submit this information as soon as possible via the secure link below:\n"
                f"{workflow_url}\n\n"
                f"Thank you for your prompt assistance.\n\n"
                f"Sincerely,\nDigiValuer Valuation Team"
            )
        else:
            subject = f"Urgent: Valuation paused for {property_address} - action required"
            body = (
                f"Dear {recipient_name},\n\n"
                f"Your valuation for {property_address} is currently paused pending required information: {missing_items}.\n\n"
                f"Please access the link below immediately to provide this item so our team can resume and finalize your report:\n"
                f"{workflow_url}\n\n"
                f"If you need immediate assistance, please reply directly to this message.\n\n"
                f"DigiValuer Priority Support"
            )
    else:
        channel = CommunicationChannel.SLACK if tone_level == ToneLevel.ESCALATED else CommunicationChannel.EMAIL
        if tone_level == ToneLevel.GENTLE:
            subject = f"[Reminder #{reminder_count}] {stage_name} pending for {case_id} ({property_address})"
            body = (
                f"Hi {recipient_name},\n\n"
                f"This is a gentle check-in regarding case {case_id} ({property_address}), which has been in "
                f"the '{stage_name}' stage for {elapsed_hours:.1f} hours (SLA target: {target_hours:.1f}h).\n\n"
                f"Pending item(s): {missing_items}.\n\n"
                f"You can review and complete this case here:\n{workflow_url}\n\n"
                f"Let us know if you need assistance from the review desk.\n\n"
                f"— DigiValuer Sentinel"
            )
        elif tone_level == ToneLevel.FIRM:
            subject = f"[SLA Warning - Reminder #{reminder_count}] Action required: {case_id} - {stage_name}"
            body = (
                f"Attention {recipient_name},\n\n"
                f"Case {case_id} ({property_address}) has exceeded expected timeline parameters in '{stage_name}' "
                f"at {elapsed_hours:.1f} hours (target: {target_hours:.1f}h).\n\n"
                f"Outstanding requirements: {missing_items}.\n\n"
                f"Please prioritize completion to avoid a formal SLA breach:\n{workflow_url}\n\n"
                f"— DigiValuer Sentinel Operations"
            )
        else:
            subject = f"[CRITICAL SLA BREACH #{reminder_count}] Escalated review: {case_id} ({property_address})"
            body = (
                f"PRIORITY ALERT: Case {case_id} ({property_address}) is in critical SLA breach in stage '{stage_name}' "
                f"({elapsed_hours:.1f}h vs target {target_hours:.1f}h). Recipient: {recipient_role} ({recipient_name}).\n\n"
                f"Unresolved bottleneck: {missing_items}.\n\n"
                f"Immediate intervention required via workflow portal:\n{workflow_url}\n\n"
                f"— DigiValuer Sentinel Escalation Desk"
            )

    return DraftedReminderOutput(
        subject=subject,
        body=body,
        tone_level=tone_level,
        suggested_channel=channel,
    )


async def generate_case_reminder(
    case_data: Union[DigiValuerCase, dict],
    sla_data: Union[ActionableOverdueCase, CaseSLAConfig, dict],
    previous_interventions: Optional[List[AgentIntervention]] = None,
    missing_items: Optional[Union[str, List[str]]] = None,
    is_external: bool = False,
    target_recipient: Optional[Tuple[str, str, str]] = None,  # (id/email, name, role)
    session: Optional[AsyncSession] = None,
) -> Tuple[DraftedReminderOutput, Optional[AgentIntervention]]:
    """Generate a context-aware valuation reminder using Google Gemini structured output

    and optionally save the drafted record to the database with status 'DRAFTED'.
    """
    interventions = previous_interventions or []
    sent_or_approved = [
        inv for inv in interventions
        if inv.status in (InterventionStatus.SENT.value, InterventionStatus.APPROVED.value)
    ]
    reminder_count = len(sent_or_approved) + 1

    # Extract case attributes
    if isinstance(case_data, DigiValuerCase):
        case_id = case_data.case_id
        property_address = case_data.property_address
        current_stage = case_data.current_stage
        default_email = case_data.assigned_owner.email
        default_name = case_data.assigned_owner.name
        default_role = case_data.assigned_owner.role
    else:
        case_id = case_data.get("case_id", "DV-UNKNOWN")
        property_address = case_data.get("property_address", "Unknown Property")
        current_stage = case_data.get("current_stage", "document_verification")
        owner_dict = case_data.get("assigned_owner", {})
        default_email = owner_dict.get("email", "owner@example.com")
        default_name = owner_dict.get("name", "Case Owner")
        default_role = owner_dict.get("role", RecipientRole.CASE_OWNER.value)

    # Extract SLA attributes
    if isinstance(sla_data, ActionableOverdueCase):
        stage_name = sla_data.stage_name
        stage_id = sla_data.stage_id
        elapsed_hours = sla_data.elapsed_hours
        target_hours = sla_data.target_duration_hours
        warning_hours = sla_data.critical_warning_threshold_hours
        should_escalate = sla_data.should_escalate
    elif isinstance(sla_data, CaseSLAConfig):
        stage_name = sla_data.stage_name
        stage_id = sla_data.stage_id
        elapsed_hours = 0.0
        target_hours = sla_data.target_duration_hours
        warning_hours = sla_data.critical_warning_threshold_hours
        should_escalate = False
    else:
        stage_name = sla_data.get("stage_name", current_stage)
        stage_id = sla_data.get("stage_id", current_stage)
        elapsed_hours = float(sla_data.get("elapsed_hours", 0.0))
        target_hours = float(sla_data.get("target_duration_hours", 24.0))
        warning_hours = float(sla_data.get("critical_warning_threshold_hours", 18.0))
        should_escalate = bool(sla_data.get("should_escalate", False))

    tone_level = determine_tone_level(reminder_count, should_escalate)

    # Recipient resolution
    if target_recipient:
        recipient_id, recipient_name, recipient_role = target_recipient
    else:
        recipient_id, recipient_name, recipient_role = default_email, default_name, default_role

    # Missing items normalization
    if missing_items is None:
        missing_text = "Updated valuation documentation and pending workflow approval"
    elif isinstance(missing_items, list):
        missing_text = ", ".join(missing_items) if missing_items else "Required valuation uploads"
    else:
        missing_text = str(missing_items)

    workflow_url = f"https://portal.digivaluer.example.com/cases/{case_id}/workflow"

    prompt_variables = {
        "case_id": case_id,
        "property_address": property_address,
        "stage_name": stage_name,
        "stage_id": stage_id,
        "elapsed_hours": elapsed_hours,
        "target_duration_hours": target_hours,
        "critical_warning_threshold_hours": warning_hours,
        "reminder_count": reminder_count,
        "tone_level": tone_level.value,
        "recipient_name": recipient_name,
        "recipient_email": recipient_id,
        "recipient_role": recipient_role,
        "missing_items": missing_text,
        "workflow_url": workflow_url,
    }

    prompt_template = EXTERNAL_STAKEHOLDER_PROMPT if is_external else INTERNAL_CASE_OWNER_PROMPT

    draft: DraftedReminderOutput
    try:
        if not settings.GEMINI_API_KEY or "mock" in settings.GEMINI_API_KEY.lower():
            raise ValueError("GEMINI_API_KEY is not configured or is in mock mode.")

        llm = get_llm()
        structured_llm = llm.with_structured_output(DraftedReminderOutput)
        formatted_prompt = await prompt_template.ainvoke(prompt_variables)
        draft = await structured_llm.ainvoke(formatted_prompt)
        logger.info("Successfully generated reminder draft using Gemini model for case %s", case_id)
    except Exception as exc:
        logger.info("Generating fallback reminder draft for case %s (Reason: %s)", case_id, exc)
        draft = _generate_fallback_draft(
            case_id=case_id,
            property_address=property_address,
            stage_name=stage_name,
            elapsed_hours=elapsed_hours,
            target_hours=target_hours,
            reminder_count=reminder_count,
            tone_level=tone_level,
            is_external=is_external,
            recipient_name=recipient_name,
            recipient_role=recipient_role,
            missing_items=missing_text,
            workflow_url=workflow_url,
        )

    # Save to agent_interventions database if session is provided
    intervention_record: Optional[AgentIntervention] = None
    if session is not None:
        channel_val = (
            draft.suggested_channel.value
            if hasattr(draft.suggested_channel, "value")
            else str(draft.suggested_channel)
        )
        full_message = f"Subject: {draft.subject}\n\n{draft.body}"

        intervention_record = AgentIntervention(
            case_id=case_id,
            recipient_id=recipient_id,
            recipient_role=recipient_role,
            stage=stage_id,
            reminder_count=reminder_count,
            drafted_message=full_message,
            channel=channel_val,
            status=InterventionStatus.DRAFTED.value,
            sent_at=None,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        session.add(intervention_record)
        await session.commit()
        await session.refresh(intervention_record)
        logger.info(
            "Saved drafted intervention record id=%s for case %s (status=DRAFTED)",
            intervention_record.id,
            case_id,
        )

    return draft, intervention_record

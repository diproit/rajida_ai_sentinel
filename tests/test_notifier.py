import pytest
from app.models.agent import CommunicationChannel
from app.services.notifier import (
    EmailDispatcher,
    InAppWebhookDispatcher,
    NotificationDispatcher,
    SMSWhatsAppDispatcher,
)


@pytest.mark.asyncio
async def test_email_dispatcher():
    dispatcher = EmailDispatcher()
    res = await dispatcher.send_email(
        to_email="appraiser@example.com",
        subject="Action Required: Valuation Review",
        body="Please review missing photos for Case #101.",
    )

    assert res["success"] is True
    assert res["channel"] == CommunicationChannel.EMAIL.value
    assert res["provider"] == "sendgrid_smtp"
    assert res["recipient"] == "appraiser@example.com"
    assert res["message_id"].startswith("msg_email_")


@pytest.mark.asyncio
async def test_sms_whatsapp_dispatcher():
    dispatcher = SMSWhatsAppDispatcher()

    # SMS test
    sms_res = await dispatcher.send_sms(
        to_phone="+15551234567",
        message="DigiValuer: Please confirm your inspection appointment.",
    )
    assert sms_res["success"] is True
    assert sms_res["channel"] == CommunicationChannel.SMS.value
    assert sms_res["provider"] == "twilio_sms"
    assert sms_res["message_id"].startswith("SM")

    # WhatsApp test
    wa_res = await dispatcher.send_whatsapp(
        to_phone="+15551234567",
        message="DigiValuer: Inspection reminder.",
    )
    assert wa_res["success"] is True
    assert wa_res["channel"] == "WHATSAPP"
    assert wa_res["provider"] == "twilio_whatsapp"
    assert wa_res["message_id"].startswith("WA")


@pytest.mark.asyncio
async def test_in_app_webhook_dispatcher():
    dispatcher = InAppWebhookDispatcher()
    res = await dispatcher.send_in_app_notification(
        case_id="DV-CASE-WEBHOOK-01",
        recipient_id="usr_reviewer_01",
        title="Escalated Case Warning",
        message="Case #DV-CASE-WEBHOOK-01 requires immediate senior appraisal review.",
        payload={"stage": "final_assessment", "priority": "high"},
    )

    assert res["success"] is True
    assert res["channel"] == CommunicationChannel.PORTAL.value
    assert res["provider"] == "digivaluer_webhook"
    assert res["case_id"] == "DV-CASE-WEBHOOK-01"
    assert res["event_id"].startswith("evt_")


@pytest.mark.asyncio
async def test_unified_notification_dispatcher():
    unified = NotificationDispatcher()

    # Dispatch to EMAIL
    email_out = await unified.dispatch(
        channel=CommunicationChannel.EMAIL,
        recipient_id="reviewer@example.com",
        subject="Case Notification",
        message="Notification text",
        case_id="DV-CASE-1",
    )
    assert email_out["provider"] == "sendgrid_smtp"

    # Dispatch to SMS
    sms_out = await unified.dispatch(
        channel=CommunicationChannel.SMS,
        recipient_id="+15559876543",
        subject="SMS Notification",
        message="SMS text",
        case_id="DV-CASE-2",
    )
    assert sms_out["provider"] == "twilio_sms"

    # Dispatch to PORTAL / WEBHOOK
    portal_out = await unified.dispatch(
        channel=CommunicationChannel.PORTAL,
        recipient_id="user_portal_1",
        subject="Portal Notice",
        message="In-app notification text",
        case_id="DV-CASE-3",
    )
    assert portal_out["provider"] == "digivaluer_webhook"

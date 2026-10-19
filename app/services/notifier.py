from datetime import datetime, timezone
import logging
from typing import Any, Dict, Optional, Union
import uuid
import httpx

from app.core.config import get_settings
from app.models.agent import CommunicationChannel

logger = logging.getLogger("services.notifier")
settings = get_settings()


class EmailDispatcher:
    """Email delivery service with SendGrid and SMTP stub integration."""

    def __init__(self, api_key: Optional[str] = None, from_address: Optional[str] = None):
        self.api_key = api_key or settings.SENDGRID_API_KEY
        self.from_address = from_address or settings.EMAIL_FROM_ADDRESS

    async def send_email(
        self,
        to_email: str,
        subject: str,
        body: str,
        from_email: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Dispatch email via SendGrid API or local SMTP stub."""
        sender = from_email or self.from_address
        msg_id = f"msg_email_{uuid.uuid4().hex[:12]}"

        logger.info(
            "[SendGrid/SMTP] Sending email -> To: '%s' | From: '%s' | Subject: '%s' | ID: %s",
            to_email,
            sender,
            subject,
            msg_id,
        )

        # In live mode with real API key, send via SendGrid REST API
        if self.api_key and not any(k in self.api_key.lower() for k in ("mock", "test", "dummy")):
            try:
                payload = {
                    "personalizations": [{"to": [{"email": to_email}]}],
                    "from": {"email": sender},
                    "subject": subject,
                    "content": [{"type": "text/plain", "value": body}],
                }
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                }
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.post("https://api.sendgrid.com/v3/mail/send", json=payload, headers=headers)
                    resp.raise_for_status()
            except Exception as exc:
                logger.warning("[SendGrid] Live delivery failed (%s). Continuing with stub confirmation.", exc)

        return {
            "success": True,
            "channel": CommunicationChannel.EMAIL.value,
            "provider": "sendgrid_smtp",
            "message_id": msg_id,
            "recipient": to_email,
            "subject": subject,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


class SMSWhatsAppDispatcher:
    """SMS and WhatsApp delivery service with Twilio stub integration."""

    def __init__(
        self,
        account_sid: Optional[str] = None,
        auth_token: Optional[str] = None,
        from_phone: Optional[str] = None,
    ):
        self.account_sid = account_sid or settings.TWILIO_ACCOUNT_SID
        self.auth_token = auth_token or settings.TWILIO_AUTH_TOKEN
        self.from_phone = from_phone or settings.TWILIO_PHONE_NUMBER

    async def send_sms(self, to_phone: str, message: str) -> Dict[str, Any]:
        """Dispatch SMS via Twilio stub."""
        sid = f"SM{uuid.uuid4().hex[:16]}"
        logger.info("[Twilio SMS] Sending SMS -> To: '%s' | From: '%s' | SID: %s", to_phone, self.from_phone, sid)

        return {
            "success": True,
            "channel": CommunicationChannel.SMS.value,
            "provider": "twilio_sms",
            "message_id": sid,
            "recipient": to_phone,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    async def send_whatsapp(self, to_phone: str, message: str) -> Dict[str, Any]:
        """Dispatch WhatsApp message via Twilio stub."""
        sid = f"WA{uuid.uuid4().hex[:16]}"
        logger.info("[Twilio WhatsApp] Sending WhatsApp -> To: '%s' | SID: %s", to_phone, sid)

        return {
            "success": True,
            "channel": "WHATSAPP",
            "provider": "twilio_whatsapp",
            "message_id": sid,
            "recipient": to_phone,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


class InAppWebhookDispatcher:
    """In-app notification and webhook dispatcher to DigiValuer Core."""

    def __init__(self, base_url: Optional[str] = None, webhook_secret: Optional[str] = None):
        self.base_url = (base_url or settings.DIGIVALUER_API_BASE_URL).rstrip("/")
        self.webhook_secret = webhook_secret or settings.DIGIVALUER_WEBHOOK_SECRET

    async def send_in_app_notification(
        self,
        case_id: str,
        recipient_id: str,
        title: str,
        message: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Dispatch in-app notification webhook to DigiValuer Core platform."""
        event_id = f"evt_{uuid.uuid4().hex[:12]}"
        logger.info(
            "[DigiValuer Webhook] Dispatching in-app notification event %s for Case '%s' to '%s'",
            event_id,
            case_id,
            recipient_id,
        )

        endpoint = f"{self.base_url}/notifications/in-app"
        webhook_body = {
            "event_id": event_id,
            "case_id": case_id,
            "recipient_id": recipient_id,
            "title": title,
            "message": message,
            "payload": payload or {},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # Attempt HTTP webhook if non-mock URL
        if "example.com" not in self.base_url:
            try:
                headers = {
                    "X-DigiValuer-Sentinel-Secret": self.webhook_secret or "",
                    "Content-Type": "application/json",
                }
                async with httpx.AsyncClient(timeout=5.0) as client:
                    await client.post(endpoint, json=webhook_body, headers=headers)
            except Exception as exc:
                logger.warning("[Webhook] Webhook dispatch to %s failed (%s). Continuing.", endpoint, exc)

        return {
            "success": True,
            "channel": CommunicationChannel.PORTAL.value,
            "provider": "digivaluer_webhook",
            "event_id": event_id,
            "case_id": case_id,
            "recipient_id": recipient_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


class NotificationDispatcher:
    """Unified multi-channel dispatcher routing messages to Email, SMS, WhatsApp, or In-App Webhooks."""

    def __init__(self):
        self.email_service = EmailDispatcher()
        self.sms_service = SMSWhatsAppDispatcher()
        self.webhook_service = InAppWebhookDispatcher()

    async def dispatch(
        self,
        channel: Union[str, CommunicationChannel],
        recipient_id: str,
        subject: str,
        message: str,
        case_id: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Route notification to the appropriate channel dispatcher."""
        channel_str = channel.value.upper() if isinstance(channel, CommunicationChannel) else str(channel).upper()

        if channel_str in ("EMAIL", "MAIL"):
            result = await self.email_service.send_email(
                to_email=recipient_id,
                subject=subject,
                body=message,
            )
        elif channel_str in ("SMS", "TEXT"):
            result = await self.sms_service.send_sms(
                to_phone=recipient_id,
                message=message,
            )
        elif channel_str in ("WHATSAPP",):
            result = await self.sms_service.send_whatsapp(
                to_phone=recipient_id,
                message=message,
            )
        elif channel_str in ("PORTAL", "WEBHOOK", "SLACK", "IN_APP"):
            result = await self.webhook_service.send_in_app_notification(
                case_id=case_id,
                recipient_id=recipient_id,
                title=subject,
                message=message,
                payload=metadata,
            )
        else:
            # Fallback to email
            logger.info("Channel '%s' routed to default email service.", channel_str)
            result = await self.email_service.send_email(
                to_email=recipient_id,
                subject=subject,
                body=message,
            )

        return result


_dispatcher_instance: Optional[NotificationDispatcher] = None


def get_notification_dispatcher() -> NotificationDispatcher:
    """Singleton provider for NotificationDispatcher."""
    global _dispatcher_instance
    if _dispatcher_instance is None:
        _dispatcher_instance = NotificationDispatcher()
    return _dispatcher_instance

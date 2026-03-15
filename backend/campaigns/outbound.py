from __future__ import annotations

import asyncio
import logging
from typing import Optional

from twilio.rest import Client as TwilioClient

from config import settings

logger = logging.getLogger(__name__)


def _build_twiml(ws_url: str, from_phone: str, campaign: bool = True) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Connect>
        <Stream url="{ws_url}">
            <Parameter name="from" value="{from_phone}"/>
            <Parameter name="campaign" value="{'true' if campaign else 'false'}"/>
        </Stream>
    </Connect>
</Response>"""


class OutboundCallService:
    """Initiates outbound Twilio calls for appointment reminders and campaigns."""

    def __init__(self) -> None:
        self._client = TwilioClient(
            settings.TWILIO_ACCOUNT_SID,
            settings.TWILIO_AUTH_TOKEN,
        )
        self._from_number = settings.TWILIO_PHONE_NUMBER

    def _get_twiml_url(self) -> str:
        """API_BASE_URL env var or derive from config extra fields."""
        base: str = settings.API_BASE_URL
        if not base:
            raise RuntimeError(
                "API_BASE_URL not set. Add it to .env so Twilio can reach /api/twilio/voice."
            )
        return base.rstrip("/") + "/api/twilio/voice"

    def _place_call_sync(self, to_phone: str, twiml_url: str) -> Optional[str]:
        """Blocking Twilio REST call; runs in a thread via asyncio.to_thread."""
        try:
            call = self._client.calls.create(
                to=to_phone,
                from_=self._from_number,
                url=twiml_url,
                method="POST",
            )
            logger.info("[outbound] call placed to=%s sid=%s", to_phone, call.sid)
            return call.sid
        except Exception as exc:
            logger.error("[outbound] call failed to=%s: %s", to_phone, exc)
            return None

    async def make_call(
        self,
        *,
        to_phone: str,
        patient_id: int,
        appointment_id: int,
        language: str = "en",
    ) -> Optional[str]:
        """Initiate an outbound call asynchronously (Twilio REST runs in thread pool)."""
        twiml_url = self._get_twiml_url()
        call_sid = await asyncio.to_thread(
            self._place_call_sync, to_phone, twiml_url
        )
        return call_sid


outbound_call_service = OutboundCallService()

from __future__ import annotations

import asyncio
import logging
import ssl
from datetime import datetime, timedelta, timezone

from celery import Celery
from celery.schedules import crontab
from sqlalchemy import select

from config import settings

logger = logging.getLogger(__name__)

_SSL_OPTS = {"ssl_cert_reqs": ssl.CERT_NONE}

celery_app = Celery(
    "2careai",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    broker_use_ssl=_SSL_OPTS,
    redis_backend_use_ssl=_SSL_OPTS,
)

celery_app.conf.beat_schedule = {
    "schedule-reminders-hourly": {
        "task": "campaigns.tasks.schedule_reminders",
        "schedule": crontab(minute=0),
    },
}


def _run(coro):
    """Run an async coroutine from a sync Celery task context."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(name="campaigns.tasks.send_reminder", bind=True, max_retries=3)
def send_reminder(self, patient_id: int, appointment_id: int, language: str = "en"):
    """
    Initiate an outbound reminder call for a specific appointment.
    Logs the attempt in CampaignLog. Retries up to 3 times on failure.
    """
    async def _inner():
        from database import _SessionFactory
        from models import Appointment, CampaignLog, Patient
        from campaigns.outbound import outbound_call_service

        async with _SessionFactory() as db:
            # Fetch appointment + patient
            appt_result = await db.execute(
                select(Appointment).where(Appointment.id == appointment_id)
            )
            appt = appt_result.scalar_one_or_none()
            if appt is None:
                logger.warning("[reminder] appointment %d not found", appointment_id)
                return

            pat_result = await db.execute(
                select(Patient).where(Patient.id == patient_id)
            )
            patient = pat_result.scalar_one_or_none()
            if patient is None:
                logger.warning("[reminder] patient %d not found", patient_id)
                return

            # Place the call
            call_sid = await outbound_call_service.make_call(
                to_phone=patient.phone,
                patient_id=patient_id,
                appointment_id=appointment_id,
                language=language,
            )

            outcome = "pending" if call_sid else "no_answer"

            # Log in CampaignLog
            log = CampaignLog(
                patient_id=patient_id,
                campaign_type="appointment_reminder",
                outcome=outcome,
                call_sid=call_sid,
            )
            db.add(log)
            await db.commit()

            logger.info(
                "[reminder] patient=%d appt=%d sid=%s outcome=%s",
                patient_id, appointment_id, call_sid, outcome,
            )

    try:
        _run(_inner())
    except Exception as exc:
        logger.error("[reminder] failed: %s", exc)
        raise self.retry(exc=exc, countdown=60)


@celery_app.task(name="campaigns.tasks.schedule_reminders")
def schedule_reminders():
    """
    Hourly beat task: find appointments in the next 24 hours without a reminder log
    and enqueue send_reminder for each. Idempotent.
    """
    async def _inner():
        from database import _SessionFactory
        from models import Appointment, AppointmentStatus, CampaignLog, Slot

        async with _SessionFactory() as db:
            now = datetime.now(tz=timezone.utc)
            window_end = now + timedelta(hours=24)

            # Appointments scheduled in the next 24 hours
            result = await db.execute(
                select(Appointment)
                .join(Appointment.slot)
                .where(
                    Appointment.status == AppointmentStatus.SCHEDULED,
                    Slot.start_time >= now,
                    Slot.start_time <= window_end,
                )
            )
            appointments = result.scalars().all()

            queued = 0
            for appt in appointments:
                # Check if already sent a reminder
                log_result = await db.execute(
                    select(CampaignLog).where(
                        CampaignLog.patient_id == appt.patient_id,
                        CampaignLog.campaign_type == "appointment_reminder",
                    )
                )
                existing = log_result.scalar_one_or_none()
                if existing:
                    continue

                # Fetch patient language
                from models import Patient
                pat_result = await db.execute(
                    select(Patient).where(Patient.id == appt.patient_id)
                )
                patient = pat_result.scalar_one_or_none()
                lang = patient.language_preference.value if patient and patient.language_preference else "en"

                send_reminder.delay(appt.patient_id, appt.id, lang)
                queued += 1

            logger.info("[schedule_reminders] queued %d reminder calls", queued)

    _run(_inner())

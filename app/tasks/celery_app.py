from celery import Celery
from celery.signals import worker_ready
from app.core.config import settings

celery = Celery(
    "flysunbird",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.tasks.jobs"],
)

celery.conf.timezone = "Africa/Dar_es_Salaam"

# Run generate_slots once when worker starts so slots appear without start_api or waiting 6h
@worker_ready.connect
def on_worker_ready(sender, **kwargs):
    from app.tasks.jobs import generate_slots
    generate_slots.delay()

celery.conf.beat_schedule = {
    "expire-holds-every-minute": {
        "task": "app.tasks.jobs.expire_holds",
        "schedule": 60.0,
    },
    "generate-slots-every-6-hours": {
        "task": "app.tasks.jobs.generate_slots",
        "schedule": 21600.0,
    },
    "process-email-queue-every-2-minutes": {
        "task": "app.tasks.jobs.process_email_queue",
        "schedule": 120.0,
        "kwargs": {"limit": 50},
    },
}

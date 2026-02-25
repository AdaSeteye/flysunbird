from urllib.parse import urlparse, urlunparse, parse_qs, urlencode

from celery import Celery
from celery.signals import worker_ready
from app.core.config import settings


def _redis_url_for_celery(url: str) -> str:
    """Celery requires ssl_cert_reqs for rediss:// (e.g. Upstash TLS)."""
    if not url or not url.strip().lower().startswith("rediss://"):
        return url
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    if "ssl_cert_reqs" not in qs:
        qs["ssl_cert_reqs"] = ["CERT_NONE"]
        new_query = urlencode(qs, doseq=True)
        return urlunparse(parsed._replace(query=new_query))
    return url


_redis_url = _redis_url_for_celery(settings.REDIS_URL)

celery = Celery(
    "flysunbird",
    broker=_redis_url,
    backend=_redis_url,
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

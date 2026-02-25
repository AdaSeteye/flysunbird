from app.tasks.celery_app import celery
from app.tasks import worker_jobs

@celery.task(name="app.tasks.jobs.expire_holds")
def expire_holds():
    return worker_jobs.expire_holds()

@celery.task(name="app.tasks.jobs.generate_slots")
def generate_slots():
    return worker_jobs.generate_slots()


@celery.task(name="app.tasks.jobs.process_email_queue")
def process_email_queue(limit: int = 50):
    return worker_jobs.process_email_queue(limit=limit)

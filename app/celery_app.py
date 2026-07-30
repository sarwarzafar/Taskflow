"""
The Celery application instance. This is what the FastAPI process imports
to dispatch tasks, and what the `celery worker` command loads to execute them.
Both processes point at the same Redis instance, which is how they talk
to each other — FastAPI never calls worker code directly.
"""
from celery import Celery

from app.config import settings

celery_app = Celery(
    "taskflow",
    broker=settings.redis_url,       # where tasks get queued
    backend=settings.redis_url,      # where results/status get stored
    include=["app.tasks"],           # module(s) containing @celery_app.task defs
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    result_expires=3600,             # stop keeping results around after 1hr
    task_track_started=True,         # lets us report "STARTED" not just PENDING/SUCCESS
    worker_send_task_events=True,    # required for Flower to show live task events
    task_send_sent_event=True,
)

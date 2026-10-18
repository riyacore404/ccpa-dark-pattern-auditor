"""Celery application. Start the worker with:

    .venv/bin/python -m app.workers.run_worker
"""

from celery import Celery

from app.core.config import Settings, get_settings


def create_celery_app(settings: Settings | None = None) -> Celery:
    settings = settings or get_settings()
    app = Celery(
        "ccpa_auditor",
        broker=settings.broker_url,
        backend=settings.result_backend_url,
        include=["app.workers.tasks"],
    )
    app.conf.update(
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        timezone="UTC",
        enable_utc=True,
        task_default_queue="audits",
        # Outcomes are stored in the database, not in Redis.
        task_ignore_result=True,
        # One audit per slot, and an audit is never run twice: a job is
        # acknowledged when it starts, and the session is claimed atomically.
        worker_prefetch_multiplier=1,
        task_acks_late=False,
        task_reject_on_worker_lost=False,
        # Fail fast when Redis is down instead of hanging a web request.
        broker_connection_retry_on_startup=True,
        broker_connection_timeout=3,
        broker_transport_options={"socket_connect_timeout": 3, "socket_timeout": 5},
        task_publish_retry=True,
        task_publish_retry_policy={
            "max_retries": 1,
            "interval_start": 0,
            "interval_step": 0.2,
            "interval_max": 0.5,
        },
    )
    return app


celery_app = create_celery_app()

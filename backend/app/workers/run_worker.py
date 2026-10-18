"""Start the Celery worker with the concurrency set by AUDIT_MAX_CONCURRENT_RUNS.

    .venv/bin/python -m app.workers.run_worker

Threads are used instead of forked processes: they behave the same on macOS
and Linux, and each audit builds its own clients, so nothing is shared.
"""

from app.core.config import Settings, get_settings
from app.workers.celery_app import celery_app


def worker_argv(settings: Settings) -> list[str]:
    return [
        "worker",
        "--pool=threads",
        f"--concurrency={settings.audit_max_concurrent_runs}",
        "--queues=audits",
        "--loglevel=INFO",
    ]


def main() -> None:
    celery_app.worker_main(worker_argv(get_settings()))


if __name__ == "__main__":
    main()

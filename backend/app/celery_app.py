"""Celery 应用配置。"""

from celery import Celery  # type: ignore[import-untyped]

from app.core.config import Settings


def create_celery_app(settings: Settings | None = None) -> Celery:
    resolved = settings or Settings()

    broker = (
        resolved.celery_broker_url.get_secret_value()
        if resolved.celery_broker_url
        else None
    )
    backend = (
        resolved.celery_result_backend.get_secret_value()
        if resolved.celery_result_backend
        else None
    )

    app = Celery(
        "marketmind",
        broker=broker,
        backend=backend,
        include=["app.tasks.user_stats"],
    )
    app.conf.update(
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        enable_utc=True,
        timezone="UTC",
        task_track_started=True,
        task_always_eager=resolved.celery_task_always_eager,
        task_store_eager_result=True,
        result_expires=resolved.celery_result_expires_seconds,
    )

    return app


celery_app = create_celery_app()

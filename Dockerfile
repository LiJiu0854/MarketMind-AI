FROM registry-1.docker.io/library/python:3.12.12-slim-bookworm

WORKDIR /app

COPY pyproject.toml README.md ./
COPY backend ./backend
COPY alembic.ini ./
COPY alembic ./alembic

RUN pip install --no-cache-dir .
RUN useradd --uid 10001 --create-home appuser \
    && mkdir -p /app/data/knowledge \
    && chown -R appuser:appuser /app/data

USER appuser

CMD ["celery", "-A", "app.celery_app:celery_app", "worker", "--loglevel=INFO"]

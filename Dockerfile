FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY backend ./backend

RUN pip install --no-cache-dir .

CMD ["celery", "-A", "app.celery_app:celery_app", "worker", "--loglevel=INFO"]
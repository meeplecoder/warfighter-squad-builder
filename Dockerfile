# Warfighter WWII - Squad Builder — container image (any Docker host; see docs/deploy-docker.md)
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8080 \
    DATABASE_URL=sqlite:////data/warfighter.db

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
RUN useradd --system --no-create-home app \
    && mkdir -p /data \
    && chown -R app:app /app /data \
    && chmod +x docker/entrypoint.sh

VOLUME /data
EXPOSE 8080
ENTRYPOINT ["docker/entrypoint.sh"]

# Local development image — use with docker compose (PostgreSQL + hot reload).
FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# libpq headers/libs for asyncpg; gcc for any native wheel builds
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt pyproject.toml ./
RUN pip install --upgrade pip \
    && pip install -r requirements.txt

COPY src ./src
RUN pip install -e .

EXPOSE 8000

CMD ["uvicorn", "ai_incident_commander.server.main:api", "--host", "0.0.0.0", "--port", "8000"]

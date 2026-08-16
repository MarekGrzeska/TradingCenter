# Multi-stage, same shape as market-data/Dockerfile: uv resolves and builds the venv,
# the runtime stage only ever ships that venv and the source.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

COPY agent ./agent
COPY migrations ./migrations
COPY alembic.ini ./alembic.ini
RUN uv sync --frozen --no-dev

FROM python:3.12-slim-bookworm
WORKDIR /app
COPY --from=builder /app /app
ENV PATH="/app/.venv/bin:$PATH"

# Azure App Service's default expectation for a Linux custom container — matches
# infra/app-service.tf, which sets no WEBSITES_PORT override.
EXPOSE 80

# Migrations run at startup, inside the process — `agent/app.py`'s lifespan, not this
# line. This file used to say the opposite, and the reason it gave was real: a restart
# racing another worker to migrate the same database. What changed is not the risk but
# the answer to it — a Postgres advisory lock (`db.py`), which the racing worker waits on
# instead of duplicating the work. It also used to say the deploy workflow ran the
# migration; it never did, and production stood dark on 16 August because of it.
CMD ["uvicorn", "agent.app:app", "--host", "0.0.0.0", "--port", "80"]

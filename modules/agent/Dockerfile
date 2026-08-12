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

# Migrations are a deliberate, separate step run by the deploy workflow, never implicit
# in container start — same reason as market-data: a restart racing another worker to
# migrate the same database is a failure mode with no upside.
CMD ["uvicorn", "agent.app:app", "--host", "0.0.0.0", "--port", "80"]

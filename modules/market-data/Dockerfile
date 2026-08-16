# Multi-stage: uv resolves and builds the venv, the runtime stage only ever ships
# that venv and the source — no compiler toolchain, no uv binary, no lockfile parsing
# at container start.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

# Dependencies first, from the lockfile alone — this layer only invalidates when
# pyproject.toml or uv.lock change, not on every source edit.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

COPY market_data ./market_data
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

# Migrations (8.6) are a deliberate, separate step — `alembic upgrade head` run by hand
# or by the deploy workflow, never implicit in container start. Running it here would
# mean every restart (and every one of the two workers a bad `worker_count` edit could
# add — see app-service.tf) racing to migrate the same database.
CMD ["uvicorn", "market_data.app:app", "--host", "0.0.0.0", "--port", "80"]

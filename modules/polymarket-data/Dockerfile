# Multi-stage: uv resolves and builds the venv, the runtime stage ships only that venv and the source. **The build
# context is the repository root**, because uv resolves the packages' paths while installing the lock.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder
WORKDIR /app/modules/polymarket-data
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

# Only the packages this module's pyproject.toml names: copying all of `packages/` makes an edit to a package this
# image never installs invalidate every layer below. `test_deploy_workflows.py` holds this list against pyproject.toml.
COPY packages/tc-runtime /app/packages/tc-runtime
COPY packages/tc-mcp-kit /app/packages/tc-mcp-kit
COPY modules/polymarket-data/pyproject.toml modules/polymarket-data/uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

COPY modules/polymarket-data/polymarket_data ./polymarket_data
COPY modules/polymarket-data/migrations ./migrations
COPY modules/polymarket-data/alembic.ini ./alembic.ini
RUN uv sync --frozen --no-dev

FROM python:3.12-slim-bookworm
WORKDIR /app/modules/polymarket-data
COPY --from=builder /app /app
ENV PATH="/app/modules/polymarket-data/.venv/bin:$PATH"

# Azure App Service's default expectation for a Linux custom container.
EXPOSE 80

# Migrations run at startup inside the process, not from this line. Two instances starting together do not race: the
# one that loses waits on a Postgres advisory lock and finds the work done.
CMD ["uvicorn", "polymarket_data.app:app", "--host", "0.0.0.0", "--port", "80"]

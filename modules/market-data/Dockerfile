# Multi-stage: uv resolves and builds the venv, the runtime stage ships only that venv and the source. **The build
# context is the repository root**: uv resolves `tc-runtime`'s path while installing the lock, so it must be inside it.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder
WORKDIR /app/modules/market-data
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

# Dependencies first, from the lockfile alone, and only the packages this module's pyproject.toml names: copying all of
# `packages/` makes an edit to a package this image never installs invalidate every layer below.
COPY packages/tc-runtime /app/packages/tc-runtime
COPY packages/tc-mcp-kit /app/packages/tc-mcp-kit
COPY modules/market-data/pyproject.toml modules/market-data/uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

COPY modules/market-data/market_data ./market_data
COPY modules/market-data/migrations ./migrations
COPY modules/market-data/alembic.ini ./alembic.ini
RUN uv sync --frozen --no-dev

FROM python:3.12-slim-bookworm
WORKDIR /app/modules/market-data
COPY --from=builder /app /app
ENV PATH="/app/modules/market-data/.venv/bin:$PATH"

# Azure App Service's default expectation for a Linux custom container — matches
# infra/app-service.tf, which sets no WEBSITES_PORT override.
EXPOSE 80

# Migrations run at startup inside the process, not from this line: two workers racing to migrate is answered by a
# Postgres advisory lock, so a merge to main leaves production serving with no step in between.
CMD ["uvicorn", "market_data.app:app", "--host", "0.0.0.0", "--port", "80"]

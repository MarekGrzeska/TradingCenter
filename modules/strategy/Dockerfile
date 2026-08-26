# Multi-stage: uv resolves and builds the venv, the runtime stage ships only that venv and the source. **The build
# context is the repository root**, because uv resolves the packages' paths while installing the lock.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder
WORKDIR /app/modules/strategy
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

# Dependencies first, from the lockfile alone, and only the packages this module's pyproject.toml names: copying all
# of `packages/` makes an edit to a package this image never installs invalidate every layer below.
COPY packages/tc-runtime /app/packages/tc-runtime
COPY packages/tc-mcp-kit /app/packages/tc-mcp-kit
COPY modules/strategy/pyproject.toml modules/strategy/uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

COPY modules/strategy/strategy ./strategy
COPY modules/strategy/migrations ./migrations
COPY modules/strategy/alembic.ini ./alembic.ini
RUN uv sync --frozen --no-dev

FROM python:3.12-slim-bookworm
WORKDIR /app/modules/strategy
COPY --from=builder /app /app
ENV PATH="/app/modules/strategy/.venv/bin:$PATH"

# Azure App Service's default expectation for a Linux custom container — matches
# infra/app-service.tf, which sets no WEBSITES_PORT override.
EXPOSE 80

# Migrations run at startup inside the process, not from this line, under an advisory lock so a second worker waits.
# What that buys is the standing rule: a merge to main leaves production serving, with no operator step in between.
CMD ["uvicorn", "strategy.app:app", "--host", "0.0.0.0", "--port", "80"]

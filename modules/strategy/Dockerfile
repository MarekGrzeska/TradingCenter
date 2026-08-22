# Multi-stage: uv resolves and builds the venv, the runtime stage only ever ships that
# venv and the source — no compiler toolchain, no uv binary, no lockfile parsing at
# container start.
#
# **The build context is the repository root, not this directory**, because `tc-runtime`
# and `tc-mcp-kit` are path dependencies: uv resolves those paths while installing the
# lock, so they have to be inside the context. The image mirrors the repository's layout
# for the same reason — `pyproject.toml` names them relative to the repository.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder
WORKDIR /app/modules/strategy
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

# Dependencies first, from the lockfile alone — this layer only invalidates when
# pyproject.toml or uv.lock change, not on every source edit. Only the packages this
# module's pyproject.toml names: copying all of `packages/` would make an edit to a
# package this image never installs invalidate this layer and every one below it.
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

# Migrations run at startup, inside the process — `strategy/app.py`'s lifespan, not this
# line, under a Postgres advisory lock so a second worker waits rather than duplicating
# the work. What that buys is the standing rule: a merge to main leaves production
# serving, with no operator step in between.
CMD ["uvicorn", "strategy.app:app", "--host", "0.0.0.0", "--port", "80"]

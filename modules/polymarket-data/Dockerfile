# Multi-stage: uv resolves and builds the venv, the runtime stage only ever ships that
# venv and the source — no compiler toolchain, no uv binary, no lockfile parsing at
# container start.
#
# **The build context is the repository root, not this directory**, because `tc-runtime`
# and `tc-mcp-kit` are path dependencies and uv resolves them while installing the lock.
# The image mirrors the repository's layout for the same reason — `pyproject.toml` names
# the packages relative to the repository, and a flattened image would have to rewrite
# those paths.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder
WORKDIR /app/modules/polymarket-data
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

# Only the packages this module's pyproject.toml names. Copying all of `packages/` would
# make an edit to a package this image never installs invalidate this layer and every one
# below it. A package added to pyproject.toml but not here fails the build loudly — uv
# cannot resolve a path dependency that is not in the context — and
# `scripts/tests/test_deploy_workflows.py` holds this list against pyproject.toml so the
# failure arrives before a deploy rather than during one.
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

# Migrations run at startup, inside the process — `polymarket_data/app.py`'s lifespan, not
# this line. Two instances starting together do not race: the one that loses waits on a
# Postgres advisory lock and finds the work done.
CMD ["uvicorn", "polymarket_data.app:app", "--host", "0.0.0.0", "--port", "80"]

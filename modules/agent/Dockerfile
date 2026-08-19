# Multi-stage, same shape as market-data/Dockerfile: uv resolves and builds the venv,
# the runtime stage only ever ships that venv and the source.
#
# **The build context is the repository root, not this directory.** It became so when
# `tc-runtime` turned from a copied file into a path dependency: uv resolves that path
# while installing the lock, so the package has to be inside the context. The image
# mirrors the repository's layout for the same reason — `pyproject.toml` names the
# package as `../../packages/tc-runtime`, and a flattened image would have to rewrite
# that path, which is one more place for the two to disagree.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder
WORKDIR /app/modules/agent
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

# The packages before the lock: `uv sync` reads them during resolution, not after.
# Only the ones this module's pyproject.toml names — copying all of `packages/` made
# an edit to a package this image never installs invalidate this layer and every one
# below it. A package added to pyproject.toml but not here fails the build loudly:
# uv cannot resolve a path dependency that is not in the context.
COPY packages/tc-runtime /app/packages/tc-runtime
COPY packages/tc-openai /app/packages/tc-openai
COPY modules/agent/pyproject.toml modules/agent/uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

COPY modules/agent/agent ./agent
COPY modules/agent/migrations ./migrations
COPY modules/agent/alembic.ini ./alembic.ini
RUN uv sync --frozen --no-dev

FROM python:3.12-slim-bookworm
WORKDIR /app/modules/agent
COPY --from=builder /app /app
ENV PATH="/app/modules/agent/.venv/bin:$PATH"

# Azure App Service's default expectation for a Linux custom container — matches
# infra/app-service.tf, which sets no WEBSITES_PORT override.
EXPOSE 80

# Migrations run at startup, inside the process — `agent/app.py`'s lifespan, not this
# line. This file used to say the opposite, and the reason it gave was real: a restart
# racing another worker to migrate the same database. What changed is not the risk but
# the answer to it — a Postgres advisory lock (`tc_runtime/db.py`), which the racing
# worker waits on instead of duplicating the work. It also used to say the deploy
# workflow ran the migration; it never did, and production stood dark on 16 August
# because of it.
CMD ["uvicorn", "agent.app:app", "--host", "0.0.0.0", "--port", "80"]

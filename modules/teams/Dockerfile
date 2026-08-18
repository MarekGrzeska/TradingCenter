# Multi-stage, same shape as agent/Dockerfile and market-data/Dockerfile: uv resolves
# and builds the venv, the runtime stage only ever ships that venv and the source.
#
# **The build context is the repository root, not this directory.** It became so when
# `tc-runtime` turned from a copied file into a path dependency: uv resolves that path
# while installing the lock, so the package has to be inside the context. The image
# mirrors the repository's layout for the same reason — `pyproject.toml` names the
# package relative to the repository, and a flattened image would have to rewrite that
# path, which is one more place for the two to disagree.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder
WORKDIR /app/modules/teams
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

# The package before the lock: `uv sync` reads it during resolution, not after.
COPY packages /app/packages
COPY modules/teams/pyproject.toml modules/teams/uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

COPY modules/teams/teams ./teams
COPY modules/teams/migrations ./migrations
COPY modules/teams/alembic.ini ./alembic.ini
RUN uv sync --frozen --no-dev

FROM python:3.12-slim-bookworm
WORKDIR /app/modules/teams
COPY --from=builder /app /app
ENV PATH="/app/modules/teams/.venv/bin:$PATH"

# Azure App Service's default expectation for a Linux custom container — matches
# infra/app-service.tf, which sets no WEBSITES_PORT override.
EXPOSE 80

# Migrations run at startup, inside the process — `teams/app.py`'s lifespan, not this
# line. See agent/Dockerfile's own comment for the incident that made this the rule
# rather than a convenience: a deploy workflow is not where a database gets migrated.
CMD ["uvicorn", "teams.app:app", "--host", "0.0.0.0", "--port", "80"]

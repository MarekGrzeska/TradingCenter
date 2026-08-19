# Multi-stage: uv resolves and builds the venv, the runtime stage only ever ships
# that venv and the source — no compiler toolchain, no uv binary, no lockfile parsing
# at container start.
#
# **The build context is the repository root, not this directory.** It became so when
# `tc-runtime` turned from a copied file into a path dependency: uv resolves that path
# while installing the lock, so the package has to be inside the context. The image
# mirrors the repository's layout for the same reason — `pyproject.toml` names the
# package relative to the repository, and a flattened image would have to rewrite that
# path, which is one more place for the two to disagree.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder
WORKDIR /app/modules/market-data
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

# Dependencies first, from the lockfile alone — this layer only invalidates when
# pyproject.toml or uv.lock change, not on every source edit.
# The package before the lock: `uv sync` reads it during resolution, not after.
# Only the one this module's pyproject.toml names — copying all of `packages/` made
# an edit to a package this image never installs invalidate this layer and every one
# below it. A package added to pyproject.toml but not here fails the build loudly:
# uv cannot resolve a path dependency that is not in the context.
COPY packages/tc-runtime /app/packages/tc-runtime
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

# Migrations run at startup, inside the process — `market_data/app.py`'s lifespan, not
# this line. This file used to say the opposite, and the reason it gave was real: two
# workers restarting together would race to migrate the same database. What changed is
# not the risk but the answer to it — a Postgres advisory lock (`db.py`), which the
# racing worker waits on instead of duplicating the work. What that bought is in
# `market-data-database-connection`, "Moduł sam doprowadza bazę do rewizji, dla której
# powstał": a merge to main leaves production serving, with no step in between.
CMD ["uvicorn", "market_data.app:app", "--host", "0.0.0.0", "--port", "80"]

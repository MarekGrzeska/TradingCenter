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
WORKDIR /app/modules/workbench
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

# The packages before the lock: `uv sync` reads them during resolution, not after.
# Only the ones this module's pyproject.toml names — copying all of `packages/` made
# an edit to a package this image never installs invalidate this layer and every one
# below it. A package added to pyproject.toml but not here fails the build loudly:
# uv cannot resolve a path dependency that is not in the context.
COPY packages/tc-runtime /app/packages/tc-runtime
COPY packages/tc-openai /app/packages/tc-openai
COPY packages/tc-mcp-kit /app/packages/tc-mcp-kit
COPY modules/workbench/pyproject.toml modules/workbench/uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

# Four packages, and the layering rule between them is `tests/test_layering.py`'s, not
# this file's: `agent` and `teams` never import each other, `teams_tools` reaches `teams`
# only to build an ASGI transport on its routers, and `workbench` is the one place that
# imports all three.
COPY modules/workbench/workbench ./workbench
COPY modules/workbench/agent ./agent
COPY modules/workbench/teams ./teams
COPY modules/workbench/teams_tools ./teams_tools
COPY modules/workbench/migrations ./migrations
RUN uv sync --frozen --no-dev

FROM python:3.12-slim-bookworm
WORKDIR /app/modules/workbench
COPY --from=builder /app /app
ENV PATH="/app/modules/workbench/.venv/bin:$PATH"

# Azure App Service's default expectation for a Linux custom container — matches
# infra/app-service.tf, which sets no WEBSITES_PORT override.
EXPOSE 80

# Both migration chains run at startup, inside the process — `workbench/app.py`'s
# lifespan, not this line, and each under its own advisory lock (`tc_runtime/db.py`), so
# a second worker waits rather than duplicating the work. The image ships no
# `alembic.ini`: `tc_runtime.migrate` builds its Config in memory, and the two ini files
# beside this one exist for running a chain by hand.
CMD ["uvicorn", "workbench.app:app", "--host", "0.0.0.0", "--port", "80"]

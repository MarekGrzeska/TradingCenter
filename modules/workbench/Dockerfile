# Multi-stage, the same shape as market-data's. **The build context is the repository root**: uv resolves
# `tc-runtime`'s path while installing the lock, so the package has to be inside the context.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder
WORKDIR /app/modules/workbench
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

# The packages before the lock, since `uv sync` reads them during resolution, and only the ones this module's
# pyproject.toml names — copying all of `packages/` invalidates every layer below on an unrelated edit.
COPY packages/tc-runtime /app/packages/tc-runtime
COPY packages/tc-openai /app/packages/tc-openai
COPY packages/tc-mcp-kit /app/packages/tc-mcp-kit
COPY modules/workbench/pyproject.toml modules/workbench/uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

# Four packages, and the layering between them is `tests/test_layering.py`'s rather than this file's: `agent` and
# `teams` never import each other, and `workbench` is the one place that imports all three.
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

# Both migration chains run at startup inside the process, each under its own advisory lock. The image ships no
# `alembic.ini`: `tc_runtime.migrate` builds its Config in memory, and the two ini files exist for running by hand.
CMD ["uvicorn", "workbench.app:app", "--host", "0.0.0.0", "--port", "80"]

# Multi-stage: uv resolves and builds the venv, the runtime stage only ever ships
# that venv and the source — no compiler toolchain, no uv binary, no lockfile parsing
# at container start.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

# Dependencies first, from the lockfile alone — this layer only invalidates when
# pyproject.toml or uv.lock change, not on every source edit.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

COPY teams_mcp ./teams_mcp
RUN uv sync --frozen --no-dev

FROM python:3.12-slim-bookworm
WORKDIR /app
COPY --from=builder /app /app
ENV PATH="/app/.venv/bin:$PATH"

# Azure App Service's default expectation for a Linux custom container — matches
# infra/app-service.tf, which sets no WEBSITES_PORT override.
EXPOSE 80

# Every interface, because the platform reaches the container from outside it — this
# module's override of `config.py`'s loopback default, the same line the other
# modules write as `--host 0.0.0.0`.
ENV TEAMS_MCP_HOST=0.0.0.0
ENV TEAMS_MCP_PORT=80

# The only transport this module has (`server.py`) — there is no stdio choice to
# pass on the command line.
CMD ["python", "-m", "teams_mcp"]

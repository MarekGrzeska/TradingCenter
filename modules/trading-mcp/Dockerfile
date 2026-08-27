# Multi-stage: uv resolves and builds the venv, the runtime stage ships only that venv and the source. **The build
# context is the repository root**: uv resolves `tc-mcp-kit`'s path while installing the lock, so it must be inside it.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder
WORKDIR /app/modules/trading-mcp
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

# Dependencies first, from the lockfile alone, and only the package this module's pyproject.toml names: copying all of
# `packages/` makes an edit to a package this image never installs invalidate every layer below.
COPY packages/tc-mcp-kit /app/packages/tc-mcp-kit
COPY modules/trading-mcp/pyproject.toml modules/trading-mcp/uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

COPY modules/trading-mcp/trading_mcp ./trading_mcp
RUN uv sync --frozen --no-dev

FROM python:3.12-slim-bookworm
WORKDIR /app/modules/trading-mcp
COPY --from=builder /app /app
ENV PATH="/app/modules/trading-mcp/.venv/bin:$PATH"

# Azure App Service's default expectation for a Linux custom container — matches
# infra/app-service.tf, which sets no WEBSITES_PORT override.
EXPOSE 80

# Every interface, because the platform reaches the container from outside it — this module's override of config.py's
# loopback default, the same line the other modules write as `--host 0.0.0.0`.
ENV TRADING_MCP_HOST=0.0.0.0
ENV TRADING_MCP_PORT=80

# The only transport this module has (`server.py`) — there is no stdio choice to
# pass on the command line.
CMD ["python", "-m", "trading_mcp"]

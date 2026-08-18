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
WORKDIR /app/modules/trading-mcp
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

# Dependencies first, from the lockfile alone — this layer only invalidates when
# pyproject.toml or uv.lock change, not on every source edit.
# The package before the lock: `uv sync` reads it during resolution, not after.
COPY packages /app/packages
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

# Every interface, because the platform reaches the container from outside it — this
# module's override of `config.py`'s loopback default, the same line the other
# modules write as `--host 0.0.0.0`.
ENV TRADING_MCP_HOST=0.0.0.0
ENV TRADING_MCP_PORT=80

# The only transport this module has (`server.py`) — there is no stdio choice to
# pass on the command line.
CMD ["python", "-m", "trading_mcp"]

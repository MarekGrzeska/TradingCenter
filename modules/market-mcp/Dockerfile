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
WORKDIR /app/modules/market-mcp
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

# Dependencies first, from the lockfile alone — this layer only invalidates when
# pyproject.toml or uv.lock change, not on every source edit.
# The package before the lock: `uv sync` reads it during resolution, not after.
# Only the one this module's pyproject.toml names — copying all of `packages/` made
# an edit to a package this image never installs invalidate this layer and every one
# below it. A package added to pyproject.toml but not here fails the build loudly:
# uv cannot resolve a path dependency that is not in the context.
COPY packages/tc-mcp-kit /app/packages/tc-mcp-kit
COPY modules/market-mcp/pyproject.toml modules/market-mcp/uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

COPY modules/market-mcp/market_mcp ./market_mcp
RUN uv sync --frozen --no-dev

FROM python:3.12-slim-bookworm
WORKDIR /app/modules/market-mcp
COPY --from=builder /app /app
ENV PATH="/app/modules/market-mcp/.venv/bin:$PATH"

# Azure App Service's default expectation for a Linux custom container — matches
# infra/app-service.tf, which sets no WEBSITES_PORT override. MCP_HTTP_PORT=80 is set
# alongside it so the server binds where the platform is listening.
EXPOSE 80

# Every interface, because the platform reaches the container from outside it. This is
# the container's override of `config.py`'s loopback default, and it is the same line
# the other three modules write as `--host 0.0.0.0` in their uvicorn CMD.
ENV MCP_HTTP_HOST=0.0.0.0

# The `http` transport, not `stdio` — App Service speaks HTTP to the container, and
# `/health` lives on the same ASGI app `server.py` builds around the MCP route.
CMD ["python", "-m", "market_mcp", "http"]

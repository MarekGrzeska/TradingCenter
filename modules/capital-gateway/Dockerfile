# Multi-stage: uv resolves and builds the venv, the runtime stage ships only that venv and the source — no compiler
# toolchain, no uv binary, no lockfile parsing at container start.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

# Dependencies first, from the lockfile alone — this layer only invalidates when
# pyproject.toml or uv.lock change, not on every source edit.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

COPY capital_gateway ./capital_gateway
RUN uv sync --frozen --no-dev

FROM python:3.12-slim-bookworm
WORKDIR /app
COPY --from=builder /app /app
ENV PATH="/app/.venv/bin:$PATH"

# Azure App Service's default expectation for a Linux custom container — matches
# infra/app-service.tf, which sets no WEBSITES_PORT override.
EXPOSE 80

# No --reload and no dev server: what makes this safe to run against real capital.com credentials is config.py's own
# guards — production refuses /docs, GATEWAY_ENV, the caller-key check — and nothing in this image.
CMD ["uvicorn", "capital_gateway.app:app", "--host", "0.0.0.0", "--port", "80"]

# The operator's agent: one Claude Code session in tmux, a scheduler, and nothing that can reach the host. After
# AgenticEnglish's infra/agent.Dockerfile. **The build context is the repository root**: the token helper is
# `scripts/mcp_token.py`, the one the operator runs at the desk.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder
# A Python of uv's own under /opt/agent, not the image's: the runtime stage is a Node image with no 3.12 to link to.
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_PREFERENCE=only-managed \
    UV_PYTHON_INSTALL_DIR=/opt/agent/python UV_PROJECT_ENVIRONMENT=/opt/agent/venv UV_PYTHON=3.12
WORKDIR /src
COPY modules/claude-agent/pyproject.toml modules/claude-agent/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

FROM node:22-bookworm-slim

ARG CLAUDE_CODE_VERSION=2.1.304
ARG BUN_VERSION=1.4.3
ARG SUPERCRONIC_VERSION=v0.2.50
ARG SUPERCRONIC_SHA256=d2d7c97fbfefc763d5bbcbbb3f8d61f9dd3410ce5d05a737c414994b80b8cdd0

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
 && apt-get install -y --no-install-recommends tmux tzdata tini ca-certificates curl jq procps git \
 && rm -rf /var/lib/apt/lists/*

RUN curl -fsSLo /usr/local/bin/supercronic \
      "https://github.com/aptible/supercronic/releases/download/${SUPERCRONIC_VERSION}/supercronic-linux-amd64" \
 && echo "${SUPERCRONIC_SHA256}  /usr/local/bin/supercronic" | sha256sum -c - \
 && chmod 0755 /usr/local/bin/supercronic

# Claude Code pinned: channels are a research preview, so an update is a deliberate rebuild. Bun runs the Telegram plugin.
RUN npm install -g "@anthropic-ai/claude-code@${CLAUDE_CODE_VERSION}" "bun@${BUN_VERSION}" \
 && npm cache clean --force

RUN useradd --create-home --uid 10001 --shell /bin/bash agent \
 && mkdir -p /home/agent/.claude /home/agent/work \
 && chown -R agent:agent /home/agent

COPY --from=builder /opt/agent /opt/agent
COPY modules/claude-agent/claude_agent /opt/agent/claude_agent
COPY modules/claude-agent/agent /opt/agent/agent
COPY modules/claude-agent/runtime/*.sh /opt/agent/bin/
COPY scripts/mcp_token.py /opt/agent/bin/mcp_token.py
RUN find /opt/agent/agent /opt/agent/claude_agent -type f -exec chmod 0644 {} + \
 && chmod 0755 /opt/agent/bin/*.sh

ENV TZ=Europe/Warsaw \
    HOME=/home/agent \
    CLAUDE_CONFIG_DIR=/home/agent/.claude \
    DISABLE_AUTOUPDATER=1 \
    AGENT_WORKDIR=/home/agent/work \
    AGENT_PYTHON=/opt/agent/venv/bin/python \
    PYTHONPATH=/opt/agent \
    TERM=xterm-256color

USER agent
WORKDIR /home/agent/work

HEALTHCHECK --interval=60s --timeout=10s --start-period=60s --retries=3 CMD ["/opt/agent/bin/healthcheck.sh"]
ENTRYPOINT ["/usr/bin/tini", "--", "/opt/agent/bin/entrypoint.sh"]

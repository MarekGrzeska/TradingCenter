# claude-agent

The operator's Claude Code session on the server (`openspec/changes/operator-agent-on-telegram`): one session in tmux,
reached from a phone through a private Telegram bot and from the Claude app through Remote Control, acting on the
system **only** through the nine production tool surfaces — the same ones the operator's Claude Code reaches at the desk
(`scripts/claude-mcp.sh`). After AgenticEnglish's `agent/` and `infra/runtime/`, which ran this shape first.

```
uv run pytest · uv run ruff check . · uv run pyright
```

The entrypoint tests need bash, `jq` and coreutils' `timeout`, and skip without them (on Windows); CI runs them.

## What it is and is not

- **On the subscription only.** No API key anywhere; `claude_agent/zero_api.py` refuses the start when one is found.
- **One process, no privilege.** No port, no `edge`/`services`/`data` network, no secret of the system. It calls
  `https://API_HOST/…/mcp` through Caddy like any outside caller and is admitted by the same three checks: token, the
  operator's `admin` role, and its own application on the lists of callers.
- **Its own application, the operator's person.** Signed in once with a device code as the operator, to the registration
  `app-tradingcenter-vps-agent`: teams it creates are the operator's, and every log names it apart from the desk client.
- **Account writes off** unless `AGENT_ACCOUNT_WRITES=on`; the live account's (`tc-trading-live`, `live-account-trading`)
  off unless `AGENT_LIVE_ACCOUNT_WRITES=on`, a switch of its own that the demo one never opens. `send_telegram_message`, the shell, file writes and the web are
  denied either way (`agent/.claude/settings.json`, rendered by `claude_agent/render.py`).

## Layout

| Path | What |
|---|---|
| `agent/` | `CLAUDE.md`, the skills (`przeglad-rana`, `podsumowanie-dnia`, `pozycje`) and the permission settings |
| `claude_agent/` | the zero-API check, the rendering of settings and MCP servers, the check-in scheduler |
| `runtime/` | `entrypoint.sh` (the session loop), `channel-watchdog.sh`, `restart.sh` (04:00), `healthcheck.sh` |
| `Dockerfile` | Claude Code and bun pinned; the build context is the repository root, for `scripts/mcp_token.py` |

## Settings

`.env.example` is the list. On the server they come from the GitHub environment `vps` (`deploy/env.required`).

## On the server, once

Steps the operator takes after the first deploy, from `.local/vps/vps.sh`; the container is healthy without them, so
nothing is rolled back while they are pending. Detailed in `deploy/README.md`.

1. Log in the subscription: attach to the session, `/login`, the subscription, the code.
2. `claude plugin install telegram@claude-plugins-official`, the bot's token into `~/.claude/channels/telegram/.env`
   (a bot from @BotFather, **never one registered in `/telegram`**: the workbench long-polls every bot it holds, and
   Telegram allows one poller per token), then pair and set `allowFrom` to the operator alone.
3. `mcp_token.py login --device-code` with the agent's client id and the cache in the volume.

## Traps

- Claude Code connects MCP servers once, at session start, and never retries: the entrypoint waits for
  `https://API_HOST/health` first. A server shown as failed afterwards is `/mcp` → reconnect, or a restart.
- The channel plugin is often marked failed at start (2.1.304): `channel-watchdog.sh` reconnects it within a minute.
- A dialog in the pane (an upsell, a "what's new") blocks the session; attach and dismiss it.

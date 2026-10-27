# deploy/

The whole system on one server (`openspec/changes/move-from-azure-to-vps`). Nothing here is Azure's, and nothing names a
provider: any machine that takes cloud-init user-data and runs Ubuntu 24.04 will do.

| File | What it is |
|---|---|
| `docker-compose.yml` | caddy · gateway · trading-mcp · workbench · postgres · db-init. Only Caddy has `ports:`. |
| `Caddyfile` | TLS for four names, the edge marker `X-TC-Edge`, CORS for the two front ends, the static files. |
| `postgres/ensure-databases.sh` | eight roles, each the owner of its database, created or updated on every deploy. |
| `env.required` | the names `.env` must hold. The deploy refuses to start if one is missing. |
| `cloud-init.yaml` · `ansible/` | the machine: users and SSH policy, then firewall, updates, log rotation, directories, the deploy key. |
| `scripts/deploy.sh` | the one command the deploy key may run (`env`, `sync`, `www`, `login`, `release`, `rollback`, `status`). |
| `scripts/assemble_env.py` | builds `.env` from GitHub's secrets and variables on the runner. |
| `scripts/alert.sh` · `disk-alert.sh` | a message to the operator, straight to Telegram's Bot API. |
| `scripts/backup.sh` · `backup-check.sh` | the nightly dump of every database (14 days, in `/var/backups/tradingcenter`), and the morning check that one exists and that someone collected it. |
| `scripts/backup-serve.sh` | the one command the `tcbackup` key may run: `list`, `get <dump>`, `ack`. Installed by Ansible as root's `/usr/local/bin/tc-backup-serve`. |
| `../scripts/pull-backups.ps1` | runs on the operator's computer and collects the dumps (below). |

## The first time

1. A machine with ≥ 4 vCPU, 8 GB, 80 GB in the EU. Put the operator's public key into `cloud-init.yaml` (the line that says
   `REPLACE_WITH_…`) and pass the file as user-data.
2. DNS: `API_HOST`, `GATEWAY_HOST`, `TERMINAL_HOST`, `POCKET_HOST` → the machine's address. Caddy fetches the certificates
   itself once they resolve.
3. `ansible-playbook -i inventory.ini site.yml -e deploy_public_key="$(cat deploy_key.pub)" -e '{"ssh_allowed_cidrs": ["<ip>/32"]}'`
   — from `deploy/ansible/`, with `inventory.ini` copied from the example. The play opens port 22 to nobody until it is told
   from where.
4. GitHub environment `vps`: the secrets `deploy/env.required` lists, plus `DEPLOY_SSH_KEY` (the private half of the deploy
   key); the variables `DEPLOY_HOST`, `DEPLOY_KNOWN_HOSTS` (the output of `ssh-keyscan -t ed25519 <host>`, taken from a
   place you trust), the four `*_HOST` names, `ENTRA_TENANT_ID`, `TERMINAL_ENTRA_CLIENT_ID`, `POCKET_ENTRA_CLIENT_ID`.
   `WORKBENCH_ENTRA_AUDIENCES` and `GATEWAY_ENTRA_AUDIENCES` are **both spellings of each API** (`api://…` and the client id),
   comma-separated: a v1 token carries the first, a v2 token the second.
5. Run `deploy-vps` by hand (`workflow_dispatch`) once.

## Claude Code on production's tools

Every tool surface — the workbench's `/<package>/mcp`, `/team-tools/mcp` and trading-mcp's `/trading/mcp` — answers the
operator's own Claude Code and nothing else outside (`openspec/changes/operator-mcp-access`). Once, in this order:

1. `terraform apply` in `infra/` — it creates `app-tradingcenter-claude-code` and pre-authorizes it on both APIs. **Read
   the plan**: anything it wants to destroy besides what this change adds is drift to settle first.
2. `CLAUDE_CODE_APPLICATION_ID` (`terraform output -raw claude_code_entra_client_id`) as a variable of the environment
   `vps` — `fill-github-environment.sh` sets it. The deploy stops before sending anything while it is missing.
3. After the deploy, on the operator's machine:
   `uv run --script scripts/mcp_token.py login --tenant <tenant> --client-id <id>` (a browser; it prints the roles each
   API sees), then `scripts/claude-mcp.sh install <API_HOST> <tenant> <id>` and `claude mcp list`.

## Backups

The server dumps each database nightly and keeps 14 days; that protects against a bad migration, not against losing the
server. The dumps leave it by being collected: a scheduled task on your computer runs `scripts/pull-backups.ps1` (the
header of the file has the `Register-ScheduledTask` lines) with a key that can list, read and acknowledge dumps and
nothing else. The server holds no credential to your computer. If nothing has been collected for three days, or a database
has no dump from the last day, the server tells you on Telegram. Generate the key pair for it with
`ssh-keygen -t ed25519 -f backup_key`, give the public half to Ansible as `backup_public_key`, keep the private half on the
computer that collects.

## Reaching the database

It has no published port, on purpose. From the operator's machine:

```
ssh -L 55433:$(ssh operator@HOST "docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' tradingcenter-vps-postgres-1"):5432 operator@HOST
psql "postgresql://agent:<password>@127.0.0.1:55433/agent"
```

## A bad release

`deploy.sh release` puts the previous images back by itself when the new ones do not become healthy; the workflow then
fails. To go back by hand: `ssh operator@HOST "sudo -u deploy SSH_ORIGINAL_COMMAND=rollback /opt/tradingcenter/bin/deploy"`.

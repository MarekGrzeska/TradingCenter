---
name: deploy-watch
description: Follow a commit all the way onto the server — the checks run for it, the deploy-vps.yml run it triggers, the release on the server and the probe that asks whether this commit's images are the ones running and the public addresses answer — and, when a release fails, confirm the server put the previous images back (or put them back by hand), first, then diagnose. Use it right after a merge or a push the server follows ("zmergowane", "po merge", "czy się wdrożyło", "deploy padł", "watch the deploy", "is it live", "wycofaj obraz", "rollback"), or when deploy-vps went red. Not for reading production in general (prod-health) and not for Terraform (apply stays the operator's).
---

# Deploy watch

A commit reaches the server in three hops, and each can fail quietly:

1. `checks.yml` on the commit — only the jobs the diff can have broken run.
2. `deploy-vps.yml`, started by `workflow_run` **only after a green checks run of the same commit**. `scripts/deploy_gate.py`
   skips it when nothing the server runs changed since the last green run. `workflow_dispatch` is the door around the gate.
3. On the server, `deploy/scripts/deploy.sh release <sha>` (the one command the deploy key may run): pull, `up -d`, wait
   for every container to be healthy — and on failure put `tags.env.prev` back and exit 1. Then `scripts/vps_probe.py`
   asks the server which images run and asks the four public addresses from outside.

## Follow it

```
gh run list --branch <branch> --limit 5                  # the checks run for the commit
gh run list --workflow deploy-vps.yml --limit 3          # and the deploy it started
gh run watch <id> --exit-status
```

A deploy run that ends `action_required` with no jobs is GitHub holding a workflow it thinks may be malicious — the
operator approves it on the run's page. A step handed the whole secret store is what set it off the first time.

## When it went red

Read which step failed (`gh run view <id> --log-failed`):

- **Assemble the environment** — a name in `deploy/env.required` has no secret or variable in the environment `vps`.
  `deploy/scripts/fill-github-environment.sh` fills what can be filled; nothing was sent to the server.
- **Release** — the server did not get healthy; `deploy.sh` already rolled back. Confirm, then read the logs:
  ```
  .local/vps/vps.sh run 'sudo -u deploy /opt/tradingcenter/bin/deploy status'   # images and health, as the probe sees them
  .local/vps/vps.sh run 'sudo docker logs --since 15m tradingcenter-vps-workbench-1 2>&1 | tail -80'
  ```
- **Confirm this commit is what runs** — the release said yes, the outside said no (certificate, DNS, Caddy). The
  workflow's next step runs `rollback`. Check Caddy: `sudo docker logs tradingcenter-vps-caddy-1 --since 15m`.

To roll back by hand: `.local/vps/vps.sh run 'sudo -u deploy SSH_ORIGINAL_COMMAND=rollback /opt/tradingcenter/bin/deploy'`.

`.local/vps/` is the operator's access from this machine (outside git); without it, `ssh ubuntu@<host>` does the same.

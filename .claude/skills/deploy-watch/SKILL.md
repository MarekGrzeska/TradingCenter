---
name: deploy-watch
description: Follow a merge to main all the way into production — the checks run for that commit, each deploy-*.yml it triggers, the probe that asks whether this commit's image is the one serving and the process came up — and, when a container fails to start, roll the app back to the image it served before, first, then diagnose. Use it right after merging a PR ("zmergowane", "po merge", "czy się wdrożyło", "deploy padł", "watch the deploy", "is it live", "wycofaj obraz", "rollback"), or when a deploy workflow went red. Not for reading production in general (prod-health) and not for Terraform (apply stays the operator's).
---

# Deploy watch

A merge to `main` reaches production in three hops, and each can fail quietly:

1. `checks.yml` on the merge commit — only the jobs the diff can have broken run.
2. `deploy-*.yml`, started by `workflow_run` **only after a green checks run of the same commit**.
   `scripts/deploy_gate.py` skips the build when nothing that image bakes in changed since the last
   green run — so "skipped" is normal for apps the merge did not touch.
3. `scripts/deploy_probe.py` at the end: is this commit's image the one App Service serves, **and**
   did the process inside answer its health path? The control plane alone reported `Running` over
   a crash-looping container on 16 August 2026.

There are no deployment slots. **A failed container start is downtime**, so the order is: roll the
image back (about 40 s), confirm the probe answers, *then* read logs.

## Run

```bash
bash .claude/skills/deploy-watch/scripts/watch.sh            # origin/main's head
bash .claude/skills/deploy-watch/scripts/watch.sh <sha>
```

It records the image each App Service serves **before** anything changes — those are the rollback
targets — then waits for the checks run of the commit, then for every deploy run it triggered,
then probes all three apps and prints, for any that is not answering, the exact rollback command.
Start it straight after the merge; started late, the recorded images may already be the new ones,
and the script says where to find the previous tag (the last successful deploy run of that app).

## Rolling back

```bash
az webapp config container set -g rg-tradingcenter -n <app> \
   --container-image-name ghcr.io/marekgrzeska/tradingcenter/<module>:<previous sha>
```

Then wait for the app's health path to answer 200 (`prod-health`'s probes) before anything else.
Rolling back does not undo a migration: every module migrates in its lifespan, and an older image
refuses a schema newer than itself (`schema_version.verify`). If the new image migrated before it
crashed, the rollback will not start either — say so, and fix forward instead.

## Traps

- **Settings before the image that needs them.** A new required setting must reach the app
  (`terraform apply`, the operator's) before the deploy, or the new image refuses to start. The
  PR says the order; this skill does not apply anything.
- **A deploy "succeeded" with the old image serving** is what the probe's first question exists
  for; trust its verdict over the workflow's green tick.
- **Git Bash:** `MSYS_NO_PATHCONV=1` for any `/subscriptions/...` argument, and strip `\r` from
  `az -o tsv`. The script does both.
- **Restart overlap:** during a deploy two containers run side by side for a minute — a plan memory
  peak and a Telegram `getUpdates` conflict in that minute are expected, not findings.

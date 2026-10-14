---
name: prod-health
description: Read-only health check of TradingCenter's production on its server — do the five containers run and answer, do the four public addresses answer from outside, how full are the disk and the memory, did last night's dump happen and did the operator's computer collect it, what failed in the logs in the last hour — and, only with the operator's yes, which statements load the database. Use it when production seems silent, slow or wrong ("produkcja milczy", "coś zwolniło", "czy produkcja żyje", "co z bazą", "sprawdź produkcję", "prod health", "503 on the terminal", "alert przyszedł"), after a deploy looked odd, or before measuring anything. Not for a deploy in flight (deploy-watch) and not for fixing — it says where to look, then diagnose directly.
---

# Production health

Symptoms arrive far from causes, so read the whole board in the same order every time, cheapest and most telling first.
Everything here reads; nothing restarts. The operator's access from this machine is `.local/vps/vps.sh` (outside git);
without it, `ssh ubuntu@<host>` and the same commands.

1. **From outside** — what a browser sees. `curl -s -o /dev/null -w "%{http_code}\n"` on `https://api.<domain>/health`
   (200), `https://gateway.<domain>/` (200), `https://terminal.<domain>/` and `https://pocket.<domain>/` (200), and
   `https://api.<domain>/sessions` with no token (401 — anything else is the door, and that is the first thing to say).
2. **The containers** — `vps.sh run 'sudo docker ps --format "{{.Names}} {{.Status}} {{.Image}}"'`. Five, all `Up`, four
   `(healthy)`; a `Restarting` is a crash loop and its logs are the answer.
3. **The machine** — `vps.sh run 'df -h / ; free -h ; sudo docker stats --no-stream'`. The disk alert fires at 80%.
4. **The copies** — `vps.sh run 'ls -lt /var/backups/tradingcenter | head; ls -l /var/lib/tradingcenter/backup-ack/'`.
   A dump of every database from the last day, and an acknowledgement younger than three days.
5. **What failed** — `vps.sh run 'sudo docker logs --since 1h tradingcenter-vps-workbench-1 2>&1 | grep -iE "error|traceback|refused" | tail -40'`,
   and the same for `gateway` and `trading-mcp`. Loops log each pass; a loop that went quiet is as telling as one that errs.
6. **The database, only with the operator's yes** — it costs the server a query:
   ```
   vps.sh run 'sudo docker exec tradingcenter-vps-postgres-1 psql -U postgres -c "SELECT calls, round(total_exec_time) ms, left(query, 120) FROM pg_stat_statements ORDER BY total_exec_time DESC LIMIT 15"'
   ```
   `pg_stat_statements` is created in the `postgres` database by `ensure-databases.sh`; add `-d <name>` for one database.

Report in that order, with the number each step read, and name the one thing to look at next.

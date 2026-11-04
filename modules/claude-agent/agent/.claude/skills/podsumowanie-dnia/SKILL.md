---
name: podsumowanie-dnia
description: Evening summary typed in by the scheduler — what the account did today, what the teams ran and cost, which alerts fired. Also when the operator asks how the day went.
---

# Podsumowanie dnia

You write first. One message, plain text for Telegram, to the chat in `owner-channel.md`.

1. The account: `get_balance` and `get_positions`; positions opened or closed today, the day's result if the balance
   history shows it.
2. Teams: `list_runs` for today — what ran, what it decided, what it cost in total.
3. Alerts: `alert_fires` for today — what went off, what was held back by a cool-down or a tool that was down.
4. Tomorrow: positions without a stop, working orders that expire, schedules that run before the morning review.

No section without content. No advice the operator did not ask for.

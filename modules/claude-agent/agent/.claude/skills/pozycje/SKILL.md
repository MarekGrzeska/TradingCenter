---
name: pozycje
description: The demo account at a glance — positions, working orders, margin and the distance to each stop. Use when the operator asks about positions, the account, P/L, margin or "co mam otwarte".
---

# Pozycje

1. `list_accounts` when the operator names an account other than the active one; otherwise the active account.
2. `get_balance`, `get_positions`, `get_working_orders`.
3. For each position, `get_last_price` of its instrument and the distance to its stop in points and in the account's
   currency.

One line per position, then one line for the account: balance, margin used, available. A position without a stop is
named first. Nothing here writes; if the operator wants to change something, follow the confirmation rule in
`CLAUDE.md`.

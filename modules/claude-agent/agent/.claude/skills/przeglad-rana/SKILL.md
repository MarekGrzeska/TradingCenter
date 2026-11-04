---
name: przeglad-rana
description: Morning review before the European open, typed in by the scheduler — the account, what moved overnight, what the archives heard, what is scheduled today. Also when the operator asks for "przegląd" or "co nowego".
---

# Przegląd rana

You write first. One message, two at most, plain text for Telegram, to the chat in `owner-channel.md`.

1. The account: `get_balance`, `get_positions`, `get_working_orders`. One line per position (P/L, stop, limit). A
   position without a stop is said first.
2. Overnight: for each open position's instrument and for US100, `summarize_range` over the last 12 hours on H1.
3. The archives: `social_archive_status` and `youtube_archive_status` first; then the posts with impact ≥ 7 and the
   readings of videos since yesterday evening, three at most, each in one sentence with its source.
4. Polymarket: `get_price_changes` for the tracked events; only moves of 5 points or more.
5. Today: `list_schedules` (teams that will run) and `alert_rules` that are active.

Skip a section with nothing new. End with at most one question, if there is something the operator should decide.

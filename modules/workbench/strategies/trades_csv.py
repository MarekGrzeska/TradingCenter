"""A run's trades as a CSV file the operator opens in a spreadsheet: every time in UTC and in Warsaw, an empty field where
a value does not exist (a trade without a stop has no R), never a zero standing in for it."""

from __future__ import annotations

import csv
import io
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

WARSAW = ZoneInfo("Europe/Warsaw")
# What a spreadsheet needs to read the Polish words of an exit reason as UTF-8.
BOM = "﻿"

COLUMNS = (
    "seq", "side", "entry_time_utc", "entry_time_warsaw", "entry_price", "exit_time_utc", "exit_time_warsaw", "exit_price",
    "units", "initial_stop", "result_money", "result_pct", "result_r", "mae_pct", "spread", "slippage", "financing",
    "exit_reason", "pessimistic",
)


def header() -> str:
    return BOM + _line(COLUMNS)


def rows(trades: list[Mapping[str, Any]]) -> str:
    return "".join(_line(_cells(trade)) for trade in trades)


def _cells(trade: Mapping[str, Any]) -> list[str]:
    costs = trade["costs"]
    entry, leave = trade["entry_time"], trade["exit_time"]
    return [
        _text(trade["seq"]), trade["side"],
        _utc(entry), _warsaw(entry), _text(trade["entry_price"]),
        _utc(leave), _warsaw(leave), _text(trade["exit_price"]),
        _text(trade["units"]), _text(trade["initial_stop"]), _text(trade["result_money"]), _text(trade["result_pct"]),
        _text(trade["result_r"]), _text(trade["mae_pct"]),
        _text(costs.get("spread")), _text(costs.get("slippage")), _text(costs.get("financing")),
        trade["exit_reason"], "true" if trade["pessimistic"] else "false",
    ]


def _text(value: float | None) -> str:
    return "" if value is None else repr(value)


def _utc(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat(timespec="seconds")


def _warsaw(moment: datetime) -> str:
    return moment.astimezone(WARSAW).isoformat(timespec="seconds")


def _line(cells: tuple[str, ...] | list[str]) -> str:
    out = io.StringIO()
    csv.writer(out, lineterminator="\r\n").writerow(cells)
    return out.getvalue()

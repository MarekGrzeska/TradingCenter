"""The trades file (`strategies-api`, "Transakcje uruchomienia jako CSV"): columns, the two time zones and the empty fields."""

from __future__ import annotations

import csv
import io
from datetime import UTC, datetime

from strategies import trades_csv


def _trade(**changes) -> dict:
    return {
        "seq": 0, "side": "long", "entry_time": datetime(2026, 7, 2, 13, 35, tzinfo=UTC), "entry_price": 100.5,
        "exit_time": datetime(2026, 7, 2, 19, 55, tzinfo=UTC), "exit_price": 101.0, "units": 2.0, "initial_stop": None,
        "result_money": 1.0, "result_pct": 0.0001, "result_r": None, "mae_pct": 0.0,
        "costs": {"spread": 1.5, "slippage": 0.0, "financing": 0.2}, "exit_reason": "when", "pessimistic": False,
    } | changes


def _row(trade: dict) -> dict[str, str]:
    table = list(csv.reader(io.StringIO(trades_csv.header().lstrip(trades_csv.BOM) + trades_csv.rows([trade]))))
    return dict(zip(table[0], table[1], strict=True))


def test_a_trade_is_written_in_utc_and_in_warsaw_summer_and_winter() -> None:
    summer = _row(_trade())
    winter = _row(_trade(entry_time=datetime(2026, 1, 15, 13, 35, tzinfo=UTC)))

    assert (summer["entry_time_utc"], summer["entry_time_warsaw"]) == ("2026-07-02T13:35:00+00:00", "2026-07-02T15:35:00+02:00")
    assert winter["entry_time_warsaw"] == "2026-01-15T14:35:00+01:00"
    assert summer["exit_time_warsaw"] == "2026-07-02T21:55:00+02:00"


def test_what_a_trade_does_not_have_is_an_empty_field_not_a_zero() -> None:
    row = _row(_trade())

    assert row["initial_stop"] == "" and row["result_r"] == ""
    assert row["mae_pct"] == "0.0" and row["slippage"] == "0.0" and row["pessimistic"] == "false"
    assert (row["spread"], row["financing"], row["exit_reason"]) == ("1.5", "0.2", "when")


def test_the_file_starts_with_the_byte_order_mark_and_one_header_line() -> None:
    assert trades_csv.header().startswith(trades_csv.BOM + "seq,side,")
    assert trades_csv.header().count("\n") == 1

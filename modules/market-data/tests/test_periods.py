from __future__ import annotations

from datetime import UTC, datetime

import pytest

from market_data.periods import from_epoch_millis, from_epoch_seconds, from_iso

MOMENT = datetime(2026, 8, 7, 12, 0, tzinfo=UTC)
EPOCH_SECONDS = 1_786_104_000


def test_the_form_the_gateway_actually_sends_is_read_as_utc() -> None:
    # The gateway stamps the Z the provider omits, so this is the ordinary case.
    assert from_iso("2026-08-07T12:00:00Z") == MOMENT


def test_a_timestamp_with_an_offset_becomes_the_same_instant() -> None:
    assert from_iso("2026-08-07T14:00:00+02:00") == MOMENT


def test_a_timestamp_without_a_zone_is_read_as_utc() -> None:
    # A candle the provider gave no `snapshotTimeUTC` for reaches the gateway as broker
    # local time with no marker. Reading it as UTC is the same assumption the gateway
    # makes parsing its own output back, so the two are wrong together or right
    # together — never quietly a couple of hours apart.
    assert from_iso("2026-08-07T12:00:00") == MOMENT


def test_subsecond_precision_survives() -> None:
    assert from_iso("2026-08-07T12:00:00.500Z") == MOMENT.replace(microsecond=500_000)


@pytest.mark.parametrize("ts", ["", "   "])
def test_a_candle_with_no_timestamp_at_all_names_itself(ts: str) -> None:
    # `mapping._candle_ts` returns an empty string when the provider sent neither time
    # field. Without this the failure surfaces as a stack trace from the date parser.
    with pytest.raises(ValueError, match="no timestamp"):
        from_iso(ts)


def test_an_unreadable_timestamp_quotes_what_arrived() -> None:
    with pytest.raises(ValueError, match="unreadable"):
        from_iso("last tuesday")


def test_epoch_seconds_are_read_as_utc() -> None:
    assert from_epoch_seconds(EPOCH_SECONDS) == MOMENT


def test_epoch_millis_are_read_as_utc() -> None:
    # Quotes are the one thing on the feed that speaks in milliseconds, because that is
    # what the provider sends and the gateway forwards unchanged.
    assert from_epoch_millis(EPOCH_SECONDS * 1000 + 250) == MOMENT.replace(microsecond=250_000)


def test_both_forms_of_the_same_period_are_one_instant() -> None:
    assert from_iso("2026-08-07T12:00:00Z") == from_epoch_seconds(EPOCH_SECONDS)

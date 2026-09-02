"""The rule tested once, here: a loop that stopped reads as late, and one that has never run reads
as later still. What each module considers late is its own number and its own test."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from tc_runtime.liveness import NEVER_RAN, Heartbeats, LoopHeartbeat

START = datetime(2026, 9, 2, 12, 0, tzinfo=UTC)


def test_a_loop_that_has_never_finished_a_pass_reads_as_far_behind() -> None:
    """Not zero, which an alert reads as "just ran" — a process that comes up and never manages a
    pass is exactly the failure this exists for, and it must fire rather than look healthy."""
    heartbeat = LoopHeartbeat("collect", expected_seconds=60)
    assert not heartbeat.has_run
    assert heartbeat.age_seconds(START) == NEVER_RAN
    assert heartbeat.passes_late(START) > 1


def test_a_pass_resets_the_age() -> None:
    heartbeat = LoopHeartbeat("collect", expected_seconds=60)
    heartbeat.beat(START)
    assert heartbeat.age_seconds(START + timedelta(seconds=30)) == 30
    assert heartbeat.passes_late(START + timedelta(seconds=30)) == 0.5


def test_lateness_is_counted_in_the_loops_own_interval() -> None:
    """A sampling pass every minute and a collection every hour are both healthy, so one threshold
    in seconds would be wrong for one of them. Both are one pass late after one interval."""
    quick = LoopHeartbeat("sample", expected_seconds=60)
    slow = LoopHeartbeat("collect", expected_seconds=3600)
    quick.beat(START)
    slow.beat(START)

    assert quick.passes_late(START + timedelta(minutes=1)) == 1
    assert slow.passes_late(START + timedelta(hours=1)) == 1
    assert slow.passes_late(START + timedelta(minutes=1)) < 0.1


def test_a_clock_that_went_backwards_is_not_a_negative_age() -> None:
    heartbeat = LoopHeartbeat("sample", expected_seconds=60)
    heartbeat.beat(START)
    assert heartbeat.age_seconds(START - timedelta(seconds=5)) == 0


def test_the_registry_answers_for_every_loop_it_holds() -> None:
    sample = LoopHeartbeat("sample", expected_seconds=60)
    collect = LoopHeartbeat("collect", expected_seconds=3600)
    heartbeats = Heartbeats(sample, collect)
    sample.beat(START)

    reported = heartbeats.as_dict(START + timedelta(seconds=10))
    assert reported["sample"] == {"ran": True, "age_seconds": 10.0, "expected_seconds": 60}
    assert reported["collect"]["ran"] is False
    assert heartbeats["collect"] is collect

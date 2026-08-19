"""Regions rather than lines: three-bar imbalances and fixed clock windows.

No market calendar backs any of this. `session_range` and `opening_range` take the hours
they cover as parameters and read the archive's own fine series to place them; a gap is
suppressed across a *verified* market closure, which coverage knows and a calendar would
have to be taught (docs/wskazniki-plan-wdrozenia.html, "W2 — strefy"; task 4.3).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

import numpy as np

from .spec import (
    IndicatorSpec,
    MinuteZoneFn,
    MinuteZones,
    Param,
    Render,
    Series,
    Warmup,
    Zone,
    Zones,
)

# ("market_status wie tylko, czy rynek jest otwarty teraz"). ---


def _three_bar_gaps(
    hi: np.ndarray,
    lo: np.ndarray,
    session_close_before: np.ndarray,
    skip_session_gaps: bool,
) -> list[Zone]:
    """A void between bar `i - 1` and bar `i + 1` that bar `i` itself never
    reaches into, in whichever direction `i`'s impulse moved — the "fair value
    gap" a three-bar pattern is, on whichever pair of edges the caller hands in
    (`hi`/`lo` are the full wick range for `range_gap`, the body's own edges for
    `body_gap`; the pattern itself does not care which).

    Touched and filled are different claims: touched is price merely reaching
    the near edge again, filled is a later bar crossing all the way to the far
    one. Only the second means the imbalance is gone, so only the second closes
    the zone (`end_bar`) — `IndicatorZoneOut.to` stays null on a merely-touched
    gap, same as one nothing has come back to at all.

    A candidate spanning a confirmed market closure (`session_close_before`) is
    skipped when `skip_session_gaps` is set — a weekend is not an imbalance,
    task 4.3's whole point.
    """
    n = len(hi)
    zones: list[Zone] = []
    for i in range(1, n - 1):
        if skip_session_gaps and (session_close_before[i] or session_close_before[i + 1]):
            continue
        direction: Literal["bullish", "bearish"]
        if lo[i + 1] > hi[i - 1]:
            top, bottom, direction = float(lo[i + 1]), float(hi[i - 1]), "bullish"
        elif hi[i + 1] < lo[i - 1]:
            top, bottom, direction = float(lo[i - 1]), float(hi[i + 1]), "bearish"
        else:
            continue

        touched_at: int | None = None
        filled_at: int | None = None
        # `i + 2`, not `i + 1`: bar `i + 1` is one of the three bars that forms
        # the gap in the first place (its own edge *is* `top`, by construction
        # above), so starting the scan there would count the gap as touching
        # itself the instant it exists.
        for j in range(i + 2, n):
            if direction == "bullish":
                if touched_at is None and lo[j] <= top:
                    touched_at = j
                if lo[j] <= bottom:
                    filled_at = j
                    break
            else:
                if touched_at is None and hi[j] >= bottom:
                    touched_at = j
                if hi[j] >= top:
                    filled_at = j
                    break

        zones.append(
            Zone(
                start_bar=i - 1,
                end_bar=filled_at,
                top=top,
                bottom=bottom,
                direction=direction,
                touched_at_bar=touched_at,
                filled_at_bar=filled_at,
            )
        )
    return zones


def _body_edges(s: Series) -> tuple[np.ndarray, np.ndarray]:
    return np.maximum(s.open, s.close), np.minimum(s.open, s.close)


_SKIP_SESSION_GAPS_PARAM = Param(name="skip_session_gaps", type="int", default=1, min=0, max=1)

_RANGE_GAP = IndicatorSpec(
    id="range_gap",
    name="Range Gap",
    group="zones",
    aliases=("Fair Value Gap", "FVG", "Imbalance"),
    inputs=("high", "low"),
    params=(_SKIP_SESSION_GAPS_PARAM,),
    render=Render(pane="price", style="line"),
    warmup=Warmup(kind="fixed", bars=lambda p: 0),
    computer=Zones(lambda s, p, session_close_before: _three_bar_gaps(
        s.high, s.low, session_close_before, bool(p["skip_session_gaps"])
    )),
)

_BODY_GAP = IndicatorSpec(
    id="body_gap",
    name="Body Gap",
    group="zones",
    inputs=("open", "close"),
    params=(_SKIP_SESSION_GAPS_PARAM,),
    render=Render(pane="price", style="line"),
    warmup=Warmup(kind="fixed", bars=lambda p: 0),
    computer=Zones(lambda s, p, session_close_before: _three_bar_gaps(
        *_body_edges(s), session_close_before, bool(p["skip_session_gaps"])
    )),
)


def _fixed_window_zones(
    s: Series, days: Sequence[object], in_window: Callable[[int], bool]
) -> list[Zone]:
    """Groups consecutive in-window minute bars into one zone apiece — shared
    by `_session_window_zones` (a window per local calendar day) and
    `_opening_range_zones` (a window per UTC calendar day), which differ only
    in how `in_window` decides a bar belongs to today's window, and in which
    calendar `days` names.

    A day boundary always closes whatever window was open first, even if
    `in_window` would call the new day's own first bar "inside" too — a
    window defined in its own zone's local hours never legitimately reaches
    midnight, so two different days' windows must never merge into one zone
    just because nothing out-of-window separated them.
    """
    zones: list[Zone] = []
    window_bars: list[int] = []

    def flush(closed: bool) -> None:
        if not window_bars:
            return
        highs = [float(s.high[b]) for b in window_bars]
        lows = [float(s.low[b]) for b in window_bars]
        zones.append(
            Zone(
                start_bar=window_bars[0],
                end_bar=window_bars[-1] if closed else None,
                top=max(highs),
                bottom=min(lows),
            )
        )
        window_bars.clear()

    for i in range(len(days)):
        if i > 0 and days[i] != days[i - 1]:
            flush(closed=True)
        if in_window(i):
            window_bars.append(i)
        else:
            flush(closed=True)
    # Whatever is still open when the read range ends has not closed within it
    # — `end_bar=None`, `IndicatorZoneOut.to`'s null, same as an unfilled gap.
    flush(closed=False)
    return zones


def _session_window_zones(zone_info: ZoneInfo) -> MinuteZoneFn:
    """One zone per local calendar day in `zone_info`, spanning the bars whose
    local clock time falls in `[from_hour, to_hour)` — a fixed window, not a
    market-hours lookup (see this module's docstring). `zoneinfo`
    resolves the UTC offset per calendar day rather than once for the whole
    read, so the same local hours line up across a DST change instead of
    sliding by the transition's hour (task 4.9)."""

    def compute(s: Series, times: Sequence[datetime], p: Mapping[str, float]) -> list[Zone]:
        from_hour = float(p["from_hour"])
        to_hour = float(p["to_hour"])
        local_times = [t.astimezone(zone_info) for t in times]
        days = [t.date() for t in local_times]

        def in_window(i: int) -> bool:
            local = local_times[i]
            hour = local.hour + local.minute / 60 + local.second / 3600
            return from_hour <= hour < to_hour

        return _fixed_window_zones(s, days, in_window)

    return compute


def _opening_range_zones(s: Series, times: Sequence[datetime], p: Mapping[str, float]) -> list[Zone]:
    """The high-low range of the first `window_minutes` of each UTC calendar
    day — `htf_levels_day` anchors to the same boundary for the same reason:
    it is the only "day" this module can name without a session calendar
    (design.md, Ichimoku/Alligator decision). Kept to the most recent `n` —
    unlike a gap or a session window, nothing bounds how many opening ranges a
    wide daily-chart request would otherwise produce."""
    window = timedelta(minutes=int(p["window_minutes"]))
    n = int(p["n"])
    days = [t.date() for t in times]
    day_starts = [t.replace(hour=0, minute=0, second=0, microsecond=0) for t in times]

    def in_window(i: int) -> bool:
        return times[i] < day_starts[i] + window

    zones = _fixed_window_zones(s, days, in_window)
    return zones[-n:] if n > 0 else []


_SESSION_TYPES: tuple[tuple[str, str, str, float, float], ...] = (
    ("session_range_london", "London Session Range", "Europe/London", 8.0, 16.5),
    ("session_range_new_york", "New York Session Range", "America/New_York", 9.5, 16.0),
    ("session_range_tokyo", "Tokyo Session Range", "Asia/Tokyo", 9.0, 15.0),
)

_SESSIONS: tuple[IndicatorSpec, ...] = tuple(
    IndicatorSpec(
        id=id_,
        name=name,
        group="zones",
        inputs=("high", "low"),
        params=(
            Param(name="from_hour", type="float", default=default_from, min=0.0, max=24.0),
            Param(name="to_hour", type="float", default=default_to, min=0.0, max=24.0),
        ),
        render=Render(pane="price", style="line"),
        warmup=Warmup(kind="fixed", bars=lambda p: 0),
        computer=MinuteZones(_session_window_zones(ZoneInfo(tz_name))),
    )
    for id_, name, tz_name, default_from, default_to in _SESSION_TYPES
)

_OPENING_RANGE = IndicatorSpec(
    id="opening_range",
    name="Opening Range",
    group="zones",
    aliases=("ORB", "Opening Range Breakout"),
    inputs=("high", "low"),
    params=(
        Param(name="window_minutes", type="int", default=30, min=1, max=240),
        Param(name="n", type="int", default=5, min=1, max=50),
    ),
    render=Render(pane="price", style="line"),
    warmup=Warmup(kind="fixed", bars=lambda p: 0),
    computer=MinuteZones(_opening_range_zones),
)


ZONES: tuple[IndicatorSpec, ...] = (
    _RANGE_GAP,
    _BODY_GAP,
    *_SESSIONS,
    _OPENING_RANGE,
)

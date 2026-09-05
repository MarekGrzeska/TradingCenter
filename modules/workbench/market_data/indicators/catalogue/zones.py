"""Regions rather than lines: three-bar imbalances and fixed clock windows. No market calendar backs
any of it — a gap is suppressed across a *verified* closure, which coverage knows."""

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


def _three_bar_gaps(
    hi: np.ndarray,
    lo: np.ndarray,
    session_close_before: np.ndarray,
    skip_session_gaps: bool,
) -> list[Zone]:
    """A void between bar `i - 1` and bar `i + 1` that bar `i` never reaches into. Touched and filled
    are different claims, and only filled — a later bar crossing to the far edge — closes the zone."""
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
        # `i + 2`, not `i + 1`: bar `i + 1` is one of the three bars forming the gap, so a scan
        # starting there would count the gap as touching itself the instant it exists.
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
    """Groups consecutive in-window minute bars into one zone apiece. A day boundary always closes
    the open window first, so two days' windows never merge because nothing out-of-window separated them."""
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
    """One zone per local calendar day, spanning the bars whose local clock falls in the window — not
    a market-hours lookup. `zoneinfo` resolves the offset per day, so DST does not slide the hours."""

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
    """The high-low range of the first `window_minutes` of each UTC day — the only "day" this module
    can name without a session calendar. Kept to the most recent `n`: nothing else bounds the count."""
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

# /// script
# requires-python = ">=3.12"
# dependencies = ["httpx>=0.27"]
# ///
"""One levels file feeds both the terminal's chart and the article's figures, so they cannot disagree.

    uv run --script psv.py payload levels.json --remove 111,112 > draw.json
    uv run --script psv.py svg levels.json --chart intraday --resolution HOUR --from 2026-11-13T00:00:00Z \
        --aria "US100 H1 ..." > fig1.svg

levels.json is a list of {"short": caption on the figure, "charts": ["intraday", "d1"], "draw": <draw_on_chart `add` item>}.
Candles come from production's /market/mcp through tc_mcp.py (bid side, the only one the archive holds)."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from tc_mcp import call  # noqa: E402

PALETTE = {  # modules/terminal/src/index.css, so a figure's colour is the colour on the operator's chart
    "--color-drawing-1": "#009fb4",
    "--color-drawing-2": "#8f5ada",
    "--color-drawing-3": "#7f9422",
    "--color-drawing-4": "#d14f72",
}
UP, DOWN, NAVY, GRID, AXIS = "#17734c", "#b8322a", "#14306b", "#ebe8de", "#85899a"
X0, X1, Y0, Y1 = 58, 690, 16, 524
MONTHS = "sty lut mar kwi maj cze lip sie wrz paź lis gru".split()


def pts(value: float) -> str:
    return f"{round(value):,}".replace(",", " ")


def load(path: str) -> list[dict]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def payload(args: argparse.Namespace) -> None:
    body: dict = {"symbol": args.symbol, "add": [item["draw"] for item in load(args.levels)]}
    if args.remove:
        body["remove"] = [int(i) for i in args.remove.split(",")]
    print(json.dumps(body, ensure_ascii=False, indent=1))


def session_date(moment: str) -> str:
    """The index CFD's session opens at 23:00 UTC (22:00 in summer): that hour already belongs to the next day."""
    return str((datetime.fromisoformat(moment.replace("Z", "+00:00")) + timedelta(hours=2)).date())


def candles(symbol: str, resolution: str, start: str, end: str | None) -> list[dict]:
    query = {"symbol": symbol, "resolution": resolution, "from_iso": start, "to_iso": end}
    answer = json.loads(call("market", "get_candles", query))
    if answer.get("aggregated"):
        print(f"note: bucketed from {answer['original_candle_count']} candles", file=sys.stderr)
    series = answer["candles"]
    if resolution == "DAY" and series:
        # The archive's forming DAY candle can stand still at its first hour, or not exist yet: the days from the
        # last one on are rebuilt from H1, one candle per session, so two sessions are never merged into one.
        hours = json.loads(call("market", "get_candles", {**query, "resolution": "HOUR", "from_iso": series[-1]["time"]}))
        days: dict[str, list[dict]] = {}
        for c in hours["candles"]:
            days.setdefault(session_date(c["time"]), []).append(c)
        rebuilt = [{"time": f"{day}T00:00:00Z", "open": h[0]["open"], "high": max(c["high"] for c in h),
                    "low": min(c["low"] for c in h), "close": h[-1]["close"]} for day, h in sorted(days.items())]
        if rebuilt:
            series = series[:-1] + rebuilt
    return series


def svg(args: argparse.Namespace) -> None:
    series = candles(args.symbol, args.resolution, args.start, args.end)
    items = [i for i in load(args.levels) if args.chart in i.get("charts", [])]
    lows = [c["low"] for c in series]
    highs = [c["high"] for c in series]
    lo = args.ymin if args.ymin is not None else min(lows)
    hi = args.ymax if args.ymax is not None else max(highs)
    pad = (hi - lo) * 0.04
    lo, hi = lo - pad, hi + pad

    def y(price: float) -> float:
        return Y1 - (price - lo) / (hi - lo) * (Y1 - Y0)

    step = (X1 - X0) / len(series)
    times = [datetime.fromisoformat(c["time"].replace("Z", "+00:00")) for c in series]

    def x(index: int) -> float:
        return X0 + step * (index + 0.5)

    def x_at(moment: str | None) -> float:
        if not moment:
            return X0
        when = datetime.fromisoformat(moment.replace("Z", "+00:00"))
        return next((x(i) - step / 2 for i, t in enumerate(times) if t >= when), X1)

    out = [f'<svg viewBox="0 0 1000 560" role="img" aria-label="{args.aria}">',
           '<g font-family="Roboto Mono, monospace" font-size="11">']
    grid = next(g for g in (100, 200, 250, 500, 1000, 2000, 2500, 5000) if (hi - lo) / g <= 14)
    level = (int(lo // grid) + 1) * grid
    while level < hi:
        out.append(f'<line x1="{X0}" x2="{X1}" y1="{y(level):.1f}" y2="{y(level):.1f}" stroke="{GRID}"/>')
        out.append(f'<text x="{X0 - 6}" y="{y(level) + 4:.1f}" fill="{AXIS}" text-anchor="end">{pts(level)}</text>')
        level += grid

    daily = args.resolution in ("DAY", "WEEK")
    last_tick = -99.0
    # The index CFD's session opens at 23:00 UTC (22:00 in summer): that candle already belongs to the next day.
    sessions = [t if daily else t + timedelta(hours=2) for t in times]
    for i, t in enumerate(sessions):
        new = i > 0 and ((t.month != sessions[i - 1].month) if daily else (t.date() != sessions[i - 1].date()))
        if not new or x(i) - last_tick < 42:
            continue
        last_tick = x(i)
        text = MONTHS[t.month - 1] if daily else f"{t.day}.{t.month}"
        out.append(f'<line x1="{x(i):.1f}" x2="{x(i):.1f}" y1="{Y0}" y2="{Y1}" stroke="#f1efe7"/>')
        out.append(f'<text x="{x(i):.1f}" y="546" fill="{AXIS}" text-anchor="middle">{text}</text>')

    labels: list[tuple[float, str, str]] = []
    for item in items:
        d = item["draw"]
        colour = PALETTE.get(d.get("color", ""), NAVY)
        if d["kind"] == "zone":
            top, bottom = min(d["top"], hi), max(d["bottom"], lo)
            if top <= bottom:
                print(f"off the figure: {item['short']}", file=sys.stderr)
                continue
            left, right = x_at(d.get("from")), (x_at(d["to"]) if d.get("to") else X1)
            out.append(f'<rect x="{left:.1f}" y="{y(top):.1f}" width="{right - left:.1f}" '
                       f'height="{y(bottom) - y(top):.1f}" fill="{colour}" opacity="0.15"/>')
            labels.append(((y(top) + y(bottom)) / 2, f'{pts(d["bottom"])}–{pts(d["top"])} {item["short"]}', colour))
        elif d["kind"] == "level":
            if not lo <= d["price"] <= hi:
                print(f"off the figure: {item['short']}", file=sys.stderr)
                continue
            out.append(f'<line x1="{x_at(d.get("at")):.1f}" x2="{X1}" y1="{y(d["price"]):.1f}" '
                       f'y2="{y(d["price"]):.1f}" stroke="{colour}" stroke-width="1.5" stroke-dasharray="6 4"/>')
            labels.append((y(d["price"]), f'{pts(d["price"])} {item["short"]}', colour))

    body = max(1.0, step * 0.62)
    for i, c in enumerate(series):
        colour = UP if c["close"] >= c["open"] else DOWN
        top, bottom = y(max(c["open"], c["close"])), y(min(c["open"], c["close"]))
        out.append(f'<line x1="{x(i):.1f}" x2="{x(i):.1f}" y1="{y(c["high"]):.1f}" y2="{y(c["low"]):.1f}" '
                   f'stroke="{colour}" stroke-width="1"/>')
        out.append(f'<rect x="{x(i) - body / 2:.1f}" y="{top:.1f}" width="{body:.1f}" '
                   f'height="{max(1.0, bottom - top):.1f}" fill="{colour}"/>')

    last = series[-1]["close"]
    out.append(f'<line x1="{X0}" x2="{X1}" y1="{y(last):.1f}" y2="{y(last):.1f}" stroke="{NAVY}" '
               'stroke-width="1" stroke-dasharray="2 3"/>')
    out.append(f'<rect x="692" y="{y(last) - 8:.1f}" width="50" height="16" fill="{NAVY}"/>')
    out.append(f'<text x="717" y="{y(last) + 4:.1f}" fill="#fff" text-anchor="middle" font-weight="700">{pts(last)}</text>')

    # Captions keep their order and are pushed apart, so two near levels never print on top of each other.
    labels.sort(key=lambda label: label[0])
    placed: list[float] = []
    for want, _, _ in labels:
        placed.append(max(want, (placed[-1] + 14) if placed else Y0 + 8))
    overflow = placed[-1] - (Y1 - 4) if placed else 0
    if overflow > 0:
        placed = [p - overflow for p in placed]
        for i in range(len(placed) - 2, -1, -1):
            placed[i] = min(placed[i], placed[i + 1] - 14)
    for (_, text, colour), at in zip(labels, placed, strict=True):
        if len(text) > 36:
            print(f"caption runs off the figure, shorten `short`: {text}", file=sys.stderr)
        out.append(f'<text x="750" y="{at + 4:.1f}" fill="{colour}" font-weight="700">{text}</text>')

    out.append(f'<rect x="{X0}" y="{Y0}" width="{X1 - X0}" height="{Y1 - Y0}" fill="none" stroke="#ddd9cd"/>')
    out.append("</g></svg>")
    sys.stdout.reconfigure(encoding="utf-8")
    print("\n".join(out))
    print(f"{len(series)} candles {series[0]['time']} → {series[-1]['time']}, last {last}", file=sys.stderr)


def assemble(args: argparse.Namespace) -> None:
    head = (Path(__file__).parent.parent / "assets" / "head.html").read_text(encoding="utf-8")
    page = head.replace("@@TITLE@@", args.title) + Path(args.body).read_text(encoding="utf-8")
    for pair in args.fig:
        name, path = pair.split("=", 1)
        page = page.replace(f"@@{name}@@", Path(path).read_text(encoding="utf-8").strip())
    if "@@" in page:
        sys.exit("a placeholder was left unfilled")
    Path(args.out).write_text(page, encoding="utf-8", newline="\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("payload")
    p.add_argument("levels")
    p.add_argument("--symbol", default="US100")
    p.add_argument("--remove", default="")
    p.set_defaults(run=payload)
    a = sub.add_parser("assemble", help="the article: house head + body, each @@FIGn@@ replaced by its SVG")
    a.add_argument("body")
    a.add_argument("--title", required=True, help="2-4 words, the <title>")
    a.add_argument("--fig", action="append", default=[], help="FIG1=path/to/fig1.svg")
    a.add_argument("--out", required=True)
    a.set_defaults(run=assemble)
    s = sub.add_parser("svg")
    s.add_argument("levels")
    s.add_argument("--chart", required=True, help="which figure: items whose `charts` name it are drawn")
    s.add_argument("--symbol", default="US100")
    s.add_argument("--resolution", default="HOUR")
    s.add_argument("--from", dest="start", required=True)
    s.add_argument("--to", dest="end")
    s.add_argument("--ymin", type=float)
    s.add_argument("--ymax", type=float)
    s.add_argument("--aria", required=True)
    s.set_defaults(run=svg)
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")  # a Windows console's cp1250 cannot print − and ±
    sys.stderr.reconfigure(encoding="utf-8")
    args.run(args)


if __name__ == "__main__":
    main()

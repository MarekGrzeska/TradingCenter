# /// script
# requires-python = ">=3.10"
# dependencies = ["youtube-transcript-api>=1.0", "httpx>=0.27"]
# ///
"""Does YouTube hand captions to this machine's address? The test of tasks.md 0.2, runnable on any machine with `uv`:

    uv run yt_ip_test.py                       # ten well-known videos with captions
    uv run yt_ip_test.py --videos ids.txt      # your own: one video id (or watch URL) per line

Each video ends in exactly one verdict, because the whole point is telling *the address is refused* from *the video has
no captions*:

  ok           captions came back
  blocked      YouTube refused this address (RequestBlocked / IpBlocked) — the thing being measured
  no_captions  the video has none, or has them disabled — says nothing about the address
  unavailable  private, removed or region-locked video
  error        anything else; the message is printed

Run it twice, a day apart, on the machine you are judging: a block can arrive after the first requests. The exit code is
0 when every video that *has* captions came back, 1 when any was blocked, 2 when nothing could be judged."""

from __future__ import annotations

import argparse
import json
import re
import sys
import time

import httpx
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    IpBlocked,
    NoTranscriptFound,
    RequestBlocked,
    TranscriptsDisabled,
    VideoUnavailable,
    VideoUnplayable,
)

# Public videos that carried captions when this was written (all but one answered from a home address on 14 October 2026).
# A miss here is a video that changed, not an address that failed — which is why the verdicts keep the two apart.
DEFAULT_VIDEOS = [
    "dQw4w9WgXcQ",
    "UF8uR6Z6KLc",
    "arj7oStGLkU",
    "8jPQjjsBbIc",
    "iG9CE55wbtY",
    "ZXsQAXx_ao0",
    "H14bBuluwB8",
    "9bZkp7q19f0",  # answered "no captions" in English or Polish; kept as the control for that verdict
    "kJQP7kiw5Fk",
    "RgKAFK5djSk",
]


def video_id(text: str) -> str | None:
    text = text.strip()
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", text):
        return text
    found = re.search(r"(?:v=|youtu\.be/|shorts/)([A-Za-z0-9_-]{11})", text)
    return found.group(1) if found else None


def where_am_i() -> str:
    """The address and who owns it — enough to say afterwards which provider's range the verdicts belong to."""
    try:
        data = httpx.get("https://ipinfo.io/json", timeout=10).json()
        return f"{data.get('ip')} ({data.get('org')}, {data.get('city')}, {data.get('country')})"
    except Exception as err:  # noqa: BLE001 - this line is a label, not part of the measurement
        return f"unknown ({type(err).__name__})"


def verdict(api: YouTubeTranscriptApi, vid: str) -> tuple[str, str]:
    try:
        fetched = api.fetch(vid, languages=["en", "pl", "en-US", "en-GB"])
        return "ok", f"{len(fetched)} snippets"
    except (RequestBlocked, IpBlocked) as err:
        return "blocked", type(err).__name__
    except (TranscriptsDisabled, NoTranscriptFound) as err:
        return "no_captions", type(err).__name__
    except (VideoUnavailable, VideoUnplayable) as err:
        return "unavailable", type(err).__name__
    except Exception as err:  # noqa: BLE001 - reported, never swallowed: an unclassified failure is a finding
        return "error", f"{type(err).__name__}: {str(err)[:160]}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--videos", help="a file with one video id or URL per line")
    parser.add_argument("--pause", type=float, default=3.0, help="seconds between videos (default 3)")
    parser.add_argument("--json", action="store_true", help="one JSON object per line instead of text")
    args = parser.parse_args()

    if args.videos:
        with open(args.videos, encoding="utf-8") as handle:
            ids = [i for i in (video_id(line) for line in handle) if i]
    else:
        ids = DEFAULT_VIDEOS
    if not ids:
        print("no video ids to test", file=sys.stderr)
        return 2

    label = where_am_i()
    print(f"from {label}", file=sys.stderr)
    api = YouTubeTranscriptApi()
    results = []
    for index, vid in enumerate(ids):
        if index:
            time.sleep(args.pause)
        kind, detail = verdict(api, vid)
        results.append(kind)
        line = {"video": vid, "verdict": kind, "detail": detail}
        print(json.dumps(line) if args.json else f"{vid:<13} {kind:<12} {detail}")

    counts = {kind: results.count(kind) for kind in sorted(set(results))}
    judged = results.count("ok") + results.count("blocked")
    print(f"\n{label}\n{counts}", file=sys.stderr)
    if judged == 0:
        print("nothing could be judged: no video with captions answered either way", file=sys.stderr)
        return 2
    return 1 if results.count("blocked") else 0


if __name__ == "__main__":
    raise SystemExit(main())

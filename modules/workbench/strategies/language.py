"""The language, described from the registry the validator checks against — so the two cannot disagree. One description
for `GET /language` and for the tool that hands it to a model."""

from __future__ import annotations

from . import vocabulary as v
from .archive import Archive, ArchiveUnavailable
from .contract import LanguageOut
from .document import SCHEMA_VERSION, DocumentIn

CONSTRUCTIONS = [
    "numbers, True/False", "names", "+ - * /", "unary -", "< <= > >= == != (chained: 7 <= hour < 20)",
    "and, or, not", "a if test else b", "function(args) — the language's and the catalogue's", "p.name — a parameter",
    "indicator(…).line — one line of a multi-line indicator", "x[n] — n bars back, n ≥ 0",
    "x @ RESOLUTION, x @ INSTRUMENT, x @ \"INSTRUMENT\" — read elsewhere, visible from when it was available",
]


async def describe(archive: Archive) -> LanguageOut:
    try:
        catalogue = await archive.catalogue()
        indicators = [
            {"id": e.id, "signature": e.signature(), "lines": list(e.lines)}
            for e in sorted(catalogue.values(), key=lambda e: e.id)
            # The validator's own rule: a built-in function wins over a catalogue entry of the same name.
            if e.output == "lines" and e.id not in v.FUNCTIONS
        ]
    except ArchiveUnavailable:
        indicators = None
    return LanguageOut.model_validate({
        "schema_version": SCHEMA_VERSION,
        "sections": [field.alias or name for name, field in DocumentIn.model_fields.items()],
        "constructions": CONSTRUCTIONS,
        "series": v.SERIES,
        "time": v.TIME,
        "constants": v.CONSTANTS,
        "position": v.POSITION,
        "history": v.HISTORY,
        "resolutions": list(v.RESOLUTIONS),
        "sessions": {
            name: f"{s.zone} {s.opens // 60:02d}:{s.opens % 60:02d}–{s.closes // 60:02d}:{s.closes % 60:02d} local time, "
            "Monday to Friday; no exchange holidays"
            for name, s in v.SESSIONS.items()
        },
        "functions": [
            {
                "name": fn.name, "signature": fn.signature(), "description": fn.description,
                "places": None if fn.places is None else sorted(p.value for p in fn.places),
            }
            for fn in v.FUNCTIONS.values()
        ],
        "indicators": indicators,
        "max_bars": v.MAX_BARS,
    })

"""The language, described from the registry the validator checks against — so the two cannot disagree."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from .. import vocabulary as v
from ..archive import ArchiveUnavailable
from ..contract import LanguageOut
from ..document import SCHEMA_VERSION, DocumentIn
from .deps import archive

router = APIRouter(tags=["language"])

CONSTRUCTIONS = [
    "numbers, True/False", "names", "+ - * /", "unary -", "< <= > >= == != (chained: 7 <= hour < 20)",
    "and, or, not", "a if test else b", "function(args) — the language's and the catalogue's", "p.name — a parameter",
    "indicator(…).line — one line of a multi-line indicator", "x[n] — n bars back, n ≥ 0",
    "x @ RESOLUTION, x @ INSTRUMENT, x @ \"INSTRUMENT\" — read elsewhere, visible from when it was available",
]


@router.get("/language", response_model=LanguageOut)
async def language(reading=Depends(archive)) -> LanguageOut:
    try:
        catalogue = await reading.catalogue()
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

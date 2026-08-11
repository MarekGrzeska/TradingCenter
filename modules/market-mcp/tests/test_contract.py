"""Every field this module reads off market-data's wire, checked against the
committed snapshot rather than assumed — specs/market-mcp-upstream-access,
"Kontrakt archiwum jest sprawdzany, nie zakładany". No running market-data needed:
the snapshot is a file, and that is the point (`scripts/contract.py`'s docstring).

A field this module starts reading and forgets to add here is a gap this test does
not catch — the reverse (a field removed from market-data that this module still
reads) is what it exists for.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.contract

SNAPSHOT = Path(__file__).resolve().parent.parent / "contract" / "market-data.openapi.json"

# Every schema this module parses (upstream.py, tools/indicators.py) and every field
# read from it. Not every field the schema publishes — only what a KeyError would
# actually reach if it went missing.
READ_FIELDS = {
    "CandlesOut": {"symbol", "resolution", "derived", "candles", "uncovered"},
    "CandleOut": {"time", "open", "high", "low", "close", "volume"},
    "Uncovered": {"from", "to"},
    "PairCoverageOut": {"symbol", "resolution", "ranges", "earliest_reachable"},
    "CoverageOut": {"from", "to", "history_ended"},
    "TrackedPairOut": {"symbol", "resolution", "collection", "candle_count", "latest_candle"},
    "IndicatorsCatalogueOut": {"algorithm_version", "indicators"},
    "IndicatorCatalogueEntryOut": {
        "id",
        "name",
        "aliases",
        "group",
        "output",
        "params",
        "lines",
        "render",
        "warmup_kind",
    },
    "IndicatorParamOut": {"name", "type", "default", "min", "max"},
    "IndicatorLineSpecOut": {"key", "label", "style"},
    "IndicatorRenderOut": {"pane", "style", "scale", "autoscale", "levels"},
    "IndicatorsOut": {
        "symbol",
        "resolution",
        "derived",
        "algorithm_version",
        "times",
        "uncovered",
        "results",
    },
    "IndicatorResultOut": {
        "id",
        "params",
        "warmup_bars",
        "settled",
        "error",
        "lines",
        "markers",
        "zones",
        "levels",
    },
    "IndicatorMarkerOut": {"time", "label", "price"},
    "IndicatorZoneOut": {"from", "to", "top", "bottom", "direction", "touched_at", "filled_at"},
    "IndicatorLevelOut": {"from", "price", "label", "count"},
}

# Every path a tool or resource calls. `/instruments/search` is deliberately absent:
# market-data forwards the gateway's own JSON unread and publishes no schema for it
# (`market_data/routers/instruments.py` — no `response_model`), so there is nothing
# here for this test to check beyond the path itself existing.
READ_PATHS = {
    "/candles/{symbol}": {"get"},
    "/coverage/{symbol}": {"get"},
    "/pairs": {"get"},
    "/instruments/search": {"get"},
    "/indicators": {"get"},
    "/indicators/{symbol}": {"post"},
}


def _schema() -> dict:
    return json.loads(SNAPSHOT.read_text(encoding="utf-8"))


def test_snapshot_exists() -> None:
    assert SNAPSHOT.exists(), (
        f"{SNAPSHOT} is missing — run `uv run python scripts/contract.py generate`."
    )


def test_every_read_path_is_published() -> None:
    schema = _schema()
    for path, methods in READ_PATHS.items():
        assert path in schema["paths"], f"market-data no longer publishes {path}"
        for method in methods:
            assert method in schema["paths"][path], f"{path} no longer has a {method.upper()}"


def test_every_read_field_is_published() -> None:
    schema = _schema()
    schemas = schema["components"]["schemas"]
    for model_name, fields in READ_FIELDS.items():
        assert model_name in schemas, f"market-data no longer publishes {model_name}"
        published = set(schemas[model_name].get("properties", {}).keys())
        missing = fields - published
        assert not missing, f"{model_name} no longer publishes: {sorted(missing)}"

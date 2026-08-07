"""Getting candles into the archive and keeping them coming.

Two modes, because the provider offers two. The stream carries what is happening now and
is the only way to catch a candle as it closes; `/history` carries what already happened
and is the only way to recover from not having been listening. Neither alone is an
archive: the stream cannot fill in the hour the process was restarting, and history alone
would mean polling.
"""

from .backfill import MAX_BARS_PER_FILL, FillOutcome, bars_to_close_gap, fill_gap
from .live import Backoff, PairIngest
from .supervisor import Ingest

__all__ = [
    "MAX_BARS_PER_FILL",
    "Backoff",
    "FillOutcome",
    "Ingest",
    "PairIngest",
    "bars_to_close_gap",
    "fill_gap",
]

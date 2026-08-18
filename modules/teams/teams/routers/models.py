"""`GET /models` — the catalogue a wybierak is built from, and nothing else
(specs/teams-models, "Katalog modeli wystarcza do zbudowania wybieraka").

The route body is `tc_runtime.routers.models_router`; what this module supplies is its own
`ModelOut`, which is the only thing that differed from agent's copy.
"""

from __future__ import annotations

from tc_runtime.routers import models_router

from ..contract import ModelOut

router = models_router(ModelOut)

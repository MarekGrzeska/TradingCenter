"""Running a saved revision: the graph it compiles to, one agent's own loop, and the
engine that writes the trace while both happen.

The split is by what each part is allowed to know. `graph.py` knows the shape of a team
and nothing about models or databases; `loop.py` knows one agent's model-and-tools
exchange and nothing about the team around it; `engine.py` is where the database, the
statuses, the time limit and whoever is watching all meet.
"""

from __future__ import annotations

from .engine import (
    RunEvent,
    RunFinished,
    RunRegistry,
    StepFinished,
    StepStarted,
    ToolCalled,
    execute_run,
)
from .graph import AgentFailed, compile_team
from .loop import ROUND_CEILING, AgentWork, RecordedCall, run_agent
from .starter import start_run_on_revision

__all__ = [
    "ROUND_CEILING",
    "AgentFailed",
    "AgentWork",
    "RecordedCall",
    "RunEvent",
    "RunFinished",
    "RunRegistry",
    "StepFinished",
    "StepStarted",
    "ToolCalled",
    "compile_team",
    "execute_run",
    "run_agent",
    "start_run_on_revision",
]

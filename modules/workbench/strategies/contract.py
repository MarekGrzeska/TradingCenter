"""The shapes this package answers with. Refusals name themselves and carry every problem, never a database error."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

RunStatus = Literal["queued", "running", "done", "failed", "cancelled"]


class ProblemOut(BaseModel):
    path: str = Field(description="where in the document or request, e.g. `entries[0].when`")
    message: str
    column: int | None = Field(description="1-based character in the formula, when the problem is in one")
    hint: str | None = Field(description="the nearest known name, or what to write instead")


class ProblemsOut(BaseModel):
    detail: str
    problems: list[ProblemOut]


class RunAcceptedOut(BaseModel):
    id: int
    strategy_id: int
    revision: int = Field(description="the revision the run is of — the latest at the moment it was asked, if none was named")
    status: RunStatus


class RunCancelledOut(BaseModel):
    id: int
    status: RunStatus = Field(description="the status after the request")
    was: RunStatus = Field(description="the status the run had when the cancellation arrived")


class RunOut(BaseModel):
    id: int
    strategy_id: int
    revision: int
    status: RunStatus
    reason: str | None
    engine_version: int | None
    request: dict
    queued_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    report: dict | None
    provenance: dict | None

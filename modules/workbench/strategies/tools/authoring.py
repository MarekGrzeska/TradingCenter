"""Writing a strategy: the language, what exists, a document checked, a draft put into the operator's editor, a revision
saved. Saving is the same check and the same store as `POST /strategies` — only the author differs."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

from .. import changes, costs_store, documents, drafts, runs, store
from ..archive import ArchiveUnavailable
from ..language import describe
from ..summary import summarize
from ._shared import READ_ONLY, WRITES, ToolContext, refusal

RECENT_RUNS = 5

HOW_TO_WRITE = [
    "A document is JSON with the sections listed; formulas are strings in Python's expression syntax.",
    "One instrument per strategy, and that instrument must have its MINUTE series collected.",
    "exits.stop is required: it is what 1 R measures.",
    "Hours and weekdays are UTC.",
    (
        "When the operator's description leaves a value open (which hours a session is, what a trend is), ask, or "
        "choose and write the assumption into `notes` — never leave it unsaid."
    ),
    "Write `name`, `hypothesis` and `notes` in Polish — the operator reads them; formulas keep the language's names.",
    (
        "Put every change into the operator's editor with draft_strategy, which saves no revision; save_strategy only "
        "when the operator asks to save."
    ),
    "A draft or a save lists every problem at once with its path, column and hint. Fix them all, then draft again.",
    "Compare the summary in the answer with what the operator described before you reply.",
]


class StrategyItem(BaseModel):
    id: int
    name: str
    symbol: str
    timeframe: str
    latest_revision: int
    latest_author: str
    changed_at: datetime
    trials: int = Field(description="finished runs of every revision")
    archived: bool


class StrategiesOut(BaseModel):
    strategies: list[StrategyItem]


class RunLine(BaseModel):
    run_id: int
    revision: int
    status: str
    requested_by: str
    headline: dict[str, Any] | None


class StrategyRead(BaseModel):
    strategy_id: int
    revision: int
    latest_revision: int
    author: str
    document: dict[str, Any]
    summary: dict[str, Any] | None
    trials: int
    has_cost_profile: bool = Field(description="false: run_backtest reads the instrument's costs off the broker first")
    recent_runs: list[RunLine]


class ValidationResult(BaseModel):
    valid: bool
    problems: list[dict[str, Any]]
    summary: dict[str, Any] | None


class DraftResult(BaseModel):
    valid: bool
    problems: list[dict[str, Any]]
    summary: dict[str, Any] | None
    next_step: str = "The operator sees this draft in the editor, unsaved. Fix any problem with another draft."


class SaveResult(BaseModel):
    strategy_id: int
    revision: int
    created: bool = Field(description="false when the content equalled the latest revision, which is then the answer")
    summary: dict[str, Any] | None
    changes: list[dict[str, Any]] = Field(description="against the previous revision, by path; empty for a first one")
    next_step: str = "Tell the operator what changed. The Strategies tab shows this revision, its summary and its changes."


def register(mcp: FastMCP, ctx: ToolContext) -> None:
    @mcp.tool(annotations=READ_ONLY)
    async def strategy_language() -> dict[str, Any]:
        """The strategy document language: its sections, constructions, names, the language's functions and the
        archive's indicators as functions, and how to write a document. Read it before writing or changing one."""
        language = await describe(ctx.state.archive)
        return {"language": language.model_dump(mode="json"), "how_to_write": HOW_TO_WRITE}

    @mcp.tool(annotations=READ_ONLY)
    async def list_strategies(archived: bool = False) -> StrategiesOut:
        """The operator's strategies, last changed first, with instrument, decision interval, latest revision and how
        many runs each has had. `archived=true` lists only the archived ones."""
        async with ctx.state.pool.acquire() as conn:
            found = await store.list_strategies(conn, archived=archived)
        return StrategiesOut(strategies=[
            StrategyItem(**{k: getattr(s, k) for k in StrategyItem.model_fields if k != "archived"},
                         archived=s.archived_at is not None)
            for s in found
        ])

    @mcp.tool(annotations=READ_ONLY)
    async def read_strategy(strategy_id: int, revision: int | None = None) -> StrategyRead:
        """One strategy's document (the latest revision unless one is named), its summary, its trials, whether its
        instrument has a cost profile, and its last runs. Read it before changing a strategy, and pass the revision you
        read as `based_on` to save_strategy."""
        async with ctx.state.pool.acquire() as conn:
            try:
                summary = await store.get_strategy(conn, strategy_id)
                found = await store.get_revision(conn, strategy_id, revision)
            except store.NotFound:
                raise refusal(f"strategy {strategy_id} has no revision {revision or ''}".strip()) from None
            profile = await costs_store.get(conn, found.document["symbol"])
            recent = await runs.list_runs(conn, strategy_id, 0, RECENT_RUNS)
        return StrategyRead(
            strategy_id=strategy_id, revision=found.n, latest_revision=summary.latest_revision, author=found.author,
            document=found.document, summary=summarize(found.document), trials=summary.trials,
            has_cost_profile=profile is not None,
            recent_runs=[
                RunLine(run_id=r["id"], revision=r["revision"], status=r["status"], requested_by=r["requested_by"],
                        headline=store.decoded(r["headline"]))
                for r in recent
            ],
        )

    @mcp.tool(annotations=READ_ONLY)
    async def validate_strategy(document: dict[str, Any]) -> ValidationResult:
        """Checks a strategy document exactly as saving would, and saves nothing: every problem with its path, column and
        hint, and the document's summary when it passes. save_strategy checks too — use this to check without a revision."""
        checked, problems = await _check(ctx, document)
        return ValidationResult(
            valid=checked is not None, problems=[p.as_dict() for p in problems],
            summary=None if checked is None else summarize(checked.canonical),
        )

    @mcp.tool(annotations=WRITES)
    async def draft_strategy(document: dict[str, Any], strategy_id: int | None = None) -> DraftResult:
        """Puts a document into the operator's editor on the Strategies tab as unsaved text — of strategy `strategy_id`,
        or without it of the new strategy not saved yet. No revision and no trial; it replaces the previous draft and is
        kept even with problems, which come back all at once. Use it for every change; the operator saves."""
        checked, problems = await _check(ctx, document)
        async with ctx.state.pool.acquire() as conn:
            if strategy_id is not None:
                try:
                    await store.get_strategy(conn, strategy_id)
                except store.NotFound:
                    raise refusal(f"strategy {strategy_id} does not exist") from None
            await drafts.put(conn, strategy_id, document)
        return DraftResult(
            valid=checked is not None, problems=[p.as_dict() for p in problems],
            summary=None if checked is None else summarize(checked.canonical),
        )

    @mcp.tool(annotations=WRITES)
    async def save_strategy(
        document: dict[str, Any], strategy_id: int | None = None, based_on: int | None = None
    ) -> SaveResult:
        """Saves a strategy document as a new strategy, or — with `strategy_id` — as its next revision, authored by you,
        when the operator asks to save; until then changes go in with draft_strategy.
        A revision is never changed afterwards; the operator undoes one by restoring an earlier revision.

        With `strategy_id`, `based_on` is required: the revision you read and changed. If someone saved after it, the save
        is refused with the latest revision's number — read it again and redo your change on it.

        Every assumption the operator did not state goes into `notes`. A document with problems is not saved and every
        problem comes back at once. Compare the returned summary with what the operator described before you answer."""
        if strategy_id is not None and based_on is None:
            raise refusal("pass based_on: the revision you read with read_strategy and changed")
        checked, problems = await _check(ctx, document)
        if checked is None:
            raise refusal("the document is not a valid strategy; nothing was saved", problems)
        pool = ctx.state.pool
        if strategy_id is None:
            saved = await store.create(pool, checked, "agent")
        else:
            try:
                saved = await store.save_revision(pool, strategy_id, checked, "agent", based_on)
            except store.NotFound:
                raise refusal(f"strategy {strategy_id} does not exist") from None
            except store.Conflict as err:
                raise refusal(
                    f"revision {err.latest} was saved after revision {based_on}; read it with read_strategy and redo "
                    "the change on it — nothing was saved"
                ) from None
        found: list[dict[str, Any]] = []
        if saved.revision > 1:
            async with pool.acquire() as conn:
                previous = await store.get_revision(conn, saved.strategy_id, saved.revision - 1)
            found = [c.as_dict() for c in changes.between(previous.document, checked.canonical)]
        return SaveResult(
            strategy_id=saved.strategy_id, revision=saved.revision, created=saved.created,
            summary=summarize(checked.canonical), changes=found if saved.created else [],
        )


async def _check(ctx: ToolContext, document: dict[str, Any]):
    try:
        return await documents.check(document, ctx.state.archive)
    except ArchiveUnavailable as err:
        raise refusal(f"the document cannot be checked now: {err}") from err

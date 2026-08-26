"""Rules the operator wrote, and the revisions they went through. Every write here is checked before it
is written — against this image's catalogue and against the archive's.

Nothing here starts anything: a watch is pinned to the revision it was started with, because a rule
swapped underfoot produces decisions that look comparable and are not."""

from __future__ import annotations

from fastapi import APIRouter, Request

from .. import store
from ..catalogue import get as coded_entry
from ..contract import (
    DefinitionIn,
    DefinitionOut,
    DefinitionPatch,
    RevisionIn,
    RevisionOut,
)
from ..errors import (
    ArchiveRefused,
    ArchiveUnreachable,
    DefinitionRefused,
    UnknownDefinition,
    UnknownRevision,
    UnknownStrategy,
)
from ..rule import RuleDefinition
from ..rule_validation import check

router = APIRouter()


async def _checked(request: Request, rule: RuleDefinition) -> None:
    """Refuse the rule now, against what the archive actually announces. An archive that cannot be asked
    means the write is refused, not waved through — and the refusal keeps the archive's own status."""
    try:
        catalogue = await request.app.state.archive.announced_catalogue()
    except ArchiveUnreachable as err:
        raise ArchiveUnreachable(
            f"this rule was not saved: its indicators could not be checked, because {err}"
        ) from err
    except ArchiveRefused as err:
        raise ArchiveRefused(
            f"this rule was not saved: its indicators could not be checked, because {err}"
        ) from err
    check(rule, catalogue)


def _definition_out(row: store.StrategyDefinition) -> DefinitionOut:
    return DefinitionOut(**vars(row))


def _revision_out(row: store.StrategyRevision) -> RevisionOut:
    # Parsed back into the vocabulary rather than handed over as the stored blob: what this route
    # publishes is a rule, and a revision this image cannot read is something the caller learns here.
    return RevisionOut(
        id=row.id,
        strategy_id=row.strategy_id,
        version=row.version,
        definition=RuleDefinition.model_validate(row.definition),
        created_at=row.created_at,
    )


@router.get("/definitions", tags=["definitions"])
async def list_definitions(request: Request) -> list[DefinitionOut]:
    """Every rule that was written down. The coded entries are not here — they are in
    `/strategies`, which lists both, and this route is about what can be edited."""
    async with request.app.state.pool.acquire() as conn:
        rows = await store.list_definitions(conn)
    return [_definition_out(row) for row in rows]


@router.post("/definitions", tags=["definitions"], status_code=201)
async def add_definition(request: Request, body: DefinitionIn) -> RevisionOut:
    """A new rule and its first revision.

    Answers with the revision rather than the definition, because the revision is the thing
    anything else points at: a watch pins one, a decision names one, and a caller that got
    only the definition back would have to ask again to do anything with it.
    """
    try:
        coded_entry(body.strategy_id)
    except UnknownStrategy:
        pass
    else:
        # One namespace, and reviewed code owns it. A row shadowing a coded entry would be
        # a strategy whose rule cannot be found by reading the repository.
        raise DefinitionRefused(
            f"{body.strategy_id!r} is already an entry in this image's catalogue; a written "
            "rule may not take an id that reviewed code carries"
        )
    await _checked(request, body.definition)

    async with request.app.state.pool.acquire() as conn:
        if await store.read_definition(conn, body.strategy_id) is not None:
            raise DefinitionRefused(
                f"a definition with id {body.strategy_id!r} already exists; write its next "
                "revision instead of a second definition under the same name"
            )
        _, revision = await store.add_definition(
            conn,
            strategy_id=body.strategy_id,
            name=body.name,
            description=body.description,
            definition=body.definition.model_dump(mode="json"),
        )
    return _revision_out(revision)


@router.get("/definitions/{strategy_id}", tags=["definitions"])
async def read_definition(request: Request, strategy_id: str) -> DefinitionOut:
    async with request.app.state.pool.acquire() as conn:
        row = await store.read_definition(conn, strategy_id)
    if row is None:
        raise UnknownDefinition(strategy_id)
    return _definition_out(row)


@router.patch("/definitions/{strategy_id}", tags=["definitions"])
async def rename_definition(
    request: Request, strategy_id: str, body: DefinitionPatch
) -> DefinitionOut:
    """The title and the sentence under it — never the rule.

    Editing the rule is a new revision, and this route deliberately cannot do it: a title
    fixed in place must not change what any recorded decision points at.
    """
    async with request.app.state.pool.acquire() as conn:
        row = await store.rename_definition(
            conn, strategy_id, name=body.name, description=body.description
        )
    if row is None:
        raise UnknownDefinition(strategy_id)
    return _definition_out(row)


@router.get("/definitions/{strategy_id}/revisions", tags=["definitions"])
async def list_revisions(request: Request, strategy_id: str) -> list[RevisionOut]:
    """Newest first. Nothing is ever removed from this list."""
    async with request.app.state.pool.acquire() as conn:
        if await store.read_definition(conn, strategy_id) is None:
            raise UnknownDefinition(strategy_id)
        rows = await store.list_revisions(conn, strategy_id)
    return [_revision_out(row) for row in rows]


@router.post("/definitions/{strategy_id}/revisions", tags=["definitions"], status_code=201)
async def add_revision(request: Request, strategy_id: str, body: RevisionIn) -> RevisionOut:
    """The next revision. The previous one stays exactly as it was, and so do its watches."""
    await _checked(request, body.definition)
    async with request.app.state.pool.acquire() as conn:
        revision = await store.add_revision(
            conn, strategy_id, body.definition.model_dump(mode="json")
        )
    if revision is None:
        raise UnknownDefinition(strategy_id)
    return _revision_out(revision)


@router.get("/definitions/{strategy_id}/revisions/{version}", tags=["definitions"])
async def read_revision(request: Request, strategy_id: str, version: int) -> RevisionOut:
    """One numbered revision, in the wording it had when it was written."""
    async with request.app.state.pool.acquire() as conn:
        revision = await store.read_revision_at(conn, strategy_id, version)
    if revision is None:
        raise UnknownRevision(strategy_id, version)
    return _revision_out(revision)

"""One place where a strategy id becomes a `StrategySpec`, whatever it was written in — and the only file
that knows there are two sources. A branch of the shape "if this one was configured" anywhere else would
mean the entry contract had not been enough.

One namespace, and the image wins it. A stored rule this image can no longer parse is a refusal rather
than a crash: a revision written by a later image is an ordinary consequence of a rollback."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import ValidationError

from . import store
from .catalogue import get as coded_entry
from .errors import StrategyError, UnknownRevision, UnknownStrategy
from .interpreter import spec_from_rule
from .rule import RuleDefinition
from .spec import StrategySpec
from .store import StrategyDefinition, StrategyRevision


@dataclass(frozen=True)
class Resolved:
    """A strategy ready to evaluate, and the revision it came from if it came from one.

    `revision is None` is the whole of "this one is code in the image" — recorded on every
    decision as a null, which means what it says rather than standing in for missing data.
    """

    spec: StrategySpec
    revision: StrategyRevision | None = None
    definition: StrategyDefinition | None = None

    @property
    def revision_id(self) -> int | None:
        return None if self.revision is None else self.revision.id

    @property
    def from_code(self) -> bool:
        return self.revision is None


def build(definition: StrategyDefinition, revision: StrategyRevision) -> Resolved:
    """One stored revision as an ordinary entry. Pure — no connection, no I/O."""
    return Resolved(
        spec=spec_from_rule(
            strategy_id=definition.strategy_id,
            name=definition.name,
            description=definition.description,
            rule=parse(revision),
        ),
        revision=revision,
        definition=definition,
    )


def parse(revision: StrategyRevision) -> RuleDefinition:
    try:
        return RuleDefinition.model_validate(revision.definition)
    except ValidationError as err:
        raise StrategyError(
            f"revision {revision.version} of {revision.strategy_id!r} cannot be read by this "
            f"image: {err.error_count()} problem(s), first at "
            f"{'.'.join(str(part) for part in err.errors()[0]['loc'])}"
        ) from err


async def resolve(
    conn,
    strategy_id: str,
    *,
    revision_id: int | None = None,
    version: int | None = None,
) -> Resolved:
    """The strategy behind an id, at a named revision or at its newest. Asking for a revision of a coded
    entry is refused rather than ignored: it is a caller that believes something untrue."""
    try:
        spec = coded_entry(strategy_id)
    except UnknownStrategy:
        pass
    else:
        if revision_id is not None or version is not None:
            raise StrategyError(
                f"{strategy_id!r} is an entry in this image's catalogue, so it has no "
                "revisions — its rule is in the repository, under that id"
            )
        return Resolved(spec=spec)

    definition = await store.read_definition(conn, strategy_id)
    if definition is None:
        raise UnknownStrategy(strategy_id)

    if revision_id is not None:
        revision = await store.read_revision(conn, revision_id)
        if revision is None or revision.strategy_id != strategy_id:
            raise UnknownRevision(strategy_id, revision_id)
    else:
        revision = await store.read_revision_at(conn, strategy_id, version)
        if revision is None:
            raise UnknownRevision(strategy_id, version or 0)
    return build(definition, revision)


async def resolve_watch(conn, watch: store.Watch) -> Resolved:
    """What one watch is actually computing — its pinned revision, never the newest. A definition may have
    moved on three times since, and none of it changes what the watch decides."""
    return await resolve(conn, watch.strategy_id, revision_id=watch.strategy_revision_id)


async def all_available(conn) -> list[Resolved]:
    """Every strategy this platform can run right now. A definition whose newest revision this image
    cannot read is left out rather than raising — the rest of the catalogue is unaffected."""
    from .catalogue import all_entries

    found = [Resolved(spec=spec) for spec in all_entries()]
    for definition in await store.list_definitions(conn):
        revision = await store.read_revision_at(conn, definition.strategy_id, None)
        if revision is None:
            continue
        try:
            found.append(build(definition, revision))
        except StrategyError:
            continue
    return found

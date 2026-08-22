"""The rules every strategy is subject to, wherever it came from.

The split this file exists to hold: **a rule that binds every strategy belongs here; a rule
one strategy might not want belongs in its entry.** The first is written once and tested
once. The second is what a catalogue is for. Getting it wrong in either direction is
expensive — a shared rule copied into entries drifts between them, and a strategy's own
opinion promoted to here quietly overrides strategies that disagreed.

Two gates today, and each names its own kind so a refusal can be read for what to do about
it: a gap in the data is answered by fetching history, a reward too small for the risk by
reading the strategy or moving the threshold.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from .archive import Gap
from .spec import Decision

# Which layer refused, as the decision records it. `strategy` is the entry's own answer;
# the other two are this file's.
ReasonKind = Literal["strategy", "coverage", "limit"]


@dataclass(frozen=True)
class Refusal:
    reason: str
    kind: ReasonKind


def coverage(gaps: Sequence[Gap]) -> Refusal | None:
    """Refuse when the range an evaluation stood on has stretches the archive never verified.

    An indicator computed across a gap looks exactly like one computed over real bars —
    the difference shows up in the accounting, months later. Refusing here costs one bar's
    decision and names the remedy: a backfill job, not a change to the strategy.
    """
    if not gaps:
        return None
    first = gaps[0]
    more = f" (and {len(gaps) - 1} more)" if len(gaps) > 1 else ""
    return Refusal(
        reason=(
            f"the archive has not verified {first.start.isoformat()}–{first.end.isoformat()}"
            f"{more}; a decision over an unverified stretch is a guess"
        ),
        kind="coverage",
    )


def reward_over_risk(decision: Decision, minimum: float) -> Refusal | None:
    """Refuse a trade whose reward does not cover its risk by the required multiple.

    Here rather than in an entry because it is the platform's floor, not a strategy's
    opinion: an entry may set a higher bar of its own, and none may set a lower one.
    """
    if decision.action != "trade" or decision.rr is None:
        return None
    if decision.rr >= minimum:
        return None
    return Refusal(
        reason=f"reward over risk is {decision.rr:.2f}, below the platform's floor of {minimum:.2f}",
        kind="limit",
    )


def apply(decision: Decision, refusals: Sequence[Refusal | None]) -> tuple[Decision, ReasonKind]:
    """The first refusal that bites, or the decision as the strategy made it.

    The first rather than all of them: a decision carries one reason, and the one worth
    carrying is the one that would have to be answered first.
    """
    for refusal in refusals:
        if refusal is not None:
            return decision.refused(refusal.reason), refusal.kind
    return decision, "strategy"

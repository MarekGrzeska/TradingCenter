"""Whether a rule's recipient and bot lead anywhere. One place, because three things ask: a save, the list of rules and the
state — and they must not disagree about what is wrong."""

from __future__ import annotations

from collections.abc import Mapping

from .contract import Defect

# Recipient name -> the bots it is reached through. `None` where there is no door to ask.
Reach = Mapping[str, tuple[str, ...]]


def defect_of(destination: str, bot: str | None, reach: Reach | None) -> Defect | None:
    """What is wrong with where a rule would tell, or `None`. A rule with no bot means the recipient's only bot, so it is
    wrong the moment the recipient has several — never guessed between."""
    if reach is None:
        return None
    bots = reach.get(destination)
    if bots is None:
        return Defect(field="destination", message=f"{destination!r} is not a recipient the door to Telegram knows")
    if not bots:
        return Defect(field="destination", message=f"{destination!r} is not bound through any bot yet")
    if bot is None:
        if len(bots) > 1:
            listed = ", ".join(f"@{one}" for one in bots)
            return Defect(field="bot", message=f"{destination!r} is reached through several bots ({listed}); choose one")
        return None
    if bot.lstrip("@") not in bots:
        return Defect(field="bot", message=f"{destination!r} is not reached through @{bot.lstrip('@')}")
    return None

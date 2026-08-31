"""The two tools this module serves at `/mcp`: write to somebody, and see who there is to write to.

The set is short because the boundary is: sending is the one act here a conversation can take back by
saying the next thing. A bot created or a destination bound outlives the conversation and belongs to
the operator, so both stay in the REST contract — the same line `polymarket-data` drew around deleting.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

from .. import sending, store
from ..errors import (
    GatewayError,
    NoSuchDestination,
    RateLimited,
    TelegramUnreachable,
)
from ._shared import READ_ONLY, SENDS, ToolContext

# What a model is told to do when there is nobody to write to. The operator's move, named in full:
# a bot may not open a conversation, so no amount of asking from here produces a destination.
BINDING_IS_THE_OPERATORS = (
    "the operator binds a destination through this gateway's REST contract (POST /destinations) "
    "and hands the start link to whoever is to receive the alerts — a Telegram bot cannot open a "
    "conversation, so somebody has to tap it. Nothing in this conversation can do it."
)


class Sent(BaseModel):
    """What Telegram said about a message it accepted, and the whole of what can ever be said about
    it: this gateway keeps nothing, so there is no tool that reads a message back."""

    destination: str
    message_id: int = Field(description="Telegram's own identifier for the delivered message")


class DestinationSummary(BaseModel):
    name: str = Field(description="pass this as `destination` to send_telegram_message")
    receives: bool = Field(
        description="false means nothing can be delivered there yet — either nobody has tapped "
        "its start link, or the recipient blocked the bot"
    )
    state: str = Field(description="pending, ready, or blocked")


def register(mcp: FastMCP, ctx: ToolContext) -> None:
    @mcp.tool(annotations=READ_ONLY)
    async def telegram_destinations() -> list[DestinationSummary]:
        """Who this gateway can write to, by name. Call this before sending.

        The names are the operator's own and cannot be guessed — and a destination that exists is
        not yet one that receives, which is what `receives` says.
        """
        async with ctx.pool.acquire() as conn:
            found = await store.list_destinations(conn)
        return [
            DestinationSummary(
                name=one.name, receives=one.receives, state=one.state.value
            )
            for one in found
        ]

    @mcp.tool(annotations=SENDS)
    async def send_telegram_message(destination: str, text: str) -> Sent | dict:
        """Send a Telegram message to a named destination, now.

        This is the one thing in this system a conversation does that is visible outside it. There
        is no queue and no retry: it is delivered while this call runs, or it is refused with
        Telegram's own answer. Sending twice sends twice — nothing here deduplicates.
        """
        async with ctx.pool.acquire() as conn:
            try:
                delivered = await sending.send(
                    conn,
                    ctx.telegram,
                    name=destination,
                    text=text,
                    max_chars=ctx.settings.max_message_chars,
                )
            except NoSuchDestination as err:
                # An empty gateway and a mistyped name are the same exception and not the same
                # answer: one is a name to correct, the other is a thing only the operator can do.
                if await store.count_destinations(conn) == 0:
                    return {
                        "refused": "this gateway has no destination bound yet, so there is "
                        "nobody to send to",
                        "do_first": BINDING_IS_THE_OPERATORS,
                    }
                return {
                    "refused": str(err),
                    "do_first": "telegram_destinations lists the names this gateway knows",
                }
            except GatewayError as err:
                return {
                    "refused": str(err),
                    "retryable": isinstance(err, RateLimited | TelegramUnreachable),
                }
        return Sent(destination=destination, message_id=delivered.message_id)

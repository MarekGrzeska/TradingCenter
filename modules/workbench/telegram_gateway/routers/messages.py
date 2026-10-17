"""Sending, which is the whole point of the module and one route.

It writes nothing about the message and answers with what Telegram said. There is deliberately no route asking
what was sent: `telegram-gateway-delivery` names that absence, and the caller's own marker is what replaces it.
What it does remember is that a purpose was used — a name, never a text.
"""

from __future__ import annotations

from fastapi import APIRouter, Request, status
from tc_runtime.caller_access import IN_PROCESS_CALLER

from .. import sending
from ..contract import Problem, SendRequest, Sent
from ..errors import GatewayError
from . import deps

router = APIRouter(tags=["messages"])


@router.post(
    "/messages",
    response_model=Sent,
    status_code=status.HTTP_200_OK,
    responses={
        404: {"model": Problem},
        409: {"model": Problem},
        422: {"model": Problem},
        429: {"model": Problem},
        502: {"model": Problem},
    },
)
async def send(request: Request, body: SendRequest) -> Sent:
    """One message, now — to a destination by name, or to whoever hears a purpose.

    Nothing is queued and nothing is retried here. A refusal carries Telegram's own answer — the wait
    on a rate limit, the block on a recipient who left — because the caller decides from it whether
    its "already told" marker may be recorded. A purpose nobody hears answers 409 with
    `code: "unassigned"`: not a fault, and the cue to leave that marker unset.
    """
    if (body.destination is None) == (body.purpose is None):
        raise deps.bad_request("give exactly one of `destination` and `purpose`")

    settings = request.app.state.settings
    async with deps.connection(request.app.state.pool) as conn:
        try:
            if body.purpose is not None:
                destination, delivered = await sending.send_to_purpose(
                    conn,
                    request.app.state.telegram,
                    purpose=body.purpose,
                    text=body.text,
                    max_chars=settings.max_message_chars,
                    caller=request.scope.get(IN_PROCESS_CALLER),
                )
                return Sent.of(destination.name, delivered, purpose=body.purpose)
            assert body.destination is not None  # the exactly-one check above
            delivered = await sending.send(
                conn,
                request.app.state.telegram,
                name=body.destination,
                text=body.text,
                max_chars=settings.max_message_chars,
            )
        except GatewayError as err:
            raise deps.refusal(err) from err
    return Sent.of(body.destination, delivered)

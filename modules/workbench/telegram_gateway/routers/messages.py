"""Sending, which is the whole point of the module and one route.

It writes nothing and answers with what Telegram said. There is deliberately no route asking what was
sent: `telegram-gateway-delivery` names that absence, and the caller's own marker is what replaces it.
"""

from __future__ import annotations

from fastapi import APIRouter, Request, status

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
    """One message to one named destination, now.

    Nothing is queued and nothing is retried here. A refusal carries Telegram's own answer — the wait
    on a rate limit, the block on a recipient who left — because the caller decides from it whether
    its "already told" marker may be recorded.
    """
    settings = request.app.state.settings
    async with deps.connection(request.app.state.pool) as conn:
        try:
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

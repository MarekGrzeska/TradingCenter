"""Reading an instrument's trading terms, and turning a deposit into a size. Measured 17 August 2026:
an agent read 2% of an account as contract value and tied up a twentieth of what was meant.

`size_for_margin` takes the price as an argument rather than reading one: a price fetched here would
be a second source inside one run, and the trace would not show which one the size was computed against."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel

from ..client import GatewayClient
from ..errors import ToolRefusal
from ._shared import READ_ONLY, _read

# The one unit this module knows how to compute with, and the only one capital.com has been observed
# sending. Anything else is refused by name: a multiplier read as a percentage is wrong by the leverage.
PERCENTAGE = "PERCENTAGE"


class InstrumentTermsOut(BaseModel):
    """What the provider will allow on one instrument. No price — see the module
    docstring."""

    symbol: str
    currency: str | None = None
    lot_size: float | None = None
    margin_factor: float | None = None
    margin_factor_unit: str | None = None
    min_deal_size: float | None = None
    max_deal_size: float | None = None
    size_increment: float | None = None


class SizeForMarginOut(BaseModel):
    """A size that fits both the deposit asked for and the provider's own rules. `margin_used` is computed
    from the published factor, not read off the account, which a tiered requirement can exceed."""

    symbol: str
    size: float
    margin_used: float
    notional: float
    price: float
    margin_factor: float
    leverage: float


def register(mcp: FastMCP, gateway: GatewayClient) -> None:
    @mcp.tool(annotations=READ_ONLY)
    async def get_instrument_terms(symbol: str) -> InstrumentTermsOut:
        """The terms the provider trades this instrument on: the deposit it requires
        (`margin_factor` with its unit), the smallest and largest order it accepts, the
        step sizes move in, the lot size and the settlement currency.

        No price — ask the archive for that. A field the provider does not publish comes
        back null rather than as a zero or a default.
        """
        return InstrumentTermsOut.model_validate(await _terms(gateway, symbol))

    @mcp.tool(annotations=READ_ONLY)
    async def size_for_margin(symbol: str, margin: float, price: float) -> SizeForMarginOut:
        """How large an order to send to commit a given deposit — the conversion the
        provider's rules make, done before the order rather than silently during it.

        `margin` is the deposit to tie up, in the account's currency; `price` is the price
        to size against, and it is yours to supply — pass the one you read from the
        archive, so the size and the decision rest on the same number.

        The size comes back rounded **down** to the provider's step, with the deposit it
        really commits and the contract value it opens. A deposit too small for the
        smallest order the provider takes is a refusal naming both, not a size that would
        be rejected.
        """
        if margin <= 0:
            raise ToolRefusal(f"refused: margin must be greater than zero, got {margin}")
        if price <= 0:
            raise ToolRefusal(f"refused: price must be greater than zero, got {price}")

        terms = await _terms(gateway, symbol)
        factor = _margin_factor_or_refuse(symbol, terms)

        # deposit -> contract value -> size. Written in this order because it is the order
        # the reasoning goes in, and each step is a number the answer carries back.
        notional = _decimal(margin) / (factor / Decimal(100))
        size = _round_down(notional / _decimal(price), terms.get("size_increment"))

        # Before the provider's own floor, because an instrument it publishes no `min_deal_size` for
        # still cannot be traded in nothing: a deposit under one step rounds down to zero.
        if size <= 0:
            raise ToolRefusal(
                f"refused: {margin} of margin buys less than one step of {symbol} at "
                f"{price} — the size rounds down to nothing. Ask for more margin."
            )

        minimum = terms.get("min_deal_size")
        if minimum is not None and size < _decimal(minimum):
            needed = _decimal(minimum) * _decimal(price) * factor / Decimal(100)
            raise ToolRefusal(
                f"refused: {margin} of margin buys {size} of {symbol}, under the smallest "
                f"order the provider takes ({minimum}). That size needs about "
                f"{_as_float(needed)} of margin."
            )
        maximum = terms.get("max_deal_size")
        if maximum is not None and size > _decimal(maximum):
            raise ToolRefusal(
                f"refused: {margin} of margin buys {size} of {symbol}, over the largest "
                f"order the provider takes ({maximum}). Place several, or ask for less."
            )

        settled_notional = size * _decimal(price)
        return SizeForMarginOut(
            symbol=symbol,
            size=_as_float(size),
            margin_used=_as_float(settled_notional * factor / Decimal(100)),
            notional=_as_float(settled_notional),
            price=price,
            margin_factor=_as_float(factor),
            leverage=_as_float(Decimal(100) / factor),
        )


async def _terms(gateway: GatewayClient, symbol: str) -> dict:
    return await _read(gateway, f"/instruments/{symbol}/terms")


def _margin_factor_or_refuse(symbol: str, terms: dict) -> Decimal:
    unit = terms.get("margin_factor_unit")
    factor = terms.get("margin_factor")
    if factor is None:
        raise ToolRefusal(
            f"refused: the provider publishes no margin requirement for {symbol}, so a "
            "size cannot be computed from a deposit. Send a size directly instead."
        )
    if unit != PERCENTAGE:
        raise ToolRefusal(
            f"refused: the provider states {symbol}'s margin requirement in {unit!r}, "
            f"which this module cannot compute with — it knows {PERCENTAGE!r}. Read "
            "`get_instrument_terms` and size the order yourself."
        )
    if _decimal(factor) <= 0:
        raise ToolRefusal(
            f"refused: the provider states {symbol}'s margin requirement as {factor}, "
            "which cannot be divided by."
        )
    return _decimal(factor)


def _round_down(size: Decimal, increment: float | None) -> Decimal:
    """Down, never to the nearest step: rounding up commits more deposit than was asked
    for, and a ceiling that rounding can step over is not a ceiling."""
    if increment is None:
        return size
    step = _decimal(increment)
    if step <= 0:
        return size
    return (size // step) * step


def _decimal(value: float | str) -> Decimal:
    """Through `str`, because `Decimal(0.001)` is not 0.001 — and the point of working in `Decimal`
    here is that a step of 0.001 divides an obvious number into an obvious one."""
    try:
        return Decimal(str(value))
    except InvalidOperation as err:  # pragma: no cover - the gateway sends numbers
        raise ToolRefusal(f"refused: {value!r} is not a number this module can compute with") from err


def _as_float(value: Decimal) -> float:
    return float(value.normalize())

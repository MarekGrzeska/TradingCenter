"""The formula language at its lowest layer: what is read, what is refused and how the refusal reads. Each reason to
refuse once (`strategies-language`)."""

from __future__ import annotations

import ast
import pathlib

import pytest

from strategies import formula
from strategies.checking import ParamDecl, check, let_order, names_used, reserved_problem
from strategies.vocabulary import Place, Type

from .builders import catalogue, scope


def problems(text: str, place: Place = Place.ENTRY, expected: Type = Type.CONDITION, **kwargs) -> list[str]:
    node, found = formula.parse(text, "entries[0].when")
    if node is None:
        return [p.message for p in found]
    return [p.message for p in check(node, scope(place, **kwargs), "entries[0].when", expected)]


@pytest.mark.parametrize(
    "text",
    [
        "ema(20) @ HOUR_4 > ema(50) @ HOUR_4 and close[1] < low[2]",
        "7 <= hour < 20 and weekday != FRIDAY",
        "crosses_above(ema(p.fast), ema(period=50)) or not rising(close, 3)",
        "close @ US500 > ema(200) @ US500 @ DAY and not stale(close @ \"J225\")",
        "bbands(20, 2).upper < high and (close - open if close > open else 0) > 0.5 * atr(14)",
        "bars_since(crosses_below(close, ema(20))) > 5 and highest(high, p.fast)[1] < close",
        "losses_in_row < 2 and trades_today == 0",
    ],
)
def test_a_formula_built_from_the_language_is_accepted(text: str) -> None:
    assert problems(text) == []


def test_an_exit_may_read_the_open_position() -> None:
    assert problems("entry_price - 2 * at_entry(atr(14))", place=Place.EXIT, expected=Type.NUMBER) == []


@pytest.mark.parametrize(
    "text",
    [
        '__import__("os")', "lambda: 1", "[x for x in close]", "(x := 1)", "close[1:5]", "close ** 2", "{1: 2}",
        "(close, open)", "{close}", 'f"{close}"', "close % 2", "close is open", "close in open", "~close",
        "ema(**p)", "max(*close)", "close | open", "close.real",
    ],
)
def test_a_construction_outside_the_list_is_refused_with_its_place(text: str) -> None:
    node, found = formula.parse(text, "entries[0].when")

    refused = found or check(node, scope(), "entries[0].when", Type.CONDITION)  # type: ignore[arg-type]
    assert refused and refused[0].path == "entries[0].when" and refused[0].column is not None


@pytest.mark.parametrize("text", ["close[-1] > open", "close[p.fast * 2] > open"])
def test_an_offset_into_the_future_or_from_a_formula_is_refused(text: str) -> None:
    message = problems(text)[0]
    assert "future" in message or "never a formula" in message


def test_a_window_beyond_the_ceiling_is_refused() -> None:
    assert "1 to 5000" in problems("highest(high, 6000) > close")[0]


def test_a_parameter_that_may_leave_a_window_is_refused() -> None:
    message = problems("highest(high, p.w) > close", params={"w": ParamDecl(10, 0, 30, 5)})[0]
    assert "p.w" in message


def test_a_misspelt_function_hears_the_nearest_name() -> None:
    node, _ = formula.parse("emaa(20) > close", "entries[0].when")
    [found] = check(node, scope(), "entries[0].when", Type.CONDITION)  # type: ignore[arg-type]

    assert "emaa" in found.message and found.hint == "ema"


def test_a_number_where_a_condition_stands_is_a_type_error() -> None:
    assert "condition is expected" in problems("close - open")[0]


def test_a_multi_line_indicator_without_its_line_says_which_lines_there_are() -> None:
    node, _ = formula.parse("bbands(20, 2) > close", "entries[0].when")
    [found] = check(node, scope(), "entries[0].when", Type.CONDITION)  # type: ignore[arg-type]

    assert "several lines" in found.message and "upper" in (found.hint or "")


def test_an_indicator_that_draws_markers_is_refused_with_why() -> None:
    assert "draws markers" in problems("swing_points(3) > close")[0]


def test_an_indicator_parameter_outside_the_catalogue_range_names_the_range() -> None:
    assert "2 to 5000" in problems("ema(1) > close")[0]


def test_a_new_catalogue_entry_is_a_function_without_a_change_here() -> None:
    node, _ = formula.parse("supertrend(10) > close", "entries[0].when")
    grown = catalogue() | {
        "supertrend": catalogue()["ema"].__class__("supertrend", "lines", catalogue()["ema"].params, ("supertrend",))
    }
    widened = scope().__class__(Place.ENTRY, {}, {}, grown)

    assert check(node, widened, "entries[0].when", Type.CONDITION) == []  # type: ignore[arg-type]


def test_the_open_position_in_an_entry_condition_is_refused() -> None:
    assert "before an entry there is none" in problems("close > entry_price")[0]


def test_trades_cannot_be_read_by_a_let() -> None:
    assert "computed once" in problems("losses_in_row", place=Place.LET, expected=Type.NUMBER)[0]


@pytest.mark.parametrize("text", ["close @ HOUR4 > 1", "close @ hour4 > 1", "close @ hour > 1", "close @ p > 1"])
def test_a_slip_on_the_right_of_at_is_not_read_as_an_instrument(text: str) -> None:
    assert "neither a resolution nor an instrument" in problems(text)[0]


def test_columns_count_characters_of_the_formula_as_written() -> None:
    _, [found] = formula.parse('  close @ "Ż225" > open[-1]', "x")

    assert found.column == 25


def test_a_number_too_large_is_a_problem_not_a_crash() -> None:
    assert "too large" in problems("close > 1" + "0" * 400)[0]


def test_two_instruments_in_one_context_are_refused() -> None:
    assert "names two" in problems("close @ US500 @ DE40 > 1")[0]


def test_a_let_is_not_read_under_at() -> None:
    assert "under `@`" in problems("trend @ HOUR_4", lets={"trend": Type.CONDITION})[0]


def test_let_order_follows_use_and_names_a_cycle_and_what_depends_on_it() -> None:
    order, unordered = let_order({"a": {"b"}, "b": {"close"}, "c": {"d"}, "d": {"c"}, "e": {"c"}, "s": {"s"}})

    assert order == ["b", "a"] and unordered == ["c", "d", "e", "s"]


def test_a_long_chain_of_lets_orders_without_recursion() -> None:
    chain = {f"v{i}": {f"v{i - 1}"} for i in range(1, 3000)} | {"v0": set()}

    order, unordered = let_order(chain)

    assert order[0] == "v0" and order[-1] == "v2999" and unordered == []


def test_names_used_reads_through_every_construction() -> None:
    node, _ = formula.parse("fast[1] > slow @ HOUR_4 if trend else 0", "let.x")

    assert names_used(node) == {"fast", "slow", "trend"}  # type: ignore[arg-type]


@pytest.mark.parametrize("name", ["close", "ema", "HOUR", "p", "2fast", "None", "if", "match", "ｃｌｏｓｅ"])
def test_a_let_name_cannot_hide_a_name_of_the_language(name: str) -> None:
    assert reserved_problem(name, f"let.{name}", catalogue()) is not None


def test_nothing_in_the_package_executes_code() -> None:
    """The guarantee the whole language rests on, read off the source: no eval, exec or compile however reached, and no
    import of the modules that reach them by another door."""
    package = pathlib.Path(__file__).resolve().parents[2] / "strategies"
    trees = [ast.parse(path.read_text(encoding="utf-8")) for path in package.rglob("*.py")]
    called = {
        node.func.id if isinstance(node.func, ast.Name) else node.func.attr
        for tree in trees
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name | ast.Attribute)
    }
    imported = {
        alias.name.split(".")[0]
        for tree in trees
        for node in ast.walk(tree)
        if isinstance(node, ast.Import | ast.ImportFrom)
        for alias in (node.names if isinstance(node, ast.Import) else [ast.alias(node.module or "")])
    }

    assert not called & {"eval", "exec", "compile", "__import__", "literal_eval"}
    assert not imported & {"builtins", "importlib", "code", "codeop", "runpy", "types"}

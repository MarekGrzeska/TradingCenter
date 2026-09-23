"""When two names are one group, and when they are close enough that a model has to ask first."""

from __future__ import annotations

import pytest

from polymarket_data import group_names


def test_case_and_spacing_are_not_part_of_a_name() -> None:
    assert group_names.key("  US   Politics ") == group_names.key("us politics")


@pytest.mark.parametrize(
    ("new", "existing"),
    [
        ("tariff", "Tariffs"),
        ("Politics", "US politics"),
        ("crypto", "Cryptocurrency"),
        ("Geopolityka", "geopolityk"),
    ],
)
def test_a_respelling_reads_as_a_lookalike(new: str, existing: str) -> None:
    assert group_names.similar(new, [existing]) == [existing]


@pytest.mark.parametrize(
    ("new", "existing"),
    [
        ("AI", "Airlines"),
        ("Fed", "Elections"),
        ("Crypto", "crypto"),
    ],
)
def test_neither_a_coincidence_nor_the_same_group_is_a_lookalike(new: str, existing: str) -> None:
    """The last pair is the same group, which `find_group` answers — not a question for the model."""
    assert group_names.similar(new, [existing]) == []

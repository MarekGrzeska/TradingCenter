"""Which retired models move at startup — the rule that keeps a deploy and the operator's apply in either order."""

from __future__ import annotations

from workbench import model_successors

GPT_6 = {"gpt-6-luna", "gpt-6-sol", "gpt-6-astra"}
GPT_5_6 = {"gpt-5.6-luna", "gpt-5.6-terra", "gpt-5.6-sol"}


def test_nothing_moves_while_the_old_catalogue_is_still_configured() -> None:
    assert model_successors.applicable(GPT_5_6) == {}


def test_every_retired_model_moves_once_its_successor_is_configured() -> None:
    assert model_successors.applicable(GPT_6) == {
        "gpt-5.6-luna": "gpt-6-luna",
        "gpt-5.6-sol": "gpt-6-sol",
        "gpt-5.6-terra": "gpt-6-sol",
    }


def test_a_catalogue_without_the_successor_keeps_the_refusal() -> None:
    assert model_successors.applicable({"local-model"}) == {}

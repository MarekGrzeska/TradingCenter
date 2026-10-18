"""The document the terminal will generate its wire types from, built without starting anything."""

from __future__ import annotations

from alerts.openapi import document


def test_the_document_builds_with_nothing_running_and_describes_what_the_form_reads() -> None:
    published = document()

    assert published["info"]["title"] == "alerts"
    for name in ("RuleIn", "RuleOut", "CatalogOut", "Problem", "Defect", "ConditionSource", "EventSource"):
        assert name in published["components"]["schemas"], name


def test_a_response_declares_every_field_it_always_sends() -> None:
    """A field with a default is not `required` to Pydantic, but the package answers with it regardless; read raw, the
    terminal would get `T | undefined` for a case that cannot happen."""
    rule = document()["components"]["schemas"]["RuleOut"]

    assert sorted(rule["required"]) == sorted(rule["properties"])

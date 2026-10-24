"""What is wrong with a document, said so it can be fixed without guessing — by the operator, and in stage 2 by a model
that reads the list and tries again."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Problem:
    """One defect. `path` is where in the document (`entries[0].when`), `column` where in its formula, 1-based, or
    `None` when the defect is the field itself rather than a place in a formula."""

    path: str
    message: str
    column: int | None = None
    hint: str | None = None

    def as_dict(self) -> dict:
        return {"path": self.path, "column": self.column, "message": self.message, "hint": self.hint}

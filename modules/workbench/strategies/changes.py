"""What one revision changed against another, by the paths problems use (`entries[0].when`), so the history on the screen
and what `save_strategy` tells the model are the same list (design D5). Dictionaries compare by key — their order is not
a change — and lists by position."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, Literal

Kind = Literal["added", "removed", "changed"]
_MISSING = object()


@dataclass(frozen=True)
class Change:
    path: str
    kind: Kind
    before: Any
    after: Any

    def as_dict(self) -> dict[str, Any]:
        return {"path": self.path, "kind": self.kind, "before": self.before, "after": self.after}


def between(before: Any, after: Any) -> list[Change]:
    return list(_walk(before, after, ""))


def _join(path: str, key: str | int) -> str:
    if isinstance(key, int):
        return f"{path}[{key}]"
    return key if not path else f"{path}.{key}"


def _walk(before: Any, after: Any, path: str) -> Iterator[Change]:
    if isinstance(before, dict) and isinstance(after, dict):
        for key in [*before, *(k for k in after if k not in before)]:
            yield from _walk(before.get(key, _MISSING), after.get(key, _MISSING), _join(path, key))
        return
    if isinstance(before, list) and isinstance(after, list):
        for i in range(max(len(before), len(after))):
            yield from _walk(
                before[i] if i < len(before) else _MISSING, after[i] if i < len(after) else _MISSING, _join(path, i)
            )
        return
    if before is _MISSING:
        yield Change(path, "added", None, after)
    elif after is _MISSING:
        yield Change(path, "removed", before, None)
    elif before != after:
        yield Change(path, "changed", before, after)

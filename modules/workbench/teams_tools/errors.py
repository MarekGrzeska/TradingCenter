"""The three things that can come back, and why they are three rather than two. Collapsing the last two into
"it failed" makes a model retry where retrying changes nothing and give up where one field needed fixing."""

from __future__ import annotations


class ToolRefusal(Exception):
    """`teams` was asked and answered "not like that" — or this module refused before asking, which is the
    same fact from the caller's seat. The message carries `teams`' own words wherever it supplied them."""


class UpstreamUnavailable(Exception):
    """`teams` could not be asked at all. Nothing is known about the catalogue either way, and in particular
    a write MUST NOT be assumed not to have happened."""

"""The three things that can come back, and why they are three rather than two.

A tool answers, or `teams` refuses, or nobody could be asked. Collapsing the last two
into "it failed" is what makes a model retry where retrying changes nothing and give up
where one field needed fixing (specs/teams-mcp-upstream-access, "Odmowa modułu `teams`
jest odróżnialna od jego niedostępności").

Both classes below become a tool error the caller sees; the difference travels in the
sentence, because that is what the model reads.
"""

from __future__ import annotations


class ToolRefusal(Exception):
    """`teams` was asked and answered "not like that" — or this module refused before
    asking, which is the same fact from the caller's seat: the call as written will not
    work, and repeating it unchanged will not help.

    The message carries `teams`' own words wherever `teams` supplied them
    (specs/teams-mcp-authorship, "Odmowa modułu dociera do operatora jego słowami").
    """


class UpstreamUnavailable(Exception):
    """`teams` could not be asked at all — unreachable, too slow, or it refused this
    module's identity. Nothing is known about the catalogue either way, and in
    particular a write MUST NOT be assumed not to have happened."""

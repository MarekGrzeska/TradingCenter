"""The assembly: one process over two surfaces.

`agent/` is the operator's conversation with a model, `teams/` the teams they compose and
run, `teams_tools/` the tool surface the conversation builds teams through. This package
is the only one that imports all three — see `tests/test_layering.py`, which is where that
sentence is enforced rather than merely written.
"""

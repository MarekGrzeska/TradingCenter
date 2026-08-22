"""The strategy platform.

A catalogue of strategies, one runtime around them, and one backtest for all of them.
A strategy is an entry — declared facts, parameters with ranges, a pure `evaluate` — and
adding one changes no file of the runtime (`strategy-catalogue`).

This module decides and records. It never touches an account: execution stays with the
teams and their limits, and no setting moves that line (`strategy-runtime`).
"""

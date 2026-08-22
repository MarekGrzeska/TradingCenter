"""The prediction-market archive.

One module, two surfaces in one process: the REST contract the terminal reads, and the
tool surface at `/mcp` the workbench reads. The same shape as `market-data`, and for the
same reason — a separate MCP process over somebody else's archive adds a network hop and
a second copy of the schema, and nothing else.
"""

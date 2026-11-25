# /// script
# requires-python = ">=3.12"
# dependencies = ["httpx>=0.27"]
# ///
"""Call one tool on one of production's MCP surfaces, whether or not Claude Code has it registered.

    uv run --script tc_mcp.py chart-tools list_chart_drawings '{"symbol":"US100"}'
    uv run --script tc_mcp.py chart-tools draw_on_chart @payload.json
    uv run --script tc_mcp.py market get_candles '{"symbol":"US100","resolution":"HOUR"}'

The host and the token come from the tc-market registration in ~/.claude.json (`scripts/claude-mcp.sh install`):
same API host, same workbench token, so nothing here holds a secret of its own."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

import httpx


def registration(surface: str) -> tuple[str, dict[str, str]]:
    config = json.loads((Path.home() / ".claude.json").read_text(encoding="utf-8"))
    market = config["mcpServers"]["tc-market"]
    parts = urlsplit(market["url"])
    helper = subprocess.run(market["headersHelper"], shell=True, capture_output=True, text=True, timeout=60)
    if helper.returncode != 0:
        sys.exit(f"token helper refused: {helper.stderr.strip()} (run scripts/mcp_token.py login)")
    return f"{parts.scheme}://{parts.netloc}/{surface}/mcp", json.loads(helper.stdout)


def rpc_result(response: httpx.Response) -> dict:
    response.raise_for_status()
    if response.headers.get("content-type", "").startswith("text/event-stream"):
        for line in response.text.splitlines():
            if line.startswith("data:"):
                return json.loads(line[5:])
        sys.exit("empty event stream")
    return response.json()


def call(surface: str, tool: str, arguments: dict) -> str:
    """The tool's text answer; exits with the refusal when the surface refuses."""
    url, headers = registration(surface)
    headers |= {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
    with httpx.Client(timeout=60) as client:
        init = client.post(url, headers=headers, json={
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2025-03-26", "capabilities": {},
                       "clientInfo": {"name": "psv-us100-skill", "version": "1"}},
        })
        rpc_result(init)
        if session := init.headers.get("mcp-session-id"):
            headers["mcp-session-id"] = session
        client.post(url, headers=headers, json={"jsonrpc": "2.0", "method": "notifications/initialized"})
        answer = rpc_result(client.post(url, headers=headers, json={
            "jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": tool, "arguments": arguments},
        }))
    if "error" in answer:
        sys.exit(json.dumps(answer["error"], ensure_ascii=False))
    result = answer["result"]
    text = "\n".join(c.get("text", "") for c in result.get("content", []))
    if result.get("isError"):
        sys.exit(text)
    return text


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # a Windows console's cp1250 cannot print the labels' − and ±
    surface, tool, raw = sys.argv[1], sys.argv[2], sys.argv[3]
    arguments = json.loads(Path(raw[1:]).read_text(encoding="utf-8") if raw.startswith("@") else raw)
    print(call(surface, tool, arguments))


if __name__ == "__main__":
    main()

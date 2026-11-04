"""Zero API (`claude-agent-runtime`): the agent reaches the model only through the operator's subscription. Refuses a
key or token in the environment, an `apiKeyHelper` in any settings file, and a key stored in Claude Code's state.

    python -m claude_agent.zero_api <settings files...>   # exit 64 naming the reason, or prints "zero-api: ok"
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

API_VARIABLES = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")
REFUSED = 64


def _json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def problem(env: Mapping[str, str], settings_files: Iterable[Path], config_dir: Path) -> str | None:
    for name in API_VARIABLES:
        if env.get(name):
            return f"{name} is set; the agent runs on the Claude subscription only"
    for file in settings_files:
        settings = _json(file)
        if isinstance(settings, dict) and "apiKeyHelper" in settings:
            return f"apiKeyHelper is configured in {file}"
    state = _json(config_dir / ".claude.json")
    if isinstance(state, dict) and isinstance(state.get("primaryApiKey"), str):
        return f"an API key is stored in {config_dir / '.claude.json'}"
    return None


def main(argv: list[str]) -> int:
    config_dir = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
    found = problem(os.environ, [Path(a) for a in argv], config_dir)
    if found is not None:
        print(f"[zero-api] REFUSING TO START: {found}", file=sys.stderr)
        return REFUSED
    # The entrypoint starts only on this exact line, so a check that silently did not run cannot pass for one that did.
    print("zero-api: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

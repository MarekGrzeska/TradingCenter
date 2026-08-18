"""The one invariant both scripts resolve everything else from.

`dev.py` finds the repository root by walking up from its own file, and every service
directory, `compose.yaml` and `.env` it touches hangs off that. A move of `scripts/` would
break both scripts in a way whose symptom is a path error deep inside a service start —
this fails at the top instead, and names why.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_repo_root_is_two_levels_above_this_file() -> None:
    assert (REPO_ROOT / "modules").is_dir()
    assert (REPO_ROOT / "packages").is_dir()
    assert (REPO_ROOT / "compose.yaml").is_file()

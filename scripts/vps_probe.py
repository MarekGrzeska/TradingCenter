"""Is this commit's image the one serving on the server, and does the system answer from outside? The VPS twin of
`deploy_probe.py`, which asks Azure's control plane: here the server says which images its containers run (the deploy
key's `status` verb) and the public addresses are asked the way a browser would. Both questions, or the deploy failed."""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass

import httpx

SERVICES = ("capital-gateway", "trading-mcp", "workbench")
# The compose service names, which `status` prints, mapped to the image each runs.
SERVICE_IMAGE = {"gateway": "capital-gateway", "trading-mcp": "trading-mcp", "workbench": "workbench"}


@dataclass(frozen=True)
class Check:
    """One public address that must answer 200 with a given word in its body."""

    name: str
    url: str
    body_contains: str = ""


StatusReader = Callable[[], str]
Fetcher = Callable[[str], tuple[int, str]]


def running_images(status_output: str) -> dict[str, str]:
    """`gateway ghcr.io/o/r/capital-gateway:abc123` lines -> {module: image}. Lines that are not that shape (the compose
    table that follows) are ignored."""
    found: dict[str, str] = {}
    for line in status_output.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[0] in SERVICE_IMAGE:
            found[SERVICE_IMAGE[parts[0]]] = parts[1]
    return found


def wrong_images(running: dict[str, str], prefix: str, sha: str) -> list[str]:
    problems = []
    for module in SERVICES:
        expected = f"{prefix}/{module}:{sha}"
        actual = running.get(module)
        if actual != expected:
            problems.append(f"{module} runs {actual or 'nothing'}, expected {expected}")
    return problems


def failing_checks(checks: Sequence[Check], fetch: Fetcher) -> list[str]:
    problems = []
    for check in checks:
        try:
            status, body = fetch(check.url)
        except httpx.HTTPError as err:
            problems.append(f"{check.name}: {check.url} did not answer ({type(err).__name__})")
            continue
        if status != 200:
            problems.append(f"{check.name}: {check.url} answered {status}")
        elif check.body_contains not in body:
            problems.append(f"{check.name}: {check.url} answered 200 without {check.body_contains!r}")
    return problems


def wait_until_serving(
    *,
    read_status: StatusReader,
    prefix: str,
    sha: str,
    checks: Sequence[Check],
    fetch: Fetcher,
    attempts: int = 12,
    sleep_seconds: float = 10.0,
    sleep: Callable[[float], None] = time.sleep,
    log: Callable[[str], None] = print,
) -> bool:
    for attempt in range(1, attempts + 1):
        problems = [
            *wrong_images(running_images(read_status()), prefix, sha),
            *failing_checks(checks, fetch),
        ]
        if not problems:
            log(f"attempt {attempt}: {sha} is serving, and every address answers")
            return True
        log(f"attempt {attempt}/{attempts}: " + "; ".join(problems))
        if attempt < attempts:
            sleep(sleep_seconds)
    return False


def _ssh_status(target: str) -> str:
    # The deploy key runs one command whatever is asked; "status" is for the log.
    result = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", target, "status"],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    return result.stdout


def _http_get(url: str) -> tuple[int, str]:
    response = httpx.get(url, timeout=20.0, follow_redirects=False)
    return response.status_code, response.text


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ssh-target", required=True, help="deploy@host")
    parser.add_argument("--image-prefix", required=True, help="ghcr.io/owner/repo, lower-case")
    parser.add_argument("--sha", required=True)
    parser.add_argument(
        "--check",
        action="append",
        default=[],
        metavar="NAME|URL|BODY",
        help="a public address and a word its body must contain",
    )
    parser.add_argument("--attempts", type=int, default=12)
    args = parser.parse_args(argv)

    checks = [Check(*[part.strip() for part in raw.split("|", 2)]) for raw in args.check]
    ok = wait_until_serving(
        read_status=lambda: _ssh_status(args.ssh_target),
        prefix=args.image_prefix,
        sha=args.sha,
        checks=checks,
        fetch=_http_get,
        attempts=args.attempts,
    )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

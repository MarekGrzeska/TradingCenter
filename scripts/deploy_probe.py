"""Is this commit's image the one serving, and did the process inside come up? The second question used
to go unasked: on 16 August 2026 the control plane read `Running` for an hour over a crash loop."""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass

# Every app in this subscription lives here, and has since the first `apply`. A flag rather
# than a constant so a test never depends on it.
DEFAULT_RESOURCE_GROUP = "rg-tradingcenter"

# How much of a response body reaches the log. The check itself reads all of it — the shell version
# grepped the same 200 bytes it printed, which would have missed a key arriving late in a body.
BODY_LOG_LIMIT = 200


@dataclass(frozen=True)
class ProbeSpec:
    """What "serving" means for one app. An empty `probe_path` is capital-gateway, which a GitHub runner
    cannot reach at all, so the control plane is the only question its deploy can ask."""

    app_name: str
    expected_image: str
    probe_path: str = ""
    expected_status: int = 200
    body_contains: str = ""
    attempts: int = 12
    sleep_seconds: float = 15.0
    failure_hint: str = ""


# What the control plane hands back, and what an HTTP attempt saw. `state` is only read in the
# control-plane-only variant, so it is None elsewhere rather than fetched and ignored.
ImageReader = Callable[[], str | None]
StateReader = Callable[[], str | None]
Prober = Callable[[], tuple[int, str]]


def normalise_image(raw: str | None) -> str | None:
    """`az` returns the image name with a `DOCKER|` prefix on a container app setting."""
    if raw is None:
        return None
    stripped = raw.strip()
    if not stripped or stripped == "None":
        return None
    return stripped.removeprefix("DOCKER|")


def wait_until_serving(
    spec: ProbeSpec,
    current_image: ImageReader,
    probe: Prober | None = None,
    site_state: StateReader | None = None,
    sleep: Callable[[float], None] = time.sleep,
    log: Callable[[str], None] = print,
) -> bool:
    """True once this commit's image is serving; False when `spec.attempts` ran out. Both questions are
    arguments rather than imports, so "right state, wrong image" is a two-line test."""
    if probe is None and site_state is None:
        raise ValueError(
            f"{spec.app_name}: neither an HTTP probe nor a state reader was given, so this "
            "would assert the image tag and nothing else"
        )

    image: str | None = None
    status = 0
    body = ""
    state: str | None = None

    for attempt in range(1, spec.attempts + 1):
        image = normalise_image(current_image())
        image_matches = image == spec.expected_image

        if probe is None:
            state = site_state() if site_state else None
            log(f"attempt {attempt}: state={state or 'unknown'} image={image or 'none'}")
            if image_matches and state == "Running":
                log(f"deployed: {spec.expected_image}")
                return True
        else:
            status, body = probe()
            log(
                f"attempt {attempt}: image={image or 'none'} "
                f"HTTP {status} {body[:BODY_LOG_LIMIT]}"
            )
            if (
                image_matches
                and status == spec.expected_status
                and (not spec.body_contains or spec.body_contains in body)
            ):
                log(f"serving: {spec.expected_image}")
                return True

        # No sleep after the last attempt — the shell version slept, then exited, spending
        # its final 15 seconds waiting for nothing.
        if attempt < spec.attempts:
            sleep(spec.sleep_seconds)

    log(f"::error::{_failure_message(spec, image, status, body, state, probe is not None)}")
    return False


def _failure_message(
    spec: ProbeSpec,
    image: str | None,
    status: int,
    body: str,
    state: str | None,
    probe_ran: bool,
) -> str:
    """Name the condition that did not hold, not merely that something did not: an old container still
    answering wants a different next step from a new one answering 500."""
    waited = int(spec.attempts * spec.sleep_seconds)
    reasons: list[str] = []

    if image != spec.expected_image:
        reasons.append(f"serving image={image or 'none'}, expected {spec.expected_image}")
    if probe_ran:
        if status != spec.expected_status:
            reasons.append(f"HTTP {status or 'unreachable'}, expected {spec.expected_status}")
        elif spec.body_contains and spec.body_contains not in body:
            reasons.append(
                f"HTTP {status} but the body does not contain {spec.body_contains} — "
                f"answered by something other than the container"
            )
    if not probe_ran and state != "Running":
        reasons.append(f"site state={state or 'unknown'}, expected Running")

    if not reasons:
        # Every condition reads as satisfied yet the loop ran out: the last attempt raced a
        # container swap. Saying so beats an empty reason list.
        reasons.append("the final attempt saw every condition hold — a race with the swap")

    message = f"{spec.app_name} is not serving after ~{waited}s: " + "; ".join(reasons)
    if spec.failure_hint:
        message += f". {spec.failure_hint}"
    return message


def az_image_reader(app_name: str, resource_group: str) -> ImageReader:
    def read() -> str | None:
        return _az(
            "webapp",
            "config",
            "container",
            "show",
            "--name",
            app_name,
            "--resource-group",
            resource_group,
            "--query",
            "[?name=='DOCKER_CUSTOM_IMAGE_NAME'].value | [0]",
            "-o",
            "tsv",
        )

    return read


def az_state_reader(app_name: str, resource_group: str) -> StateReader:
    def read() -> str | None:
        return _az(
            "webapp",
            "show",
            "--name",
            app_name,
            "--resource-group",
            resource_group,
            "--query",
            "state",
            "-o",
            "tsv",
        )

    return read


def _az(*args: str) -> str | None:
    """`az` failing is an answer, not a crash — the site may not exist yet on a first deploy."""
    try:
        # Fixed argv, no shell — nothing here is interpolated from a response.
        done = subprocess.run(
            ["az", *args],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
            shell=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return done.stdout.strip() if done.returncode == 0 else None


def http_prober(url: str, timeout: float = 20.0) -> Prober:
    import httpx

    def probe() -> tuple[int, str]:
        try:
            response = httpx.get(url, timeout=timeout, follow_redirects=False)
        except httpx.HTTPError:
            # `curl || echo 000` in the shell version. An unreachable app during a swap is
            # the normal case, not an error worth stopping for.
            return 0, ""
        return response.status_code, response.text

    return probe


def parse_args(argv: list[str] | None = None) -> tuple[ProbeSpec, str]:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-name", required=True)
    parser.add_argument("--expected-image", required=True)
    parser.add_argument(
        "--probe-path",
        default="",
        help="empty for the control-plane-only variant (capital-gateway)",
    )
    parser.add_argument("--expected-status", type=int, default=200)
    parser.add_argument("--body-contains", default="")
    parser.add_argument("--attempts", type=int, default=12)
    parser.add_argument("--sleep-seconds", type=float, default=15.0)
    parser.add_argument(
        "--failure-hint",
        default="",
        help="what the operator should look at first when this app fails to come up",
    )
    parser.add_argument("--resource-group", default=DEFAULT_RESOURCE_GROUP)
    args = parser.parse_args(argv)

    spec = ProbeSpec(
        app_name=args.app_name,
        expected_image=args.expected_image,
        probe_path=args.probe_path,
        expected_status=args.expected_status,
        body_contains=args.body_contains,
        attempts=args.attempts,
        sleep_seconds=args.sleep_seconds,
        failure_hint=args.failure_hint,
    )
    return spec, args.resource_group


def main(argv: list[str] | None = None) -> int:
    spec, resource_group = parse_args(argv)
    current_image = az_image_reader(spec.app_name, resource_group)

    if spec.probe_path:
        url = f"https://{spec.app_name}.azurewebsites.net{spec.probe_path}"
        served = wait_until_serving(spec, current_image, probe=http_prober(url))
    else:
        served = wait_until_serving(
            spec,
            current_image,
            site_state=az_state_reader(spec.app_name, resource_group),
        )
    return 0 if served else 1


if __name__ == "__main__":
    sys.exit(main())

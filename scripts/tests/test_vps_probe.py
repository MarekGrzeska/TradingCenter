"""vps_probe: the two questions a deploy to the server has to answer, with the server and the network doubled."""

from __future__ import annotations

import httpx
import pytest

from vps_probe import Check, failing_checks, running_images, wait_until_serving, wrong_images

PREFIX = "ghcr.io/o/r"
SHA = "abc123"
GOOD = (
    f"gateway {PREFIX}/capital-gateway:{SHA}\n"
    f"trading-mcp {PREFIX}/trading-mcp:{SHA}\n"
    f"workbench {PREFIX}/workbench:{SHA}\n"
    "NAME  IMAGE  COMMAND\n"
)


def test_the_status_output_is_read_per_module() -> None:
    assert running_images(GOOD)["workbench"] == f"{PREFIX}/workbench:{SHA}"


def test_an_old_image_is_named_with_what_it_should_have_been() -> None:
    old = GOOD.replace(f"workbench:{SHA}", "workbench:old999")
    problems = wrong_images(running_images(old), PREFIX, SHA)
    assert problems == [f"workbench runs {PREFIX}/workbench:old999, expected {PREFIX}/workbench:{SHA}"]


def test_a_module_that_is_not_running_is_a_problem() -> None:
    assert len(wrong_images({}, PREFIX, SHA)) == 3


def fetch_with(answers: dict[str, tuple[int, str]]):
    def fetch(url: str) -> tuple[int, str]:
        if url not in answers:
            raise httpx.ConnectError("refused")
        return answers[url]

    return fetch


def test_an_address_must_answer_200_with_its_word() -> None:
    checks = [Check("api", "https://api/health", "ok"), Check("gw", "https://gw/", "capital-gateway")]
    fetch = fetch_with({"https://api/health": (200, '{"status":"ok"}'), "https://gw/": (200, "nothing")})
    assert failing_checks(checks, fetch) == ["gw: https://gw/ answered 200 without 'capital-gateway'"]


def test_an_address_that_does_not_answer_is_a_problem_not_a_crash() -> None:
    assert failing_checks([Check("api", "https://api/health")], fetch_with({})) == [
        "api: https://api/health did not answer (ConnectError)"
    ]


def serving(statuses: list[str], answers: dict[str, tuple[int, str]]) -> tuple[bool, list[str]]:
    log: list[str] = []
    feed = iter(statuses)
    ok = wait_until_serving(
        read_status=lambda: next(feed),
        prefix=PREFIX,
        sha=SHA,
        checks=[Check("api", "https://api/health", "ok")],
        fetch=fetch_with(answers),
        attempts=3,
        sleep=lambda _seconds: None,
        log=log.append,
    )
    return ok, log


def test_it_waits_for_the_new_images_and_then_passes() -> None:
    old = GOOD.replace(SHA, "old999")
    ok, log = serving([old, GOOD], {"https://api/health": (200, "ok")})
    assert ok
    assert len(log) == 2


def test_it_gives_up_when_the_images_never_arrive() -> None:
    old = GOOD.replace(SHA, "old999")
    ok, log = serving([old, old, old], {"https://api/health": (200, "ok")})
    assert not ok
    assert len(log) == 3


def test_the_right_images_are_not_enough_if_nothing_answers_from_outside() -> None:
    ok, _ = serving([GOOD, GOOD, GOOD], {})
    assert not ok


@pytest.mark.parametrize("line", ["gateway", "gateway a b", "unknown x"])
def test_lines_of_another_shape_are_ignored(line: str) -> None:
    assert running_images(line) == {}

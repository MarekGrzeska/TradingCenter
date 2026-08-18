"""The failure modes this probe exists to catch, each one called directly.

Iteration 0 gave every deploy workflow an image-tag assertion and could not give it a test,
because a loop inside a YAML `run:` block has nothing to call. These are that test — and the
first one is 16 August 2026 reproduced: a healthy-looking answer from the container that was
already there.
"""

from __future__ import annotations

import pytest

from deploy_probe import ProbeSpec, normalise_image, wait_until_serving

NEW = "ghcr.io/marekgrzeska/tradingcenter/agent:cafe1234"
OLD = "ghcr.io/marekgrzeska/tradingcenter/agent:0ldc0de0"


def spec(**overrides: object) -> ProbeSpec:
    base: dict[str, object] = {
        "app_name": "app-tradingcenter-agent",
        "expected_image": NEW,
        "probe_path": "/health",
        "expected_status": 200,
        "body_contains": '"status"',
        "attempts": 3,
        "sleep_seconds": 0.0,
    }
    return ProbeSpec(**(base | overrides))  # pyright: ignore[reportArgumentType]


def test_a_healthy_answer_from_the_previous_container_does_not_pass() -> None:
    """16 August 2026. The old container answers 200 with the right body; the image is old."""
    logged: list[str] = []

    served = wait_until_serving(
        spec(),
        current_image=lambda: f"DOCKER|{OLD}",
        probe=lambda: (200, '{"status":"ok"}'),
        sleep=lambda _: None,
        log=logged.append,
    )

    assert served is False
    assert any("::error::" in line for line in logged)
    assert any(OLD in line and NEW in line for line in logged), (
        "the error must name both what is serving and what was expected"
    )


def test_a_200_whose_body_is_not_the_app_does_not_pass() -> None:
    """The new image is there, but something in front of it answered — a platform page."""
    logged: list[str] = []

    served = wait_until_serving(
        spec(),
        current_image=lambda: f"DOCKER|{NEW}",
        probe=lambda: (200, "<html><title>Sign in</title></html>"),
        sleep=lambda _: None,
        log=logged.append,
    )

    assert served is False
    assert any("does not contain" in line for line in logged)


def test_the_right_image_answering_correctly_passes() -> None:
    served = wait_until_serving(
        spec(),
        current_image=lambda: f"DOCKER|{NEW}",
        probe=lambda: (200, '{"status":"ok"}'),
        sleep=lambda _: None,
    )
    assert served is True


def test_market_datas_404_with_a_detail_body_passes() -> None:
    """market-data has no route excluded from Easy Auth, so its 404 *is* the healthy answer."""
    served = wait_until_serving(
        spec(probe_path="/ws/candles", expected_status=404, body_contains='"detail"'),
        current_image=lambda: f"DOCKER|{NEW}",
        probe=lambda: (404, '{"detail":"Not Found"}'),
        sleep=lambda _: None,
    )
    assert served is True


def test_a_swap_in_progress_is_retried_and_then_succeeds() -> None:
    """The normal case: the first attempts reach the old container, a later one the new."""
    answers = [(0, ""), (200, '{"status":"ok"}')]
    images = [f"DOCKER|{OLD}", f"DOCKER|{NEW}"]
    slept: list[float] = []

    served = wait_until_serving(
        spec(attempts=5, sleep_seconds=15.0),
        current_image=lambda: images.pop(0) if images else f"DOCKER|{NEW}",
        probe=lambda: answers.pop(0) if answers else (200, '{"status":"ok"}'),
        sleep=slept.append,
        log=lambda _: None,
    )

    assert served is True
    assert slept == [15.0], "one failed attempt, so exactly one wait"


def test_exhaustion_makes_exactly_attempts_calls_and_sleeps_one_fewer() -> None:
    calls: list[int] = []
    slept: list[float] = []

    served = wait_until_serving(
        spec(attempts=4, sleep_seconds=15.0),
        current_image=lambda: (calls.append(1), f"DOCKER|{OLD}")[1],
        probe=lambda: (200, '{"status":"ok"}'),
        sleep=slept.append,
        log=lambda _: None,
    )

    assert served is False
    assert len(calls) == 4
    assert len(slept) == 3, "no sleep after the last attempt — the shell version wasted 15s"


class TestControlPlaneOnly:
    """capital-gateway: unreachable from a runner, so the image tag plus the site state."""

    def test_the_image_tag_plus_running_is_enough(self) -> None:
        served = wait_until_serving(
            spec(probe_path="", body_contains="", attempts=2),
            current_image=lambda: f"DOCKER|{NEW}",
            site_state=lambda: "Running",
            sleep=lambda _: None,
            log=lambda _: None,
        )

        assert served is True

    def test_running_over_the_previous_image_does_not_pass(self) -> None:
        logged: list[str] = []

        served = wait_until_serving(
            spec(probe_path="", body_contains="", attempts=2),
            current_image=lambda: f"DOCKER|{OLD}",
            site_state=lambda: "Running",
            sleep=lambda _: None,
            log=logged.append,
        )

        assert served is False
        assert any(OLD in line for line in logged)

    def test_a_stopped_site_on_the_right_image_does_not_pass(self) -> None:
        logged: list[str] = []

        served = wait_until_serving(
            spec(probe_path="", body_contains="", attempts=2),
            current_image=lambda: f"DOCKER|{NEW}",
            site_state=lambda: "Stopped",
            sleep=lambda _: None,
            log=logged.append,
        )

        assert served is False
        assert any("state=Stopped" in line for line in logged)


def test_neither_question_asked_is_a_programming_error_not_a_pass() -> None:
    """A probe asserting the image tag alone is the mechanism that reported green in August."""
    with pytest.raises(ValueError, match="neither an HTTP probe nor a state reader"):
        wait_until_serving(spec(), current_image=lambda: NEW)


def test_the_failure_hint_reaches_the_error_line() -> None:
    """trading-mcp's and teams-mcp's per-module advice is the most useful part of their logs."""
    logged: list[str] = []

    wait_until_serving(
        spec(failure_hint="Its start-up refuses a non-demo gateway."),
        current_image=lambda: None,
        probe=lambda: (0, ""),
        sleep=lambda _: None,
        log=logged.append,
    )

    assert any("refuses a non-demo gateway" in line for line in logged)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (f"DOCKER|{NEW}", NEW),
        (NEW, NEW),
        (f"  DOCKER|{NEW}  ", NEW),
        (None, None),
        ("", None),
        # What `az --query ... -o tsv` prints for a site that has no such setting yet.
        ("None", None),
    ],
)
def test_normalise_image(raw: str | None, expected: str | None) -> None:
    assert normalise_image(raw) == expected


class TestMainWiring:
    """What `main` builds under the loop, since that is where the variant is chosen."""

    def test_an_empty_probe_path_builds_no_http_prober(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """capital-gateway is unreachable from a runner; an attempt would hang, not fail fast."""
        import deploy_probe

        def forbidden(*_: object, **__: object) -> object:
            raise AssertionError("no HTTP prober may be built for the control-plane variant")

        monkeypatch.setattr(deploy_probe, "http_prober", forbidden)
        monkeypatch.setattr(deploy_probe, "az_image_reader", lambda *_: lambda: f"DOCKER|{NEW}")
        monkeypatch.setattr(deploy_probe, "az_state_reader", lambda *_: lambda: "Running")

        code = deploy_probe.main(
            ["--app-name", "app-tradingcenter-gateway", "--expected-image", NEW, "--attempts", "1"]
        )

        assert code == 0

    def test_the_probe_url_is_the_app_hostname_plus_the_path(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import deploy_probe

        seen: list[str] = []

        def record(url: str, timeout: float = 20.0) -> object:
            seen.append(url)
            return lambda: (200, '{"status":"ok"}')

        monkeypatch.setattr(deploy_probe, "http_prober", record)
        monkeypatch.setattr(deploy_probe, "az_image_reader", lambda *_: lambda: f"DOCKER|{NEW}")

        code = deploy_probe.main(
            [
                "--app-name",
                "app-tradingcenter-market-mcp",
                "--expected-image",
                NEW,
                "--probe-path",
                "/health",
                "--body-contains",
                '"status"',
                "--attempts",
                "1",
            ]
        )

        assert code == 0
        assert seen == ["https://app-tradingcenter-market-mcp.azurewebsites.net/health"]

    def test_a_failure_leaves_a_non_zero_exit_code(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import deploy_probe

        monkeypatch.setattr(deploy_probe, "az_image_reader", lambda *_: lambda: f"DOCKER|{OLD}")
        monkeypatch.setattr(
            deploy_probe, "http_prober", lambda *_, **__: lambda: (200, '{"status":"ok"}')
        )

        code = deploy_probe.main(
            [
                "--app-name",
                "app-tradingcenter-agent",
                "--expected-image",
                NEW,
                "--probe-path",
                "/health",
                "--attempts",
                "1",
                "--sleep-seconds",
                "0",
            ]
        )

        assert code == 1

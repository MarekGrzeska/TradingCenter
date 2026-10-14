"""move-from-azure-to-vps — a package reaches its database by the password of its own role when the host is one the
operator named as private to this machine, and by nothing else off loopback. One file for all eight packages: the
rule is the same one, written eight times, and a test per copy would drift the way the copies did."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from workbench.config import Settings

PASSWORD = "s3cret-role-password"
PACKAGES = [
    "conversation",
    "teams",
    "polymarket",
    "social",
    "strategy",
    "market",
    "telegram",
    "youtube",
]
DATABASES = ["agent", "teams", "polymarket", "social", "strategy", "market", "telegram", "youtube"]


def _url(name: str, host: str, credential: str = f"{{name}}:{PASSWORD}") -> str:
    return f"postgresql://{credential.format(name=name)}@{host}:5432/{name}"


def _settings(host: str = "postgres", private_hosts: str = "postgres", credential: str | None = None):
    values = {f"{name}_database_url": _url(name, host, credential or f"{{name}}:{PASSWORD}") for name in DATABASES}
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        gateway_api_key="gateway-key",
        agent_openai_api_key="k",
        teams_openai_api_key="k",
        agent_default_model_id="m",
        agent_models=[MODEL],
        teams_models=[MODEL],
        private_hosts=private_hosts,
        **values,
    )


MODEL = {
    "id": "m",
    "model": "m",
    "display_name": "m",
    "cost_rank": 1,
    "input_rate_per_1m": 1,
    "output_rate_per_1m": 1,
}


@pytest.mark.parametrize("package", PACKAGES)
def test_a_private_host_with_a_role_and_password_is_a_database(package) -> None:
    resolved = getattr(_settings(), f"for_{package}")()
    assert resolved.database_user is None
    assert resolved.database_url.startswith("postgresql://")


@pytest.mark.parametrize("package", PACKAGES)
def test_a_host_nobody_named_is_refused_without_an_identity(package) -> None:
    settings = _settings(host="db.example.com", private_hosts="postgres")
    with pytest.raises(ValidationError, match="PRIVATE_HOSTS"):
        getattr(settings, f"for_{package}")()


@pytest.mark.parametrize("package", PACKAGES)
def test_a_private_host_without_a_password_is_refused(package) -> None:
    settings = _settings(credential="{name}")
    with pytest.raises(ValidationError, match="private host"):
        getattr(settings, f"for_{package}")()


@pytest.mark.parametrize("package", PACKAGES)
def test_a_refusal_never_prints_the_password(package) -> None:
    for settings in (
        _settings(host="db.example.com", private_hosts=""),
        _settings(credential="{name}"),
    ):
        with pytest.raises(ValidationError) as refused:
            getattr(settings, f"for_{package}")()
        assert PASSWORD not in str(refused.value)
        assert PASSWORD not in repr(settings)

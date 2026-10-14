import jwt
import pytest
from conftest import AUDIENCE, TENANT, V1_ISSUER

from tc_entra_auth.verifier import (
    KEY_LIFETIME,
    MIN_REFRESH_INTERVAL,
    InvalidToken,
    TokenVerifier,
    application_of,
)


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def verifier(tenant, clock=None, **kwargs):
    return TokenVerifier(
        tenant_id=TENANT,
        audiences=[AUDIENCE],
        fetch_keys=tenant.jwks,
        clock=clock or Clock(),
        **kwargs,
    )


async def test_a_v2_token_gives_its_application(tenant):
    claims = await verifier(tenant).verify(tenant.token())
    assert application_of(claims) == "terminal-app-id"


async def test_a_v1_token_is_read_by_appid_and_its_own_issuer(tenant):
    token = tenant.token(issuer=V1_ISSUER, application_claim="appid")
    claims = await verifier(tenant).verify(token)
    assert application_of(claims) == "terminal-app-id"


@pytest.mark.parametrize(
    "overrides",
    [
        {"issuer": "https://login.microsoftonline.com/other-tenant/v2.0"},
        {"audience": "api://somebody-else"},
        {"lifetime": -3600},
        {"not_before": 3600},
        {"drop": ("exp",)},
        {"drop": ("aud",)},
        {"drop": ("iss",)},
    ],
    ids=["issuer", "audience", "expired", "not-yet-valid", "no-exp", "no-aud", "no-iss"],
)
async def test_a_token_failing_one_claim_is_refused(tenant, overrides):
    with pytest.raises(InvalidToken):
        await verifier(tenant).verify(tenant.token(**overrides))


async def test_a_forged_signature_under_a_known_kid_is_refused(tenant):
    attacker = tenant.add_key("attacker")
    forged = tenant.token(kid="key-1", signer=attacker)
    with pytest.raises(InvalidToken):
        await verifier(tenant).verify(forged)


async def test_an_unsigned_token_is_refused(tenant):
    unsigned = jwt.encode({"iss": "x"}, key=None, algorithm="none", headers={"kid": "key-1"})
    with pytest.raises(InvalidToken, match="algorithm"):
        await verifier(tenant).verify(unsigned)


async def test_an_hmac_token_is_refused(tenant):
    # The classic confusion attack: HS256 with the RSA public key as the secret.
    secret = "any-secret-at-all-32-bytes-long!!!!"
    hs = jwt.encode({"iss": "x"}, secret, algorithm="HS256", headers={"kid": "key-1"})
    with pytest.raises(InvalidToken, match="algorithm"):
        await verifier(tenant).verify(hs)


async def test_a_string_that_is_not_a_token_is_refused(tenant):
    with pytest.raises(InvalidToken):
        await verifier(tenant).verify("not.a.token")


async def test_an_unknown_kid_is_refused(tenant):
    other = tenant.add_key("rotated")
    token = tenant.token(kid="rotated", signer=other)
    del tenant.keys["rotated"]
    with pytest.raises(InvalidToken, match="rotated"):
        await verifier(tenant).verify(token)


async def test_a_rotated_key_is_picked_up_on_the_first_token_that_names_it(tenant):
    clock = Clock()
    v = verifier(tenant, clock)
    await v.verify(tenant.token())
    tenant.add_key("rotated")
    clock.now += MIN_REFRESH_INTERVAL
    claims = await v.verify(tenant.token(kid="rotated"))
    assert application_of(claims) == "terminal-app-id"


async def test_garbage_kids_cost_one_fetch_a_minute(tenant):
    clock = Clock()
    v = verifier(tenant, clock)
    await v.verify(tenant.token())
    fetched = tenant.fetches
    stranger = tenant.add_key("stranger")
    token = tenant.token(kid="stranger", signer=stranger)
    del tenant.keys["stranger"]
    for _ in range(5):
        with pytest.raises(InvalidToken):
            await v.verify(token)
    assert tenant.fetches == fetched  # within the interval, no refetch at all
    clock.now += MIN_REFRESH_INTERVAL
    with pytest.raises(InvalidToken):
        await v.verify(token)
    assert tenant.fetches == fetched + 1


async def test_keys_already_held_survive_a_tenant_that_stops_answering(tenant):
    clock = Clock()
    v = verifier(tenant, clock)
    await v.verify(tenant.token())
    tenant.failing = True
    clock.now += KEY_LIFETIME + 1
    claims = await v.verify(tenant.token())
    assert application_of(claims) == "terminal-app-id"


async def test_a_tenant_that_never_answered_refuses_everything(tenant):
    tenant.failing = True
    with pytest.raises(InvalidToken):
        await verifier(tenant).verify(tenant.token())


def test_a_verifier_needs_a_tenant_and_an_audience():
    with pytest.raises(ValueError):
        TokenVerifier(tenant_id=" ", audiences=[AUDIENCE])
    with pytest.raises(ValueError):
        TokenVerifier(tenant_id=TENANT, audiences=[" "])

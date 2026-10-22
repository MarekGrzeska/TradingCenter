"""A tenant that signs tokens the way Entra does — RS256, a `kid` in the header, the same claim names — without the
network. Keys are generated per session; nothing here is a credential."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

TENANT = "11111111-2222-3333-4444-555555555555"
AUDIENCE = "api://tradingcenter-workbench"
V2_ISSUER = f"https://login.microsoftonline.com/{TENANT}/v2.0"
V1_ISSUER = f"https://sts.windows.net/{TENANT}/"


def _new_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@dataclass
class Tenant:
    keys: dict[str, rsa.RSAPrivateKey] = field(default_factory=dict)
    fetches: int = 0
    failing: bool = False

    def add_key(self, kid: str) -> rsa.RSAPrivateKey:
        self.keys[kid] = _new_key()
        return self.keys[kid]

    async def jwks(self) -> dict[str, Any]:
        self.fetches += 1
        if self.failing:
            raise RuntimeError("tenant unreachable")
        keys = []
        for kid, private in self.keys.items():
            jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private.public_key()))
            jwk.update({"kid": kid, "use": "sig", "alg": "RS256"})
            keys.append(jwk)
        return {"keys": keys}

    def token(
        self,
        *,
        kid: str = "key-1",
        signer: rsa.RSAPrivateKey | None = None,
        issuer: str = V2_ISSUER,
        audience: str = AUDIENCE,
        application_claim: str = "azp",
        application: str = "terminal-app-id",
        lifetime: float = 3600,
        not_before: float = 0,
        extra: dict[str, Any] | None = None,
        drop: tuple[str, ...] = (),
    ) -> str:
        now = int(time.time())
        claims: dict[str, Any] = {
            "iss": issuer,
            "aud": audience,
            "iat": now,
            "nbf": now + int(not_before),
            "exp": now + int(lifetime),
            application_claim: application,
            "oid": "person-object-id",
            "preferred_username": "operator@example.test",
            **(extra or {}),
        }
        for name in drop:
            claims.pop(name, None)
        return jwt.encode(
            claims, signer or self.keys[kid], algorithm="RS256", headers={"kid": kid}
        )


@pytest.fixture
def tenant() -> Tenant:
    t = Tenant()
    t.add_key("key-1")
    return t

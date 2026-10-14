# tc-entra-auth

The door for a server with no platform authenticator in front of it: Entra token verification in the process, and the
rule that turns it into the one caller identity a module's own records already read. A **build-time** dependency like
the other packages — see `docs/architecture.md`, "What may be shared, and what may not". Taken by `capital-gateway`,
`trading-mcp` and the workbench.

```
uv run pytest · uv run ruff check . · uv run pyright
```

## Why a package of its own

`tc-runtime` carries a database driver and `azure-*`; `capital-gateway` has no database and keeps clear of it on
purpose. The gateway still has to verify a token, so the verifier cannot live there
(`openspec/changes/move-from-azure-to-vps/design.md`, decision 13). New code with three consumers and no difference
between them but arguments is the second route to condition 1.

## What is in here

- `TokenVerifier` — an Entra access token, checked: RS256 only, signature against the tenant's JWKS, `iss` (v1 and v2),
  `aud`, `exp`, and `nbf` when present. Keys are cached for six hours, re-read at most once a minute when a token names
  a `kid` not held, and kept when the tenant stops answering. `application_of` reads `azp` (v2) or `appid` (v1).
- `EdgeAuth` — raw ASGI, outermost. A request carrying `X-TC-Edge` (written by the proxy, overwriting what came in) must
  carry a valid bearer token; one without it came from another service on the internal network and must carry the
  shared key. What passes leaves with an `X-MS-CLIENT-PRINCIPAL` the middleware wrote itself — one `azp` claim — and
  everything the client sent under that name is removed first, so `calling_application`, `CallerAccess` and the rest keep
  reading what they read behind Easy Auth.
- `EdgeConfig` — what a module tells the door: the verifier (`None` for a process nothing external may reach), the
  service key, the name a key-holder is given, the paths that need no proof (`exempt_paths`: a health probe, a handshake
  with its own ticket) and the ones whose handler checks the key itself (`key_paths`). Given directly or as a callable
  that returns `None` when the process is not a server and raises `LookupError` before its settings exist — a request
  in that gap is refused with a 503, never admitted.

## What it does not do

It does not decide who may reach what: that stays in each module's record. A valid token of an application nobody
listed passes this layer and is refused by the record.

Not yet measured against recorded tokens from the real tenant — the tests sign with a generated key, the way Entra does
(`tests/conftest.py`). `tasks.md` 1.4 keeps that open until the operator supplies a recorded pair.

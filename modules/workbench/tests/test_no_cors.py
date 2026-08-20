from __future__ import annotations

from starlette.middleware.cors import CORSMiddleware

from workbench.app import app


def test_the_app_adds_no_cors_middleware_of_its_own() -> None:
    # design.md / market_data.app's own comment: CORS is App Service's job
    # (infra/app-service.tf) — two layers each adding Access-Control-Allow-Origin
    # produce a header a browser rejects for carrying two values.
    #
    # One assertion for one application: the two surfaces' copies of this file were
    # asserting the same thing about the same object.
    assert not any(m.cls is CORSMiddleware for m in app.user_middleware)

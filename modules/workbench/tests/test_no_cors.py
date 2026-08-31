from __future__ import annotations

from starlette.middleware.cors import CORSMiddleware

from workbench.app import app


def test_the_app_adds_no_cors_middleware_of_its_own() -> None:
    # CORS is App Service's job: two layers each adding `Access-Control-Allow-Origin` produce a header a
    # browser rejects for carrying two values. One assertion for one application.
    assert not any(m.cls is CORSMiddleware for m in app.user_middleware)

from mcp.server.lowlevel.server import request_ctx
from mcp.shared.context import RequestContext
from starlette.requests import Request

from tc_mcp_kit.tool_call import request_header


def test_a_tool_call_reads_the_header_of_the_request_it_came_in():
    request = Request({"type": "http", "method": "POST", "path": "/mcp", "headers": [(b"x-person", b"person-1")]})
    token = request_ctx.set(RequestContext(1, None, None, None, request=request))  # type: ignore[arg-type]
    try:
        assert request_header("x-person") == "person-1"
        assert request_header("x-other") is None
    finally:
        request_ctx.reset(token)


def test_outside_a_tool_call_there_is_no_request():
    assert request_header("x-person") is None

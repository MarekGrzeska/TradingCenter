"""What the slimmer must not lose, alongside what it takes.

Every test here is one half of the same claim: the published schema costs less and allows
exactly what it allowed before. `jsonschema` is what says the second half — a document
validated against the schema before the change validates against it after.
"""

from __future__ import annotations

import json

import jsonschema
import pytest
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

from tc_mcp_kit.tool_schemas import slim_schema, slim_tool_schemas


def test_titles_go() -> None:
    slimmed = slim_schema({"title": "Symbol", "type": "string"})
    assert slimmed == {"type": "string"}


def test_titles_go_from_every_level() -> None:
    schema = {
        "title": "Reply",
        "type": "object",
        "$defs": {"Row": {"title": "Row", "properties": {"id": {"title": "Id", "type": "string"}}}},
        "properties": {"rows": {"title": "Rows", "items": {"$ref": "#/$defs/Row"}}},
    }
    assert json.dumps(slim_schema(schema)).count("title") == 0


def test_nullable_anyof_becomes_a_type_list() -> None:
    schema = {"anyOf": [{"type": "string"}, {"type": "null"}], "default": None}
    assert slim_schema(schema) == {"default": None, "type": ["string", "null"]}


def test_a_union_carrying_more_than_a_type_is_left_alone() -> None:
    """`format`, `items` and `$ref` are the difference between "this may be null" and a
    real union — collapsing those would change what the schema allows."""
    dated = {"anyOf": [{"format": "date-time", "type": "string"}, {"type": "null"}]}
    assert slim_schema(dated) == dated

    listed = {"anyOf": [{"items": {"type": "number"}, "type": "array"}, {"type": "null"}]}
    assert slim_schema(listed) == listed

    referenced = {"anyOf": [{"$ref": "#/$defs/Limits"}, {"type": "null"}]}
    assert slim_schema(referenced) == referenced


def test_an_anyof_next_to_its_own_type_is_left_alone() -> None:
    """Writing `type` twice would be the one way this could produce an invalid schema."""
    schema = {"type": "object", "anyOf": [{"type": "string"}, {"type": "null"}]}
    assert slim_schema(schema) == schema


def test_defaults_stay_on_the_way_in_and_go_on_the_way_out() -> None:
    schema = {"properties": {"limit": {"default": 200, "type": "integer"}}}
    assert slim_schema(schema, keep_defaults=True) == schema
    assert slim_schema(schema, keep_defaults=False) == {"properties": {"limit": {"type": "integer"}}}


def test_format_description_and_required_survive() -> None:
    schema = {
        "properties": {
            "at": {"format": "date-time", "title": "At", "type": "string"},
            "note": {"description": "why it did not settle", "title": "Note", "type": "string"},
        },
        "required": ["at"],
        "type": "object",
    }
    assert slim_schema(schema) == {
        "properties": {
            "at": {"format": "date-time", "type": "string"},
            "note": {"description": "why it did not settle", "type": "string"},
        },
        "required": ["at"],
        "type": "object",
    }


def test_the_caller_keeps_what_it_passed_in() -> None:
    schema = {"title": "Symbol", "type": "string"}
    slim_schema(schema)
    assert schema == {"title": "Symbol", "type": "string"}


class _Row(BaseModel):
    key: str
    value: float | None = Field(default=None, description="null until it settles")


class _Reply(BaseModel):
    symbol: str
    rows: list[_Row]
    note: str | None = None


@pytest.fixture
def server() -> FastMCP:
    mcp = FastMCP("kit-test")

    @mcp.tool()
    async def read(symbol: str, limit: int = 200, since: str | None = None) -> _Reply:
        """Two schemas with something to take off both."""
        return _Reply(symbol=symbol, rows=[])

    return mcp


async def test_a_registered_tool_loses_the_scaffolding(server: FastMCP) -> None:
    before = await server.list_tools()
    fat = json.dumps([t.model_dump(exclude_none=True) for t in before])

    slim_tool_schemas(server)

    after = await server.list_tools()
    lean = json.dumps([t.model_dump(exclude_none=True) for t in after])

    assert "title" not in json.dumps([t.inputSchema for t in after])
    assert "title" not in json.dumps([t.outputSchema for t in after])
    assert len(lean) < len(fat)


async def test_the_input_keeps_its_defaults_and_the_output_loses_them(server: FastMCP) -> None:
    slim_tool_schemas(server)
    tool = (await server.list_tools())[0]

    assert tool.inputSchema["properties"]["limit"]["default"] == 200
    assert tool.outputSchema is not None
    assert "default" not in json.dumps(tool.outputSchema)


async def test_a_reply_valid_before_is_valid_after(server: FastMCP) -> None:
    """The half that matters at runtime: the lowlevel server validates every structured
    reply against the published output schema."""
    before = (await server.list_tools())[0].outputSchema
    reply = {"symbol": "EURUSD", "rows": [{"key": "ema", "value": 1.2}], "note": None}
    assert before is not None
    jsonschema.validate(instance=reply, schema=before)

    slim_tool_schemas(server)

    after = (await server.list_tools())[0].outputSchema
    assert after is not None
    jsonschema.validate(instance=reply, schema=after)


async def test_a_reply_invalid_before_is_still_invalid(server: FastMCP) -> None:
    slim_tool_schemas(server)
    after = (await server.list_tools())[0].outputSchema
    assert after is not None
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance={"rows": []}, schema=after)

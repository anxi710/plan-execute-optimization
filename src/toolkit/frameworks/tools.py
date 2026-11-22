"""Bind tool declarations to their local execution handlers."""

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass


class ToolProtocolError(ValueError):
    """A tool decision failed before dispatch."""


@dataclass(frozen=True)
class FunctionTool:
    """Keep the model-visible contract and its async handler together."""

    name: str
    description: str
    parameters: dict
    handler: Callable[[dict, dict, dict], Awaitable]

    @property
    def schema(self):
        return {"type": "function", "function": {
            "name": self.name, "description": self.description, "parameters": self.parameters,
        }}


async def invoke_tool(event, tools):
    """Validate one tool call and invoke a tool from the current request."""
    response = event["response"]
    if response.get("finish_reason") == "length":
        raise ToolProtocolError("truncated_response")
    calls = response.get("tool_calls")
    if not isinstance(calls, list) or len(calls) != 1:
        raise ToolProtocolError("expected_single_tool_call")
    call = calls[0]
    if not isinstance(call, dict) or call.get("type") != "function" or not isinstance(call.get("function"), dict):
        raise ToolProtocolError("invalid_tool_call")
    available = {tool.name: tool for tool in tools}
    name = call["function"].get("name")
    if not isinstance(name, str) or name not in available:
        raise ToolProtocolError("unavailable_tool")
    if not isinstance(call.get("id"), str) or not call["id"].strip():
        raise ToolProtocolError("missing_tool_call_id")
    try:
        fields = json.loads(call["function"].get("arguments"))
    except (TypeError, json.JSONDecodeError) as error:
        raise ToolProtocolError("invalid_tool_arguments") from error
    if not isinstance(fields, dict):
        raise ToolProtocolError("invalid_tool_arguments")
    return await available[name].handler(event, call, fields)

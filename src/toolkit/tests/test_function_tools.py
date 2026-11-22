import json
import unittest
from unittest.mock import AsyncMock

from toolkit.frameworks.tools import FunctionTool, ToolProtocolError, invoke_tool


def decision(name, arguments='{"reason": "New evidence."}'):
    return {"response": {"tool_calls": [{
        "type": "function", "id": "call-1",
        "function": {"name": name, "arguments": arguments},
    }]}}


class FunctionToolTests(unittest.IsolatedAsyncioTestCase):
    def planning_tool(self, handler):
        return FunctionTool(
            name="request_plan", description="Request planning advice.",
            parameters={"type": "object", "properties": {"reason": {"type": "string"}}, "required": ["reason"]},
            handler=handler,
        )

    async def test_declared_name_dispatches_to_bound_handler_with_runtime_context(self):
        handler = AsyncMock(return_value="Updated plan.")
        tool = self.planning_tool(handler)
        event = decision(tool.schema["function"]["name"])

        self.assertEqual(await invoke_tool(event, [tool]), "Updated plan.")
        handler.assert_awaited_once_with(event, event["response"]["tool_calls"][0], {"reason": "New evidence."})
        self.assertEqual(set(tool.schema["function"]["parameters"]["properties"]), {"reason"})

        other_handler = AsyncMock(return_value="Other run's plan.")
        other_tool = self.planning_tool(other_handler)
        self.assertEqual(await invoke_tool(event, [other_tool]), "Other run's plan.")
        other_handler.assert_awaited_once()
        handler.assert_awaited_once()

    async def test_invalid_calls_never_invoke_handler(self):
        missing_call = {"response": {}}
        truncated = decision("request_plan")
        truncated["response"]["finish_reason"] = "length"
        multiple = decision("request_plan")
        multiple["response"]["tool_calls"] *= 2
        missing_id = decision("request_plan")
        del missing_id["response"]["tool_calls"][0]["id"]
        invalid_type = decision("request_plan")
        invalid_type["response"]["tool_calls"][0]["type"] = "other"
        for event, error in (
            (missing_call, "expected_single_tool_call"),
            (truncated, "truncated_response"),
            (multiple, "expected_single_tool_call"),
            (missing_id, "missing_tool_call_id"),
            (invalid_type, "invalid_tool_call"),
            (decision("execute_step"), "unavailable_tool"),
            (decision(["request_plan"]), "unavailable_tool"),
            (decision("request_plan", "{"), "invalid_tool_arguments"),
            (decision("request_plan", json.dumps([])), "invalid_tool_arguments"),
        ):
            with self.subTest(error=error, event=event):
                handler = AsyncMock()
                with self.assertRaisesRegex(ToolProtocolError, f"^{error}$"):
                    await invoke_tool(event, [self.planning_tool(handler)])
                handler.assert_not_awaited()

    async def test_handler_failure_propagates_without_replay(self):
        handler = AsyncMock(side_effect=RuntimeError("Dispatch failed."))
        with self.assertRaisesRegex(RuntimeError, "Dispatch failed"):
            await invoke_tool(decision("request_plan"), [self.planning_tool(handler)])
        handler.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()

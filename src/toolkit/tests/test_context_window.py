import unittest

from toolkit.models.context import ContextRecord, ContextWindow, ContextWindowExceeded


def prompt(records):
    return [{"role": "user", "content": "Task: keep the object.\n" + "\n".join(record.text for record in records)}]


def characters(payload):
    return len(payload["messages"][0]["content"])


class ContextWindowTests(unittest.TestCase):
    def test_no_limit_keeps_complete_records(self):
        records = [ContextRecord(1, "x" * 5000, (1,)), ContextRecord(4, "Latest observation.", (2,))]
        messages, metadata, visible = ContextWindow().prepare(records, prompt, protected={4})
        self.assertIn("x" * 5000, messages[0]["content"])
        self.assertEqual(metadata["kept_record_ids"], [1, 4])
        self.assertEqual(metadata["dropped_record_ids"], [])
        self.assertEqual(visible, {1, 2})
        self.assertEqual(metadata["count_method"], "utf8_bytes_conservative_estimate")

    def test_oldest_whole_record_is_removed(self):
        records = [ContextRecord(1, "OLD_REPLY_AND_FEEDBACK_" * 3, (1,)),
                   ContextRecord(4, "Middle reply and feedback.", (2,)),
                   ContextRecord(7, "Current reply and feedback.", (3,))]
        messages, metadata, visible = ContextWindow(90, characters).prepare(records, prompt, protected={7})
        self.assertEqual(metadata["kept_record_ids"], [4, 7])
        self.assertEqual(metadata["dropped_record_ids"], [1])
        self.assertNotIn("OLD_REPLY", messages[0]["content"])
        self.assertEqual(visible, {2, 3})
        self.assertEqual(metadata["dropped_observation_ids"], [1])

    def test_protected_context_overflow_is_explicit(self):
        records = [ContextRecord(1, "old", (1,)), ContextRecord(4, "LATEST" * 30, (2,))]
        with self.assertRaises(ContextWindowExceeded) as failure:
            ContextWindow(50, characters).prepare(records, prompt, protected={4})
        self.assertEqual(failure.exception.metadata["dropped_record_ids"], [1])
        self.assertEqual(failure.exception.metadata["kept_record_ids"], [4])
        self.assertIn("LATEST" * 30, failure.exception.messages[0]["content"])

    def test_discarded_history_stays_out_when_the_fixed_prompt_gets_shorter(self):
        records = [ContextRecord(1, "old" * 10, (1,)), ContextRecord(4, "current", (2,))]
        window = ContextWindow(50, characters)
        window.prepare(records, prompt, protected={4})
        messages, metadata, visible = window.prepare(
            records, lambda selected: [{"role": "user", "content": "\n".join(item.text for item in selected)}],
            protected={4},
        )
        self.assertEqual(messages[0]["content"], "current")
        self.assertEqual(metadata["dropped_record_ids"], [1])
        self.assertEqual(metadata["newly_dropped_record_ids"], [])
        self.assertEqual(visible, {2})

    def test_explicitly_required_evidence_can_return_without_resetting_the_window(self):
        records = [ContextRecord(1, "old" * 10, (1,)), ContextRecord(4, "current", (2,))]
        window = ContextWindow(50, characters)
        window.prepare(records, prompt, protected={4})
        shorter = lambda selected: [{"role": "user", "content": " ".join(item.text for item in selected)}]
        _, required, visible = window.prepare(records, shorter, protected={1, 4})
        self.assertEqual(required["kept_record_ids"], [1, 4])
        self.assertEqual(visible, {1, 2})
        _, later, visible = window.prepare(records, shorter, protected={4})
        self.assertEqual(later["kept_record_ids"], [4])
        self.assertEqual(visible, {2})

    def test_usage_feedback_does_not_sum_repeated_request_or_output_costs(self):
        window = ContextWindow(count_tokens=lambda payload: 100)
        _, first, _ = window.prepare([], prompt)
        window.observe(first, {"prompt_tokens": 120, "completion_tokens": 9000, "total_tokens": 9120})
        self.assertEqual(first["reported_input_tokens"], 120)
        self.assertEqual(first["reported_output_tokens"], 9000)
        _, second, _ = window.prepare([], prompt)
        self.assertEqual(second["estimated_input_tokens"], 120)
        window.observe(second, {"prompt_tokens": 115, "completion_tokens": 8000})
        self.assertEqual(window.prepare([], prompt)[1]["estimated_input_tokens"], 120)

    def test_entire_request_including_native_tools_and_handoff_is_counted(self):
        records = [ContextRecord(1, "old reply" * 8), ContextRecord(2, "current", (2,))]
        pair = [{"role": "assistant", "content": None, "tool_calls": [{"id": "call"}]},
                {"role": "tool", "tool_call_id": "call", "content": "tool result"}]

        def rendered(selected):
            return prompt(selected) + pair

        window = ContextWindow()
        _, without_tools, _ = window.prepare(records, rendered, protected={2})
        options = {"tools": [{"function": {"description": "planning tool" * 40}}]}
        _, with_tools, _ = window.prepare(records, rendered, protected={2}, model_options=options)
        self.assertGreater(with_tools["estimated_input_tokens"], without_tools["estimated_input_tokens"])
        limit = with_tools["estimated_input_tokens"] - 1
        messages, metadata, _ = ContextWindow(limit).prepare(records, rendered, protected={2}, model_options=options)
        self.assertEqual(metadata["dropped_record_ids"], [1])
        self.assertEqual(messages[-2:], pair)

    def test_invalid_capacity_or_counter_is_rejected(self):
        for capacity in (0, -1, True, 1.5):
            with self.subTest(capacity=capacity), self.assertRaises(ValueError):
                ContextWindow(capacity)
        with self.assertRaises(ValueError):
            ContextWindow(count_tokens=lambda payload: 0.5).prepare([], prompt)

"""Select whole interaction records for an explicitly bounded model input."""

import json
from dataclasses import dataclass


@dataclass(frozen=True)
class ContextRecord:
    record_id: int
    text: str
    observation_ids: tuple[int, ...] = ()


class ContextWindowExceeded(ValueError):
    """The fixed request and protected records do not fit the input budget."""

    def __init__(self, messages, metadata):
        super().__init__("The protected context exceeds max_input_tokens")
        self.messages = messages
        self.metadata = metadata


def _utf8_estimate(payload):
    # This is a conservative estimate, not the provider's tokenizer.
    return len(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


class ContextWindow:
    """Keep newest complete records, retaining a separate full event log."""

    def __init__(self, max_input_tokens=None, count_tokens=None):
        if max_input_tokens is not None and (type(max_input_tokens) is not int or max_input_tokens < 1):
            raise ValueError("max_input_tokens must be a positive integer or null")
        if count_tokens is not None and not callable(count_tokens):
            raise ValueError("count_tokens must be callable")
        self.max_input_tokens = max_input_tokens
        self.count_tokens = count_tokens or _utf8_estimate
        self.count_method = "injected_counter" if count_tokens else "utf8_bytes_conservative_estimate"
        self.observed_extra_tokens = 0
        self.discarded_record_ids = set()

    def prepare(self, records, render, *, protected=(), model_options=None):
        """Render and count the complete candidate after each oldest-record removal."""
        records = list(records)
        protected = set(protected)
        selected = [item for item in records
                    if item.record_id not in self.discarded_record_ids or item.record_id in protected]
        discarded = [item for item in records
                     if item.record_id in self.discarded_record_ids and item.record_id not in protected]
        newly_discarded = []
        while True:
            messages = render(selected)
            payload = {"messages": messages, **(model_options or {})}
            counted = self.count_tokens(payload)
            if type(counted) is not int or counted < 0:
                raise ValueError("The token counter must return a nonnegative integer")
            estimate = counted + self.observed_extra_tokens
            discarded_ids = {item.record_id for item in discarded}
            metadata = {
                "max_input_tokens": self.max_input_tokens,
                "estimated_input_tokens": estimate,
                "counter_input_tokens": counted,
                "count_method": self.count_method,
                "observed_extra_tokens": self.observed_extra_tokens,
                "kept_record_ids": [item.record_id for item in selected],
                "dropped_record_ids": [item.record_id for item in records if item.record_id in discarded_ids],
                "newly_dropped_record_ids": [item.record_id for item in newly_discarded],
                "protected_record_ids": [item.record_id for item in records if item.record_id in protected],
                "kept_observation_ids": sorted({ref for item in selected for ref in item.observation_ids}),
                "dropped_observation_ids": sorted({ref for item in discarded for ref in item.observation_ids}),
            }
            if self.max_input_tokens is None or estimate <= self.max_input_tokens:
                self.discarded_record_ids.update(item.record_id for item in discarded)
                return messages, metadata, set(metadata["kept_observation_ids"])
            oldest = next((item for item in selected if item.record_id not in protected), None)
            if oldest is None:
                raise ContextWindowExceeded(messages, metadata)
            selected.remove(oldest)
            discarded.append(oldest)
            newly_discarded.append(oldest)

    def observe(self, metadata, usage):
        """Record provider usage without summing repeated historical request costs."""
        usage = usage or {}
        for source, target in (("prompt_tokens", "reported_input_tokens"),
                               ("completion_tokens", "reported_output_tokens")):
            value = usage.get(source)
            if type(value) is int and value >= 0:
                metadata[target] = value
        actual = metadata.get("reported_input_tokens")
        if actual is not None:
            # Only increase the conservative estimate for observed gateway overhead.
            self.observed_extra_tokens = max(self.observed_extra_tokens,
                                             actual - metadata["counter_input_tokens"])

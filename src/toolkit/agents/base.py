"""Model call interface and provider-independent usage accounting."""

import asyncio
from abc import ABC, abstractmethod
from collections import Counter


class BaseModel(ABC):
    """Count logical calls and the responses reported by the backend."""

    def __init__(self):
        self.reset_usage()

    def reset_usage(self):
        self._requests = 0
        self._responses = 0
        self._usage_responses = 0
        self._tokens = Counter()
        self._response_models = set()

    def _record_response(self, *, token_usage, model):
        self._responses += 1
        if token_usage is not None:
            self._usage_responses += 1
            self._tokens.update(token_usage)
        if model:
            self._response_models.add(model)

    def usage_metadata(self):
        return {
            "requests": self._requests,
            "responses": self._responses,
            "usage_responses": self._usage_responses,
            "usage": dict(self._tokens),
            "response_models": sorted(self._response_models),
        }

    def __call__(self, messages):
        self._requests += 1
        return self._complete(messages)

    async def async_call(self, messages):
        self._requests += 1
        return await self._async_complete(messages)

    def continue_assistant(self, messages, prefix):
        self._requests += 1
        return self._complete(messages, prefix=prefix)

    async def async_continue_assistant(self, messages, prefix):
        self._requests += 1
        return await self._async_complete(messages, prefix=prefix)

    @abstractmethod
    def _complete(self, messages, *, prefix=None):
        """Return one reply and report the received response via _record_response."""

    async def _async_complete(self, messages, *, prefix=None):
        """Allow synchronous backends to participate in asynchronous rollouts."""
        return await asyncio.to_thread(self._complete, messages, prefix=prefix)

    def close(self):
        """Release any resources owned by the backend."""

    async def aclose(self):
        await asyncio.to_thread(self.close)

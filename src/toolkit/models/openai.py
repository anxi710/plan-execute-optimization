"""OpenAI-compatible model clients and usage accounting."""

import asyncio
import time
from contextlib import nullcontext

import openai

from .base import BaseModel


class AsyncChatClient:
    """Send OpenAI-compatible chat requests and return the original completion."""

    def __init__(self, *, base_url, api_key, timeout, max_retries=0, max_concurrency=None):
        if max_concurrency is not None and (type(max_concurrency) is not int or max_concurrency < 1):
            raise ValueError("max_concurrency must be a positive integer")
        self._limit = nullcontext() if max_concurrency is None else asyncio.Semaphore(max_concurrency)
        self._client = openai.AsyncOpenAI(
            base_url=base_url, api_key=api_key, timeout=timeout, max_retries=max_retries,
        )

    async def complete(self, **options):
        async with self._limit:
            return await self._client.chat.completions.create(**options)

    async def close(self):
        await self._client.close()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        await self.close()


class ModelRequestFailed(RuntimeError):
    code = "request_error"

    def __init__(self, error_type):
        self.error_type = error_type
        super().__init__(f"Model request failed ({error_type})")


class MeteredChatModel(BaseModel):
    """An OpenAI-compatible chat model with per-run usage counters."""

    TOKEN_FIELDS = (
        "prompt_tokens", "completion_tokens", "total_tokens",
        "prompt_cache_hit_tokens", "prompt_cache_miss_tokens",
    )

    def __init__(self, config):
        self.config = dict(config)
        if not self.config["model_name"]:
            raise ValueError("model_name is required")
        self.request_timeout = self.config["request_timeout"]
        self.request_max_retries = self.config["request_max_retries"]
        if self.request_timeout <= 0 or self.request_max_retries < 0:
            raise ValueError("Model timeout must be positive and retries nonnegative")
        self.stop_words = ["\nObservation:", "\nTask:", "\n---"]
        self.client = openai.OpenAI(**self._client_options())
        self._async_client = None
        self._sync_client_closed = False
        super().__init__()

    def _client_options(self):
        return {
            "base_url": self.config["api_base"],
            "api_key": self.config["api_key"],
            "timeout": self.request_timeout,
            "max_retries": 0,
        }

    def _request_options(self, messages, *, prefix=None):
        token_parameter = self.config["token_parameter"]
        if token_parameter not in ("max_tokens", "max_completion_tokens"):
            raise ValueError(f"Unsupported token parameter: {token_parameter}")
        options = {
            "model": self.config["model_name"],
            "messages": messages,
            token_parameter: self.config["max_completion_tokens"],
        }
        temperature = self.config["temperature"]
        if temperature is not None:
            options["temperature"] = temperature
        if self.config["send_stop"]:
            options["stop"] = self.stop_words
        seed = self.config["seed"]
        if seed is not None:
            options["seed"] = seed
        body = {}
        if prefix is not None:
            options["messages"] = messages + [{"role": "assistant", "content": prefix}]
            body.update(continue_final_message=True, add_generation_prompt=False)
        thinking = self.config["thinking"]
        if thinking is not None:
            body["thinking"] = {"type": thinking}
        reasoning_effort = self.config["reasoning_effort"]
        if reasoning_effort is not None:
            options["reasoning_effort"] = reasoning_effort
        if body:
            options["extra_body"] = body
        return options

    def _complete(self, messages, *, prefix=None):
        options = self._request_options(messages, prefix=prefix)
        for attempt in range(1, self.request_max_retries + 2):
            try:
                response = self.client.chat.completions.create(**options)
            except openai.APIError as error:
                if attempt > self.request_max_retries:
                    raise ModelRequestFailed(type(error).__name__) from None
                time.sleep(min(attempt, 2))
            else:
                return self._response_content(response)

    async def _async_complete(self, messages, *, prefix=None):
        options = self._request_options(messages, prefix=prefix)
        if self._async_client is None:
            self._async_client = AsyncChatClient(**self._client_options())
        for attempt in range(1, self.request_max_retries + 2):
            try:
                response = await self._async_client.complete(**options)
            except openai.APIError as error:
                if attempt > self.request_max_retries:
                    raise ModelRequestFailed(type(error).__name__) from None
                await asyncio.sleep(min(attempt, 2))
            else:
                return self._response_content(response)

    def _response_content(self, response):
        usage = getattr(response, "usage", None)
        token_usage = None
        if usage is not None:
            token_usage = {}
            for field in self.TOKEN_FIELDS:
                count = getattr(usage, field, None)
                if count is not None:
                    token_usage[field] = count
        self._record_response(token_usage=token_usage, model=getattr(response, "model", None))
        content = response.choices[0].message.content
        if not isinstance(content, str) or not content.strip():
            raise ValueError("Model returned an empty message")
        return content

    def close(self):
        if not self._sync_client_closed:
            self.client.close()
            self._sync_client_closed = True

    async def aclose(self):
        try:
            if self._async_client is not None:
                await self._async_client.close()
                self._async_client = None
        finally:
            self.close()

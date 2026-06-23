from __future__ import annotations

import asyncio

import random

import time

import threading

from dataclasses import dataclass, field

from typing import Any, Callable

# ---------------------------------------------------------------------------

# What a shadow run produces

# ---------------------------------------------------------------------------

@dataclass

class InterceptedToolCall:

    """A tool call the shadow agent formulated but did not execute."""

    tool_name:      str

    parameters:     dict[str, Any]

    intercepted_at: float = field(default_factory=time.monotonic)

@dataclass

class ShadowResponse:

    """

    The complete output of a shadow execution: text the candidate would

    have returned and tool calls it would have made. Stored for the

    Behavioral Diff comparison in the next section.

    """

    request_id:        str

    shadow_version:    str

    generated_text:    str

    intercepted_calls: list[InterceptedToolCall]

    latency_ms:        float

    token_usage:       dict[str, int]

    error:             str | None = None

# ---------------------------------------------------------------------------

# Tool interceptor: the heart of safe shadow execution

# ---------------------------------------------------------------------------

class ShadowToolInterceptor:

    """

    Replaces the real tool registry during shadow execution.

    Records every tool call the candidate agent attempts.

    Returns a synthetic result so the agent can continue reasoning

    as if the tool had responded normally.

    synthetic_results should reflect typical successful tool responses.

    Returning an empty dict for every call is technically valid but

    may cause the candidate to produce atypical downstream reasoning,

    making the comparison with production less meaningful.

    """

    def __init__(self, synthetic_results: dict[str, Any] | None = None) -> None:

        self._synthetic = synthetic_results or {}

        self.call_log:  list[InterceptedToolCall] = []

    def __call__(self, tool_name: str, parameters: Any) -> Any:

        self.call_log.append(

            InterceptedToolCall(tool_name=tool_name, parameters=parameters)

        )

        # Return a synthetic result. Never raise: a tool error in shadow

        # mode skews the candidate's reasoning away from what it would

        # produce in production, invalidating the comparison.

        return self._synthetic.get(tool_name, {})

# ---------------------------------------------------------------------------

# Shadow router

# ---------------------------------------------------------------------------

class ShadowRouter:

    """

    Runs the production handler and, for sampled requests, runs the

    candidate handler in shadow mode asynchronously.

    The production response is always what the caller receives.

    The shadow run never blocks the production response path.

    The shadow response is stored for behavioral comparison.

    sample_rate: fraction of requests that receive a shadow run.

    Set based on cost tolerance. 0.10 (10%) is a practical starting point

    for most systems. Shadow calls consume real LLM tokens; route them

    through Protocol 2.5's tier system the same way production calls are.

    """

    def __init__(

        self,

        production_handler: Callable[[Any], dict],

        shadow_handler:     Callable[[Any, ShadowToolInterceptor], dict],

        shadow_version:     str,

        shadow_store,        # Any object with a store(ShadowResponse) method.

        synthetic_results:  dict[str, Any] | None = None,

        sample_rate:        float = 0.10,

    ) -> None:

        self._production   = production_handler

        self._shadow       = shadow_handler

        self._version      = shadow_version

        self._store        = shadow_store

        self._synthetic    = synthetic_results or {}

        self._sample_rate  = sample_rate

    def handle(self, request_id: str, request: Any) -> Any:

        """

        Always executes the production path and returns its result.

        Schedules a shadow run asynchronously for sampled requests.

        """

        production_result = self._production(request)

        if random.random() < self._sample_rate:

            self._dispatch_shadow(request_id, request)

        return production_result

    def _dispatch_shadow(self, request_id: str, request: Any) -> None:

        """

        Runs the shadow execution without blocking the production response.

        Uses the event loop if one is running; falls back to a daemon thread.

        """

        async def _run() -> None:

            await self._execute_shadow(request_id, request)

        try:

            loop = asyncio.get_running_loop()

            loop.create_task(_run())

        except RuntimeError:

            threading.Thread(

                target=lambda: asyncio.run(_run()),

                daemon=True,

            ).start()

    async def _execute_shadow(self, request_id: str, request: Any) -> None:

        interceptor = ShadowToolInterceptor(self._synthetic)

        start = time.monotonic()

        error: str | None = None

        try:

            result = self._shadow(request, interceptor)

            text   = result.get("text", "")

            usage  = result.get("usage", {})

        except Exception as exc:

            text  = ""

            usage = {}

            error = str(exc)

        self._store.store(ShadowResponse(

            request_id=request_id,

            shadow_version=self._version,

            generated_text=text,

            intercepted_calls=interceptor.call_log,

            latency_ms=(time.monotonic() - start) * 1000,

            token_usage=usage,

            error=error,

        ))

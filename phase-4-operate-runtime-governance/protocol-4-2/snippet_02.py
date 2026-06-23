from __future__ import annotations

import threading

import time

from dataclasses import dataclass, field

class CircuitBreakerTripped(Exception):

    """

    Raised when a thread exceeds its token budget.

    Carries the full diagnostic context so the halt event can be logged

    with forensic detail before the execution thread is terminated.

    Callers must not catch this exception and resume execution.

    """

    def __init__(

        self,

        thread_id: str,

        total_tokens: int,

        limit: int,

        reason: str,

    ) -> None:

        self.thread_id = thread_id

        self.total_tokens = total_tokens

        self.limit = limit

        self.reason = reason

        super().__init__(

            f"Circuit breaker tripped on thread '{thread_id}': "

            f"{total_tokens:,} tokens consumed against a limit of {limit:,}. "

            f"Reason: {reason}"

        )

@dataclass

class TokenBudget:

    """

    Per-thread token budget configuration.

    Both limits apply simultaneously; whichever is crossed first halts the thread.

    Thresholds should be set from the P95 token usage of successful runs in

    your environment, not picked arbitrarily.

    """

    max_tokens_per_thread: int = 50_000   # Hard ceiling per workflow execution.

    max_tokens_per_minute: int = 20_000   # Rate anomaly ceiling.

    window_seconds:        int = 60

class ThreadTokenTracker:

    """

    In-memory, thread-safe token counter for a single execution thread.

    Created at the start of each workflow run and passed through the

    orchestration layer. Enforcement is synchronous and does not depend

    on the observability backend being reachable or queryable in real time.

    """

    def __init__(self, thread_id: str, budget: TokenBudget) -> None:

        self.thread_id = thread_id

        self.budget = budget

        self._lock = threading.Lock()

        self._total: int = 0

        self._window: list[tuple[float, int]] = []  # (monotonic_time, tokens)

    def record_and_check(self, tokens_used: int) -> None:

        """

        Record token usage for the most recent LLM call and enforce both

        budget limits. Call this immediately after every LLM call returns,

        before any downstream logic runs on the response.

        Raises CircuitBreakerTripped on the first limit crossed.

        The exception carries all the data needed for a forensic halt log.

        """

        with self._lock:

            now = time.monotonic()

            self._total += tokens_used

            # Maintain the sliding window for rate detection.

            self._window.append((now, tokens_used))

            cutoff = now - self.budget.window_seconds

            self._window = [(ts, t) for ts, t in self._window if ts >= cutoff]

            rate_total = sum(t for _, t in self._window)

            # Hard ceiling check.

            if self._total > self.budget.max_tokens_per_thread:

                raise CircuitBreakerTripped(

                    thread_id=self.thread_id,

                    total_tokens=self._total,

                    limit=self.budget.max_tokens_per_thread,

                    reason=(

                        f"Cumulative consumption of {self._total:,} tokens exceeded "

                        f"the per-thread hard ceiling of "

                        f"{self.budget.max_tokens_per_thread:,}."

                    ),

                )

            # Rate-based anomaly check.

            if rate_total > self.budget.max_tokens_per_minute:

                raise CircuitBreakerTripped(

                    thread_id=self.thread_id,

                    total_tokens=self._total,

                    limit=self.budget.max_tokens_per_minute,

                    reason=(

                        f"Token rate of {rate_total:,} tokens in the last "

                        f"{self.budget.window_seconds}s exceeded the anomaly "

                        f"ceiling of {self.budget.max_tokens_per_minute:,}. "

                        f"Possible runaway loop."

                    ),

                )

    @property

    def total(self) -> int:

        with self._lock:

            return self._total

# ---------------------------------------------------------------------------

# Integration in the orchestration layer.

# The tracker is initialized once per workflow run and passed through

# every state in the FSM. The circuit breaker check happens after every

# LLM call, before any downstream logic processes the response.

# ---------------------------------------------------------------------------

def run_workflow_step(

    state: dict,

    call_llm_fn,

    token_tracker: ThreadTokenTracker,

) -> str:

    """

    Execute one step of the workflow with circuit breaker enforcement.

    If the token budget is exceeded, CircuitBreakerTripped propagates

    to the FSM boundary handler, which writes the halt event and stops

    the execution thread.

    """

    messages = build_messages(state)

    response_text, usage = call_llm_fn(messages)

    # Budget check: runs synchronously, before anything else sees the response.

    token_tracker.record_and_check(usage["total_tokens"])

    return response_text

from __future__ import annotations

import hashlib

from dataclasses import dataclass, field

from enum import Enum

from typing import Optional

# ---------------------------------------------------------------------------

# Health status levels

# ---------------------------------------------------------------------------

class ContextHealthStatus(str, Enum):

    HEALTHY   = "healthy"    # No action needed.

    WARNING   = "warning"    # Begin monitoring more closely.

    DEGRADED  = "degraded"   # Prepare compression or summarization.

    CRITICAL  = "critical"   # Mandatory intervention before next LLM call.

# ---------------------------------------------------------------------------

# Input signals for the health evaluation

# ---------------------------------------------------------------------------

@dataclass

class ContextHealthSignals:

    """

    All inputs the monitor needs to evaluate context health.

    Collected by the orchestration layer at every FSM state transition.

    token_count           -- cumulative tokens consumed by this thread so far.

    model_context_limit   -- the published context window size for the active model.

    recent_validations    -- list of bool outcomes for the last N schema validations

                             in this thread. True = passed, False = failed.

    tool_call_log         -- list of (tool_name, params_hash) tuples for every

                             tool call made in this thread, in chronological order.

    validation_window     -- how many recent validation outcomes to consider.

    repetition_lookback   -- how many recent tool calls to check for repetition.

    """

    token_count:         int

    model_context_limit: int

    recent_validations:  list[bool]        = field(default_factory=list)

    tool_call_log:       list[tuple[str, str]] = field(default_factory=list)

    validation_window:   int               = 8

    repetition_lookback: int               = 6

# ---------------------------------------------------------------------------

# The monitor

# ---------------------------------------------------------------------------

@dataclass(frozen=True)

class HealthEvaluation:

    status:        ContextHealthStatus

    token_ratio:   float

    reasons:       list[str]

class ContextHealthMonitor:

    """

    Evaluates the health of a running Harness Mode thread based on

    observable signals available to the orchestration layer.

    No model inference happens here. Every check is deterministic.

    The monitor never looks inside the model's reasoning -- it looks

    at the artifacts the orchestration layer already has: token counts,

    validation outcomes, and tool call patterns.

    Thresholds are tunable at construction time. Calibrate them

    against your system's observed degradation patterns using the

    RAG evaluation baselines from Protocol 5.2 as a reference point

    for what "acceptable output quality" looks like.

    """

    def __init__(

        self,

        token_warning_ratio:   float = 0.45,

        token_degraded_ratio:  float = 0.65,

        token_critical_ratio:  float = 0.78,

        validation_fail_warn:  float = 0.20,

        validation_fail_crit:  float = 0.40,

    ) -> None:

        self._warn_ratio  = token_warning_ratio

        self._deg_ratio   = token_degraded_ratio

        self._crit_ratio  = token_critical_ratio

        self._val_warn    = validation_fail_warn

        self._val_crit    = validation_fail_crit

    def evaluate(self, signals: ContextHealthSignals) -> HealthEvaluation:

        """

        Runs all checks and returns the worst observed status

        along with the specific reasons that triggered it.

        """

        reasons: list[str] = []

        worst   = ContextHealthStatus.HEALTHY

        token_ratio = signals.token_count / max(signals.model_context_limit, 1)

        token_status, token_reason = self._check_token_ratio(token_ratio)

        if token_reason:

            reasons.append(token_reason)

        worst = self._escalate(worst, token_status)

        val_status, val_reason = self._check_validation_rate(signals)

        if val_reason:

            reasons.append(val_reason)

        worst = self._escalate(worst, val_status)

        rep_status, rep_reason = self._check_tool_repetition(signals)

        if rep_reason:

            reasons.append(rep_reason)

        worst = self._escalate(worst, rep_status)

        return HealthEvaluation(

            status=worst,

            token_ratio=round(token_ratio, 3),

            reasons=reasons,

        )

    # ------------------------------------------------------------------

    # Individual signal checks

    # ------------------------------------------------------------------

    def _check_token_ratio(

        self, ratio: float

    ) -> tuple[ContextHealthStatus, Optional[str]]:

        if ratio >= self._crit_ratio:

            return (

                ContextHealthStatus.CRITICAL,

                f"Token usage at {ratio:.1%} of context limit -- "

                f"attention degradation likely. Immediate compression required.",

            )

        if ratio >= self._deg_ratio:

            return (

                ContextHealthStatus.DEGRADED,

                f"Token usage at {ratio:.1%} -- prepare summarization "

                f"at next FSM state boundary.",

            )

        if ratio >= self._warn_ratio:

            return (

                ContextHealthStatus.WARNING,

                f"Token usage at {ratio:.1%} -- monitor closely.",

            )

        return ContextHealthStatus.HEALTHY, None

    def _check_validation_rate(

        self, signals: ContextHealthSignals

    ) -> tuple[ContextHealthStatus, Optional[str]]:

        window = signals.recent_validations[-signals.validation_window:]

        if not window:

            return ContextHealthStatus.HEALTHY, None

        fail_rate = sum(1 for v in window if not v) / len(window)

        if fail_rate >= self._val_crit:

            return (

                ContextHealthStatus.CRITICAL,

                f"Schema validation failing on {fail_rate:.0%} of recent calls "

                f"in this thread -- output quality in critical decline.",

            )

        if fail_rate >= self._val_warn:

            return (

                ContextHealthStatus.DEGRADED,

                f"Schema validation failing on {fail_rate:.0%} of recent calls "

                f"-- possible context-driven output degradation.",

            )

        return ContextHealthStatus.HEALTHY, None

    def _check_tool_repetition(

        self, signals: ContextHealthSignals

    ) -> tuple[ContextHealthStatus, Optional[str]]:

        recent = signals.tool_call_log[-signals.repetition_lookback:]

        if len(recent) < 2:

            return ContextHealthStatus.HEALTHY, None

        # A repeated call is an (tool_name, params_hash) pair that

        # appears more than once in the recent window.

        seen: set[tuple[str, str]] = set()

        duplicates: set[tuple[str, str]] = set()

        for call in recent:

            if call in seen:

                duplicates.add(call)

            seen.add(call)

        if duplicates:

            dup_names = ", ".join(f"'{t}'" for t, _ in duplicates)

            return (

                ContextHealthStatus.DEGRADED,

                f"Tool repetition detected in current thread: {dup_names}. "

                f"Agent is re-requesting results it already received -- "

                f"context history likely no longer reliable.",

            )

        return ContextHealthStatus.HEALTHY, None

    # ------------------------------------------------------------------

    # Utility

    # ------------------------------------------------------------------

    @staticmethod

    def _escalate(

        current: ContextHealthStatus,

        candidate: ContextHealthStatus,

    ) -> ContextHealthStatus:

        order = [

            ContextHealthStatus.HEALTHY,

            ContextHealthStatus.WARNING,

            ContextHealthStatus.DEGRADED,

            ContextHealthStatus.CRITICAL,

        ]

        return candidate if order.index(candidate) > order.index(current) else current

    @staticmethod

    def hash_tool_call(tool_name: str, params: dict) -> tuple[str, str]:

        """

        Produces a stable (tool_name, params_hash) pair for the tool

        call log. Use this in your orchestration layer every time a

        tool invocation is recorded, before appending to the log.

        """

        raw    = str(sorted(params.items()))

        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

        return tool_name, digest

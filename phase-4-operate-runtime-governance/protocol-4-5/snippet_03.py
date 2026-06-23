from __future__ import annotations

import psycopg2

import redis

from enum import Enum

class FailoverErrorAction(str, Enum):

    RETRY_WITH_BACKOFF  = "retry_with_backoff"   # Transient; will resolve on reconnect.

    FAIL_CLOSED         = "fail_closed"           # Security: deny, do not retry blindly.

    HALT_AND_ESCALATE   = "halt_and_escalate"     # Data integrity: stop the thread.

    CONTINUE            = "continue"              # Non-critical path; proceed safely.

class FailoverErrorClassifier:

    """

    Classifies connection errors that occur during a zone failover

    and returns the correct action for each.

    This classifier is called by the orchestration layer whenever

    a connection error surfaces during active thread execution.

    It does not attempt to recover; it tells the caller what to do.

    The classification is deterministic and has no LLM in its path.

    Zone outages are exactly the wrong moment to introduce probabilistic

    reasoning into your error handling.

    """

    def classify(self, error: Exception, context: str) -> FailoverErrorAction:

        """

        context: one of "checkpoint_read", "checkpoint_write",

                 "kill_switch_read", "llm_api_call", "tool_call",

                 "telemetry_write"

        """

        is_pg_connection  = isinstance(error, psycopg2.OperationalError)

        is_redis_error    = isinstance(error, redis.RedisError)

        if context == "kill_switch_read":

            # An unverifiable revocation status is a security failure.

            # Deny the action regardless of error type or duration.

            return FailoverErrorAction.FAIL_CLOSED

        if context == "checkpoint_write" and is_pg_connection:

            # A failed checkpoint write means thread state may be lost.

            # Do not allow the FSM to advance without a confirmed write.

            return FailoverErrorAction.HALT_AND_ESCALATE

        if context == "checkpoint_read" and is_pg_connection:

            # Can't load thread state. Retry until the standby is promoted.

            # ResilientCheckpointConnection handles the retry loop.

            return FailoverErrorAction.RETRY_WITH_BACKOFF

        if context == "llm_api_call":

            # The LLM provider is external to your infrastructure.

            # A connection error here is almost always your network failing,

            # not the provider. Retry with backoff.

            return FailoverErrorAction.RETRY_WITH_BACKOFF

        if context == "tool_call":

            # Tool calls are covered by the write-ahead log.

            # Halt this execution; the recovery router will classify

            # the pending intent record on restart.

            return FailoverErrorAction.HALT_AND_ESCALATE

        if context == "telemetry_write":

            # Losing a telemetry span during failover is acceptable.

            # Do not halt the thread for an observability failure.

            return FailoverErrorAction.CONTINUE

        # Default: halt rather than guess.

        return FailoverErrorAction.HALT_AND_ESCALATE

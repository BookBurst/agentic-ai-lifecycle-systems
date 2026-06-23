from __future__ import annotations

from dataclasses import dataclass

from enum import Enum

from typing import Any, Callable

class AuditOutcome(str, Enum):

    APPROVED  = "approved"

    BLOCKED   = "blocked"

    CORRECTED = "corrected"

@dataclass

class ToolInvocationIntent:

    """

    The semantic intent the Target Agent has formulated.

    Created at the Trap phase; evaluated at the Audit phase.

    The real tool function is never called until the Visor clears this.

    """

    tool_name:  str

    parameters: dict[str, Any]

    thread_id:  str

    agent_goal: str

@dataclass

class AuditResult:

    outcome:              AuditOutcome

    reason:               str

    corrected_parameters: dict[str, Any] | None = None

class ToolInvocationBlocked(Exception):

    """Raised when the Visor denies a tool invocation after audit."""

    def __init__(self, intent: ToolInvocationIntent, reason: str) -> None:

        self.intent = intent

        self.reason = reason

        super().__init__(

            f"Visor blocked '{intent.tool_name}' on thread '{intent.thread_id}'. "

            f"Reason: {reason}"

        )

class SemanticVisor:

    """

    The trusted control layer in the AgentVisor architecture.

    Evaluates every tool invocation intent before it reaches any

    external system. Runs outside the Target Agent's semantic domain.

    The audit logic is deterministic: policy rules in code, not

    another LLM. Replacing one probabilistic model with another

    to validate the first shifts the attack surface; it does not

    eliminate it.

    """

    def __init__(

        self,

        allowed_tools: frozenset[str],

        policy_rules:  list[Callable[[ToolInvocationIntent], AuditResult | None]],

    ) -> None:

        self._allowed_tools = allowed_tools

        self._policy_rules  = policy_rules

    def trap(self, intent: ToolInvocationIntent) -> AuditResult:

        """Phase 1 (Trap): intercept and route to audit."""

        return self._audit(intent)

    def _audit(self, intent: ToolInvocationIntent) -> AuditResult:

        """

        Phase 2 (Audit): evaluate against policy rules in order.

        First matching rule determines the outcome.

        No match -> approved by default.

        """

        if intent.tool_name not in self._allowed_tools:

            return AuditResult(

                outcome=AuditOutcome.BLOCKED,

                reason=(

                    f"Tool '{intent.tool_name}' is not in the authorized set "

                    f"for thread '{intent.thread_id}'. Possible injection."

                ),

            )

        for rule in self._policy_rules:

            result = rule(intent)

            if result is not None:

                return result

        return AuditResult(outcome=AuditOutcome.APPROVED, reason="All policy checks passed.")

    def recover(

        self,

        intent: ToolInvocationIntent,

        result: AuditResult,

    ) -> dict[str, Any] | None:

        """

        Phase 3 (Recover): handle a non-approved audit result.

        BLOCKED  -> log forensic event, raise ToolInvocationBlocked.

        CORRECTED -> log correction, return corrected parameters.

        """

        if result.outcome == AuditOutcome.BLOCKED:

            _log_visor_block(intent, result.reason)

            raise ToolInvocationBlocked(intent, result.reason)

        if result.outcome == AuditOutcome.CORRECTED:

            _log_visor_correction(intent, result)

            return result.corrected_parameters

        return None

def dispatch_tool(

    tool_name:     str,

    parameters:    dict[str, Any],

    thread_id:     str,

    agent_goal:    str,

    visor:         SemanticVisor,

    tool_registry: dict[str, Callable],

) -> Any:

    """

    The single entry point for all tool calls in the orchestration layer.

    The Target Agent never calls tools directly. Every invocation passes

    through this function. If the Visor blocks, the tool never fires.

    """

    intent = ToolInvocationIntent(

        tool_name=tool_name,

        parameters=parameters,

        thread_id=thread_id,

        agent_goal=agent_goal,

    )

    audit_result = visor.trap(intent)

    if audit_result.outcome != AuditOutcome.APPROVED:

        corrected = visor.recover(intent, audit_result)

        if corrected is not None:

            parameters = corrected

        # If BLOCKED, recover() raised ToolInvocationBlocked above.

    return tool_registry[tool_name](**parameters)

from __future__ import annotations

import re

from dataclasses import dataclass

from decimal import Decimal

class SecurityViolation(Exception):

    """

    Raised when a schema-valid LLM output violates an operational

    security policy. This is distinct from OutputParseError: format

    errors are retried; security violations halt the thread immediately

    and route to the audit queue. Never catch this exception and continue.

    """

@dataclass(frozen=True)

class SecurityContext:

    """

    Runtime context threaded into every security check.

    Immutable by design: policy decisions must not modify execution state.

    """

    thread_id:          str

    authorized_agents:  frozenset[str]

    max_autonomous_charge: Decimal

    customer_id:        str

# Patterns that should never appear inside an LLM-generated rationale field.

# Their presence suggests the model read something it should not have,

# and is now about to propagate that data into an action payload.

_SENSITIVE_DATA_PATTERNS = re.compile(

    r"(sk-[a-zA-Z0-9]{32,}|"           # API key formats

    r"[a-z]+://[^\s]+:[^\s]+@[^\s]+|"  # Credentials in URI form

    r"\b(?:\d{4}[- ]?){3}\d{4}\b)",    # 16-digit card numbers

    re.IGNORECASE,

)

class SecurityPolicy:

    """

    Deterministic post-validation security layer.

    Runs after Pydantic confirms the output is structurally valid.

    Each method enforces one rule and raises SecurityViolation on breach.

    No method returns a modified or sanitized output: enforcement is binary.

    """

    def __init__(self, context: SecurityContext) -> None:

        self.ctx = context

    def enforce(self, decision: RouteDecision) -> None:

        """

        Apply all security checks in sequence.

        The first violation raises immediately; remaining checks are skipped.

        Callers must not catch SecurityViolation and resume execution.

        """

        self._check_agent_authorization(decision)

        self._check_financial_threshold(decision)

        self._check_rationale_for_sensitive_data(decision)

    def _check_agent_authorization(self, decision: RouteDecision) -> None:

        if decision.target_agent.value not in self.ctx.authorized_agents:

            raise SecurityViolation(

                f"Thread '{self.ctx.thread_id}' attempted to route to agent "

                f"'{decision.target_agent.value}', which is not in the authorized "

                f"set for this execution context: {self.ctx.authorized_agents}. "

                f"Possible privilege escalation. Halting."

            )

    def _check_financial_threshold(self, decision: RouteDecision) -> None:

        """

        Any charge action above the autonomous execution threshold must have

        requires_human_approval set to True. If the model returned False,

        it is not a configuration error in the calling code: it is the model

        making an autonomous financial commitment it is not authorized to make.

        """

        if (

            decision.action == "charge_customer"

            and not decision.requires_human_approval

            and self.ctx.max_autonomous_charge > Decimal("0.00")

        ):

            raise SecurityViolation(

                f"Charge action for customer '{self.ctx.customer_id}' "

                f"exceeds the autonomous execution ceiling "

                f"(${self.ctx.max_autonomous_charge:.2f}) but "

                f"requires_human_approval is False. Halting."

            )

    def _check_rationale_for_sensitive_data(self, decision: RouteDecision) -> None:

        if _SENSITIVE_DATA_PATTERNS.search(decision.rationale):

            raise SecurityViolation(

                f"The rationale field in thread '{self.ctx.thread_id}' contains "

                f"a pattern consistent with sensitive data (API key, credential URI, "

                f"or card number). The model may have read and is propagating "

                f"data it should not have accessed. Halting to prevent exfiltration."

            )

# --- Integration at the state boundary ---

def execute_route_decision(

    decision: RouteDecision,

    context: SecurityContext,

) -> None:

    """

    Apply security policy, then dispatch.

    Both SecurityViolation and OutputParseError produce a hard halt;

    they are logged to separate audit channels because they represent

    different failure classes and require different remediation paths.

    """

    policy = SecurityPolicy(context)

    policy.enforce(decision)         # raises SecurityViolation on any breach

    dispatch_to_agent(decision.target_agent, decision)

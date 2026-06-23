from __future__ import annotations

from dataclasses import dataclass

from enum import Enum

from typing import Any

# ---------------------------------------------------------------------------

# Task complexity tiers

# ---------------------------------------------------------------------------

class TaskTier(str, Enum):

    LIGHTWEIGHT = "lightweight"

    STANDARD    = "standard"

    FRONTIER    = "frontier"

# ---------------------------------------------------------------------------

# Model configuration per tier

# ---------------------------------------------------------------------------

@dataclass(frozen=True)

class ModelConfig:

    """

    Immutable configuration for a model tier.

    The orchestration layer reads this at runtime; it never asks the

    model itself which config to use.

    """

    model_id:        str

    max_tokens:      int

    temperature:     float

    timeout_seconds: int

# ---------------------------------------------------------------------------

# The router: maps tier to config, dispatches calls

# ---------------------------------------------------------------------------

class ModelRouter:

    """

    Deterministic routing from TaskTier to ModelConfig.

    The tier is declared by the FSM state at design time.

    No inference happens here; this is a dictionary lookup.

    Wire the three configs to whatever provider tiers match your

    cost and latency requirements. The router doesn't care which

    providers you use as long as the callable interface is consistent.

    """

    def __init__(

        self,

        lightweight_config: ModelConfig,

        standard_config:    ModelConfig,

        frontier_config:    ModelConfig,

    ) -> None:

        self._registry: dict[TaskTier, ModelConfig] = {

            TaskTier.LIGHTWEIGHT: lightweight_config,

            TaskTier.STANDARD:    standard_config,

            TaskTier.FRONTIER:    frontier_config,

        }

    def config_for(self, tier: TaskTier) -> ModelConfig:

        return self._registry[tier]

    def call(

        self,

        tier:     TaskTier,

        messages: list[dict[str, str]],

        call_fn:  Any,

    ) -> tuple[str, dict]:

        """

        Resolves the correct ModelConfig for the declared tier and

        passes it to the call function. Returns (response_text, usage).

        call_fn signature: (messages, model_config) -> (str, dict)

        The dict must contain prompt_tokens, completion_tokens, total_tokens

        so the circuit breaker in Protocol 4.2 can account for them.

        """

        config = self.config_for(tier)

        return call_fn(messages, config)

# ---------------------------------------------------------------------------

# Tier declaration on FSM states

# ---------------------------------------------------------------------------

class WorkflowState:

    """Base class from Protocol 2.1 — shown here with tier added."""

    name:      str = "undefined"

    task_tier: TaskTier = TaskTier.STANDARD   # explicit default, not implicit

class ValidatingOrderState(WorkflowState):

    """

    Checks that an order payload has the required fields and that

    the numeric values are within accepted ranges.

    The task is fully deterministic in its success criteria.

    A lightweight model handles this without any meaningful quality loss.

    """

    name      = "validating_order"

    task_tier = TaskTier.LIGHTWEIGHT

class ContractClauseAnalysisState(WorkflowState):

    """

    Reads a legal clause and identifies ambiguities, potential risks,

    and conflicts with the organization's standard agreement template.

    The output requires nuanced reasoning across potentially conflicting

    interpretations. Frontier tier is justified here.

    """

    name      = "contract_clause_analysis"

    task_tier = TaskTier.FRONTIER

class DraftRefundReplyState(WorkflowState):

    """

    Drafts a customer-facing explanation of a refund decision,

    referencing the customer's account history and the policy reason.

    Requires contextual awareness and coherent prose, but the

    output criteria are well-defined.

    """

    name      = "draft_refund_reply"

    task_tier = TaskTier.STANDARD

# ---------------------------------------------------------------------------

# Confidence-based escalation (optional safety valve)

# ---------------------------------------------------------------------------

@dataclass

class RoutedResponse:

    text:          str

    usage:         dict

    tier_used:     TaskTier

    was_escalated: bool = False

class EscalatingModelRouter(ModelRouter):

    """

    Extension of ModelRouter that supports a single escalation step.

    If a Lightweight-tier call returns a confidence score below the

    defined threshold, the same call is retried at the Standard tier.

    The escalation logic lives entirely in code. The model does not

    decide when to escalate. Your confidence threshold does.

    This mechanism is a safety valve for states that are declared

    LIGHTWEIGHT but occasionally receive edge-case inputs where the

    smaller model's output confidence is measurably lower.

    """

    def __init__(

        self,

        *args,

        escalation_confidence_floor: float = 0.72,

        **kwargs,

    ) -> None:

        super().__init__(*args, **kwargs)

        self._floor = escalation_confidence_floor

    def call_with_escalation(

        self,

        tier:           TaskTier,

        messages:       list[dict[str, str]],

        call_fn:        Any,

        confidence_fn:  Any,   # (response_text) -> float

    ) -> RoutedResponse:

        """

        Attempts the declared tier first. Escalates one tier up if the

        confidence score on the response falls below the floor.

        Never escalates more than once: if the escalated call also

        returns low confidence, that is a signal about the input or

        the prompt, not a reason to keep spending.

        """

        text, usage = self.call(tier, messages, call_fn)

        confidence  = confidence_fn(text)

        if confidence >= self._floor or tier == TaskTier.FRONTIER:

            return RoutedResponse(

                text=text, usage=usage, tier_used=tier

            )

        # One escalation step only.

        escalated_tier = (

            TaskTier.STANDARD

            if tier == TaskTier.LIGHTWEIGHT

            else TaskTier.FRONTIER

        )

        escalated_text, escalated_usage = self.call(

            escalated_tier, messages, call_fn

        )

        return RoutedResponse(

            text=escalated_text,

            usage=escalated_usage,

            tier_used=escalated_tier,

            was_escalated=True,

        )

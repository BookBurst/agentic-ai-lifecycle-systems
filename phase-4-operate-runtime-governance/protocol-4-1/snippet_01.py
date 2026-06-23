from __future__ import annotations

import json

import logging

import re

from enum import Enum

from typing import Callable

from pydantic import BaseModel, Field, ValidationError, field_validator

logger = logging.getLogger(__name__)

MAX_FORMAT_RETRIES = 2

# --- Schema Definition ---

class TargetAgent(str, Enum):

    PAYMENT_AGENT        = "payment_agent"

    CANCELLATION_AGENT   = "cancellation_agent"

    NOTIFICATION_AGENT   = "notification_agent"

    HUMAN_REVIEW_QUEUE   = "human_review_queue"

class RouteDecision(BaseModel):

    action: str = Field(

        ...,

        description="The specific action this routing decision selects.",

    )

    target_agent: TargetAgent

    confidence: float = Field(..., ge=0.0, le=1.0)

    requires_human_approval: bool

    rationale: str = Field(..., min_length=10, max_length=512)

    @field_validator("confidence")

    @classmethod

    def confidence_must_meet_threshold(cls, v: float) -> float:

        """

        A routing decision below 0.70 confidence is not a routing decision.

        It is an admission that the model is not sure what to do.

        Force it to human review rather than letting it proceed autonomously.

        """

        if v < 0.70:

            raise ValueError(

                f"Confidence {v:.2f} is below the minimum operational threshold (0.70). "

                "Set target_agent to 'human_review_queue' and requires_human_approval to true."

            )

        return v

# --- Parsing Utilities ---

class OutputParseError(Exception):

    """

    Raised when an LLM response cannot be coerced into a valid schema

    after the maximum number of corrective retries.

    """

def strip_llm_wrapping(raw: str) -> str:

    """

    Remove markdown fences and any preamble text preceding the JSON object.

    LLMs commonly wrap output in ```json ... ``` or prepend a sentence

    like "Here is the routing decision:" before the actual JSON block.

    """

    raw = raw.strip()

    # Case 1: fenced code block

    fenced = re.search(r"```(?:json)?\s(\{.?\})\s```", raw, re.DOTALL)

    if fenced:

        return fenced.group(1)

    # Case 2: bare JSON object somewhere in the string

    bare = re.search(r"\{.\}", raw, re.DOTALL)

    if bare:

        return bare.group(0)

    return raw

def parse_route_decision(raw: str, attempt: int) -> RouteDecision:

    """

    Extract JSON from the raw LLM response and validate it against RouteDecision.

    Raises OutputParseError with a structured message on failure so the caller

    can either retry with the error injected or halt the execution thread.

    """

    try:

        cleaned = strip_llm_wrapping(raw)

        data = json.loads(cleaned)

        return RouteDecision(**data)

    except (json.JSONDecodeError, ValidationError, KeyError) as exc:

        logger.warning(

            "schema_validation_failed",

            extra={

                "attempt": attempt,

                "raw_output_preview": raw[:300],

                "error": str(exc),

            },

        )

        raise OutputParseError(str(exc)) from exc

# --- Enforcement Entry Point ---

def get_route_decision(

    build_messages_fn: Callable[[str, dict], list[dict]],

    call_llm_fn: Callable[[list[dict]], str],

    user_input: str,

    context: dict,

) -> RouteDecision:

    """

    Call the routing LLM and enforce schema compliance on the response.

    On a format failure, injects the exact Pydantic validation error back

    into the conversation and retries once. On persistent failure, raises

    OutputParseError so the caller's halt logic can take over. No invalid

    data is ever returned from this function.

    """

    messages = build_messages_fn(user_input, context)

    for attempt in range(MAX_FORMAT_RETRIES + 1):

        raw = call_llm_fn(messages)

        try:

            return parse_route_decision(raw, attempt)

        except OutputParseError as exc:

            if attempt < MAX_FORMAT_RETRIES:

                # Corrective retry: give the model its own error message

                # so it can self-correct the format, not the reasoning.

                messages.append({"role": "assistant", "content": raw})

                messages.append({

                    "role": "user",

                    "content": (

                        f"Your previous response failed schema validation: {exc}\n\n"

                        "Return only a valid JSON object matching the required schema. "

                        "No markdown fences. No explanatory text before or after the JSON."

                    ),

                })

            else:

                raise OutputParseError(

                    f"LLM failed to produce a valid RouteDecision after "

                    f"{MAX_FORMAT_RETRIES + 1} attempts. Last error: {exc}"

                ) from exc

    raise OutputParseError("Unexpected exit from retry loop.")

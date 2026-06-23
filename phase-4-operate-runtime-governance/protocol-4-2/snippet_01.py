from __future__ import annotations

import logging

from typing import Any

from opentelemetry import trace

from opentelemetry.sdk.trace import TracerProvider

from opentelemetry.sdk.trace.export import BatchSpanProcessor

from opentelemetry.trace import StatusCode

from openinference.semconv.trace import (

    OpenInferenceSpanKindValues,

    SpanAttributes,

)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------

# Tracer setup: called once at application startup.

# Pass any OTLP-compatible exporter (Phoenix, LangSmith, Jaeger, a vendor

# endpoint). The instrumentation wrappers below do not change with the backend.

# ---------------------------------------------------------------------------

def configure_tracing(exporter) -> None:

    provider = TracerProvider()

    provider.add_span_processor(BatchSpanProcessor(exporter))

    trace.set_tracer_provider(provider)

tracer = trace.get_tracer("adlc.orchestrator", version="1.0.0")

# ---------------------------------------------------------------------------

# Instrumented LLM call wrapper.

# Expects call_llm_fn to return (response_text: str, usage: dict), where

# usage contains prompt_tokens, completion_tokens, and total_tokens.

# ---------------------------------------------------------------------------

def traced_llm_call(

    *,

    call_llm_fn,

    messages: list[dict],

    model: str,

    thread_id: str,

    operation_name: str,

) -> str:

    """

    Execute an LLM call inside an OpenInference LLM span.

    The span automatically becomes a child of whatever span is active

    in the calling context, building the execution tree without manual

    ID management. Token counts recorded here feed the circuit breaker

    in the next section.

    """

    with tracer.start_as_current_span(operation_name) as span:

        span.set_attribute(

            SpanAttributes.OPENINFERENCE_SPAN_KIND,

            OpenInferenceSpanKindValues.LLM.value,

        )

        span.set_attribute(SpanAttributes.LLM_MODEL_NAME, model)

        span.set_attribute("session.id", thread_id)

        # Full prompt: every message role and content, in order.

        for i, msg in enumerate(messages):

            span.set_attribute(

                f"{SpanAttributes.LLM_INPUT_MESSAGES}.{i}.message.role",

                msg["role"],

            )

            span.set_attribute(

                f"{SpanAttributes.LLM_INPUT_MESSAGES}.{i}.message.content",

                msg["content"],

            )

        try:

            response_text, usage = call_llm_fn(messages)

            span.set_attribute(

                SpanAttributes.LLM_TOKEN_COUNT_PROMPT,

                usage["prompt_tokens"],

            )

            span.set_attribute(

                SpanAttributes.LLM_TOKEN_COUNT_COMPLETION,

                usage["completion_tokens"],

            )

            span.set_attribute(

                SpanAttributes.LLM_TOKEN_COUNT_TOTAL,

                usage["total_tokens"],

            )

            span.set_attribute(SpanAttributes.OUTPUT_VALUE, response_text)

            span.set_status(StatusCode.OK)

            return response_text

        except Exception as exc:

            span.record_exception(exc)

            span.set_status(StatusCode.ERROR, str(exc))

            raise

# ---------------------------------------------------------------------------

# Instrumented tool call wrapper.

# Every external tool the agent invokes should go through here so it

# appears as a TOOL-kind child span in the execution tree.

# ---------------------------------------------------------------------------

def traced_tool_call(

    *,

    tool_fn,

    tool_name: str,

    tool_input: dict[str, Any],

    thread_id: str,

) -> Any:

    """

    Execute a tool call inside an OpenInference TOOL span.

    """

    with tracer.start_as_current_span(f"tool.{tool_name}") as span:

        span.set_attribute(

            SpanAttributes.OPENINFERENCE_SPAN_KIND,

            OpenInferenceSpanKindValues.TOOL.value,

        )

        span.set_attribute(SpanAttributes.TOOL_NAME, tool_name)

        span.set_attribute(SpanAttributes.INPUT_VALUE, str(tool_input))

        span.set_attribute("session.id", thread_id)

        try:

            result = tool_fn(**tool_input)

            span.set_attribute(SpanAttributes.OUTPUT_VALUE, str(result))

            span.set_status(StatusCode.OK)

            return result

        except Exception as exc:

            span.record_exception(exc)

            span.set_status(StatusCode.ERROR, str(exc))

            raise

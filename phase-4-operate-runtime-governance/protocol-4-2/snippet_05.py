def traced_llm_call(

    *,

    call_llm_fn,

    messages:       list[dict],

    model:          str,

    thread_id:      str,

    operation_name: str,

    # Attribution context -- passed from the FSM state at call time.

    agent_id:       str,

    tenant_id:      str,

    workflow_type:  str,

    model_tier:     str,

    fsm_state_name: str,

    attribution_ledger,       # Any object with a write(record: dict) method.

    cache_hit:      bool = False,

) -> str:

    with tracer.start_as_current_span(operation_name) as span:

        # ... existing span attribute setup unchanged ...

        try:

            response_text, usage = call_llm_fn(messages)

            # Existing span attribute writes unchanged.

            span.set_attribute(SpanAttributes.LLM_TOKEN_COUNT_TOTAL,

                               usage["total_tokens"])

            span.set_status(StatusCode.OK)

            # Attribution write: one row, synchronous, before returning.

            attribution_ledger.write({

                "thread_id":         thread_id,

                "span_id":           span.get_span_context().span_id,

                "agent_id":          agent_id,

                "tenant_id":         tenant_id,

                "workflow_type":     workflow_type,

                "model_tier":        model_tier,

                "model_id":          model,

                "prompt_tokens":     usage["prompt_tokens"],

                "completion_tokens": usage["completion_tokens"],

                "total_tokens":      usage["total_tokens"],

                "cache_hit":         cache_hit,

                "fsm_state_name":    fsm_state_name,

            })

            return response_text

        except Exception as exc:

            span.record_exception(exc)

            span.set_status(StatusCode.ERROR, str(exc))

            raise

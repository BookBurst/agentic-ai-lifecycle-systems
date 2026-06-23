CREATE TABLE token_attribution (

    id              BIGSERIAL PRIMARY KEY,

    recorded_at     TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- Thread and call identity

    thread_id       TEXT        NOT NULL,

    span_id         TEXT        NOT NULL,   -- Links back to the OpenInference trace.

    -- Attribution dimensions

    agent_id        TEXT        NOT NULL,

    tenant_id       TEXT        NOT NULL,

    workflow_type   TEXT        NOT NULL,

    model_tier      TEXT        NOT NULL,   -- lightweight / standard / frontier

    model_id        TEXT        NOT NULL,   -- Exact model string from the provider.

    -- Token consumption

    prompt_tokens      INTEGER NOT NULL,

    completion_tokens  INTEGER NOT NULL,

    total_tokens       INTEGER NOT NULL,

    cache_hit          BOOLEAN NOT NULL DEFAULT FALSE,

    -- Outcome link

    fsm_state_name  TEXT        NOT NULL    -- Which FSM state triggered this call.

);

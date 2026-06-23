CREATE TABLE agent_intent_log (

    thread_id        TEXT NOT NULL,

    action_name       TEXT NOT NULL,

    sequence          INTEGER NOT NULL,

    agent_id          TEXT NOT NULL,

    model_version     TEXT NOT NULL,

    reasoning_summary TEXT,

    tool_name         TEXT NOT NULL,

    tool_parameters   JSONB NOT NULL,

    status            TEXT NOT NULL DEFAULT 'pending',

    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),

    resolved_at       TIMESTAMPTZ,

    PRIMARY KEY (thread_id, action_name, sequence)

);

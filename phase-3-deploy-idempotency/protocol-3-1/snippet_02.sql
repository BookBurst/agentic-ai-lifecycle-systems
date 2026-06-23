CREATE TABLE completed_actions (

    thread_id       TEXT NOT NULL,

    action_name     TEXT NOT NULL,

    sequence        INTEGER NOT NULL,

    result_payload  JSONB,

    completed_at    TIMESTAMPTZ NOT NULL DEFAULT now(),

    PRIMARY KEY (thread_id, action_name, sequence)

);

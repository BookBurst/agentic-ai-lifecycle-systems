CREATE TABLE workflow_checkpoints (

    thread_id TEXT PRIMARY KEY,

    current_state TEXT NOT NULL,

    context_data JSONB NOT NULL,

    history JSONB NOT NULL,

    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()

);

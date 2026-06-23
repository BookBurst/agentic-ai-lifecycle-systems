CREATE INDEX idx_ta_tenant_date   ON token_attribution (tenant_id, recorded_at);

CREATE INDEX idx_ta_workflow_date ON token_attribution (workflow_type, recorded_at);

CREATE INDEX idx_ta_agent_date    ON token_attribution (agent_id, recorded_at);

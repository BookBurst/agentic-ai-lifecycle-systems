    tenant_id,

    SUM(total_tokens)                      AS month_to_date_tokens,

    t.monthly_token_budget,

    ROUND(

        100.0 * SUM(total_tokens) / t.monthly_token_budget, 1

    )                                      AS budget_pct_used

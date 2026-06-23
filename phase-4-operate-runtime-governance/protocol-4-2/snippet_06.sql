    tenant_id,

    SUM(total_tokens)        AS total_tokens,

    SUM(prompt_tokens)       AS prompt_tokens,

    SUM(completion_tokens)   AS completion_tokens,

    COUNT(*)                 AS call_count,

    SUM(CASE WHEN cache_hit THEN 1 ELSE 0 END) AS cache_hits

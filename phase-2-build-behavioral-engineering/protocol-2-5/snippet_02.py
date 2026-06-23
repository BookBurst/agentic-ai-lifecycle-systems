from __future__ import annotations

import time

from dataclasses import dataclass, field

from typing import Any, Callable, Protocol

import numpy as np

# ---------------------------------------------------------------------------

# Storage backend protocol -- swappable between in-memory and Redis Stack

# ---------------------------------------------------------------------------

class CacheBackend(Protocol):

    def get_all_for_scope(self, scope_key: str) -> list["SemanticCacheEntry"]:

        ...

    def store(self, entry: "SemanticCacheEntry") -> None:

        ...

    def delete_scope(self, scope_key: str) -> None:

        ...

@dataclass

class SemanticCacheEntry:

    scope_key:   str

    query:       str

    embedding:   list[float]

    response:    str

    created_at:  float = field(default_factory=time.monotonic)

    ttl_seconds: int   = 3_600

# ---------------------------------------------------------------------------

# In-memory backend (suitable for single-process deployments or testing)

# ---------------------------------------------------------------------------

class InMemoryCacheBackend:

    def __init__(self) -> None:

        self._store: dict[str, list[SemanticCacheEntry]] = {}

    def get_all_for_scope(self, scope_key: str) -> list[SemanticCacheEntry]:

        return self._store.get(scope_key, [])

    def store(self, entry: SemanticCacheEntry) -> None:

        self._store.setdefault(entry.scope_key, []).append(entry)

    def delete_scope(self, scope_key: str) -> None:

        self._store.pop(scope_key, None)

# ---------------------------------------------------------------------------

# The semantic cache

# ---------------------------------------------------------------------------

class SemanticCache:

    """

    Intercepts LLM calls for semantically equivalent queries and returns

    cached responses without touching the API.

    Cache entries are scoped by FSM state name and task tier. An entry

    stored for ValidatingOrderState::lightweight is never served to

    DraftRefundReplyState::standard, even if the query embeddings match.

    Use the same embedding_fn you already have in your retrieval pipeline.

    No additional embedding infrastructure is needed.

    """

    def __init__(

        self,

        backend:              CacheBackend,

        embedding_fn:         Callable[[str], list[float]],

        similarity_threshold: float = 0.94,

        ttl_seconds:          int   = 3_600,

    ) -> None:

        self._backend   = backend

        self._embed     = embedding_fn

        self._threshold = similarity_threshold

        self._ttl       = ttl_seconds

    def _scope_key(self, state_name: str, tier: "TaskTier") -> str:

        # Scope is always state + tier together.

        # Never use state name alone: the same query in a LIGHTWEIGHT

        # classification state means something different than the same

        # query string passed to a FRONTIER reasoning state.

        return f"{state_name}::{tier.value}"

    @staticmethod

    def _cosine_similarity(a: list[float], b: list[float]) -> float:

        vec_a = np.array(a, dtype=float)

        vec_b = np.array(b, dtype=float)

        norm_a = np.linalg.norm(vec_a)

        norm_b = np.linalg.norm(vec_b)

        if norm_a == 0.0 or norm_b == 0.0:

            return 0.0

        return float(np.dot(vec_a, vec_b) / (norm_a * norm_b))

    def lookup(

        self,

        query:      str,

        state_name: str,

        tier:       "TaskTier",

    ) -> str | None:

        """

        Returns a cached response if a semantically equivalent query

        exists in this state/tier scope and has not expired.

        Returns None otherwise -- the caller proceeds to the API.

        """

        scope           = self._scope_key(state_name, tier)

        query_embedding = self._embed(query)

        now             = time.monotonic()

        best_score = 0.0

        best_entry: SemanticCacheEntry | None = None

        for entry in self._backend.get_all_for_scope(scope):

            if now - entry.created_at > entry.ttl_seconds:

                continue

            score = self._cosine_similarity(query_embedding, entry.embedding)

            if score > best_score:

                best_score = score

                best_entry = entry

        if best_entry is not None and best_score >= self._threshold:

            return best_entry.response

        return None

    def store(

        self,

        query:      str,

        state_name: str,

        tier:       "TaskTier",

        response:   str,

    ) -> None:

        """

        Caches a response after a successful API call.

        Called by CachedModelRouter; FSM states never call this directly.

        """

        self._backend.store(

            SemanticCacheEntry(

                scope_key=self._scope_key(state_name, tier),

                query=query,

                embedding=self._embed(query),

                response=response,

                ttl_seconds=self._ttl,

            )

        )

    def invalidate_scope(self, state_name: str, tier: "TaskTier") -> None:

        """

        Clears all cached entries for this state and tier.

        CRITICAL: Call this whenever you advance the pinned prompt version

        for a state (Protocol 2.2). Cached responses were generated by the

        previous prompt wording. Serving them after a prompt update means

        your new wording never reaches users with semantically familiar

        queries -- the exact users the update was meant to reach.

        """

        self._backend.delete_scope(self._scope_key(state_name, tier))

# ---------------------------------------------------------------------------

# Cache-aware router: wraps ModelRouter with a lookup/store layer

# ---------------------------------------------------------------------------

@dataclass

class RoutedResponse:

    text:          str

    usage:         dict[str, int]

    tier_used:     "TaskTier"

    cache_hit:     bool = False

class CachedModelRouter:

    """

    Composes ModelRouter with SemanticCache.

    Cache lookup runs before any API call.

    Cache storage runs after every successful response.

    The model never knows the cache exists.

    cacheable_tiers controls which tiers participate in caching.

    LIGHTWEIGHT is included by default.

    FRONTIER requires explicit opt-in because Frontier calls tend

    to be context-specific: cache hit rates are lower and the cost

    of a false positive is higher.

    """

    def __init__(

        self,

        router:          "ModelRouter",

        cache:           SemanticCache,

        cacheable_tiers: frozenset["TaskTier"] | None = None,

    ) -> None:

        self._router         = router

        self._cache          = cache

        self._cacheable      = (

            cacheable_tiers

            or frozenset(["lightweight"])   # TaskTier.LIGHTWEIGHT

        )

    def call(

        self,

        state_name: str,

        tier:       "TaskTier",

        query:      str,

        messages:   list[dict[str, str]],

        call_fn:    Any,

    ) -> RoutedResponse:

        """

        Attempts cache lookup, falls back to API call on miss.

        Returns RoutedResponse with cache_hit flag for telemetry.

        On a cache hit, usage is an empty dict -- no tokens consumed.

        """

        if tier.value in self._cacheable:

            cached = self._cache.lookup(query, state_name, tier)

            if cached is not None:

                return RoutedResponse(

                    text=cached,

                    usage={},

                    tier_used=tier,

                    cache_hit=True,

                )

        text, usage = self._router.call(tier, messages, call_fn)

        if tier.value in self._cacheable:

            self._cache.store(query, state_name, tier, text)

        return RoutedResponse(

            text=text,

            usage=usage,

            tier_used=tier,

            cache_hit=False,

        )

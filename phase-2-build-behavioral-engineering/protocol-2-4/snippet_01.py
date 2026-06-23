from __future__ import annotations

from dataclasses import dataclass

from typing import Callable

# ---------------------------------------------------------------------------

# Shared data type

# ---------------------------------------------------------------------------

@dataclass(frozen=True)

class RetrievedChunk:

    chunk_id: str

    content:  str

    score:    float

@dataclass

class RetrievalConfig:

    """

    Controls the two-stage pipeline behavior.

    recall_k  -- candidates to surface in the first pass (coverage budget).

    final_k   -- chunks returned after re-ranking (context window budget).

    rrf_k     -- RRF constant; 60 is the standard default, rarely needs tuning.

    """

    recall_k: int = 30

    final_k:  int = 6

    rrf_k:    int = 60

# ---------------------------------------------------------------------------

# Stage 1: Hybrid Retrieval with Reciprocal Rank Fusion

# ---------------------------------------------------------------------------

class HybridRetriever:

    """

    Merges BM25 sparse retrieval and dense vector retrieval using RRF.

    Neither index is privileged: the merge is purely rank-position-based.

    Both retrieval callables are injected so this class stays fully

    testable without touching any real vector store or BM25 index.

    """

    def __init__(

        self,

        dense_fn: Callable[[str, int], list[RetrievedChunk]],

        bm25_fn:  Callable[[str, int], list[RetrievedChunk]],

        config:   RetrievalConfig,

    ) -> None:

        self._dense  = dense_fn

        self._bm25   = bm25_fn

        self._config = config

    def retrieve(self, query: str) -> list[RetrievedChunk]:

        k     = self._config.recall_k

        rrf_k = self._config.rrf_k

        dense_results = self._dense(query, k)

        bm25_results  = self._bm25(query, k)

        # Build rank-position lookup for each result list.

        dense_ranks: dict[str, int] = {

            c.chunk_id: rank

            for rank, c in enumerate(dense_results, start=1)

        }

        bm25_ranks: dict[str, int] = {

            c.chunk_id: rank

            for rank, c in enumerate(bm25_results, start=1)

        }

        # Collect all unique chunk IDs from both lists.

        all_ids: set[str] = set(dense_ranks) | set(bm25_ranks)

        # Content lookup: grab text from whichever list has the chunk.

        content_map: dict[str, str] = {

            c.chunk_id: c.content

            for c in dense_results + bm25_results

        }

        # RRF score = sum of 1 / (rrf_k + rank) across both lists.

        # A chunk that tops both lists scores much higher than one that

        # tops only one; a chunk absent from a list contributes 0 from it.

        fused: list[tuple[str, float]] = []

        for chunk_id in all_ids:

            score = 0.0

            if chunk_id in dense_ranks:

                score += 1.0 / (rrf_k + dense_ranks[chunk_id])

            if chunk_id in bm25_ranks:

                score += 1.0 / (rrf_k + bm25_ranks[chunk_id])

            fused.append((chunk_id, score))

        fused.sort(key=lambda x: x[1], reverse=True)

        return [

            RetrievedChunk(

                chunk_id=cid,

                content=content_map[cid],

                score=score,

            )

            for cid, score in fused[:k]

        ]

# ---------------------------------------------------------------------------

# Stage 2: Cross-Encoder Re-Ranking

# ---------------------------------------------------------------------------

class CrossEncoderReranker:

    """

    Re-scores each candidate by evaluating the query and the chunk content

    together as a single input. The cross-encoder sees both at once, which

    is why it catches relevance signals the bi-encoder's independent

    encoding misses.

    score_fn accepts a list of (query, document) pairs and returns a list

    of float scores in the same order. Wire it to sentence-transformers

    CrossEncoder, the Cohere rerank endpoint, or any hosted cross-encoder.

    The pipeline doesn't care which one -- that decision belongs to

    whoever wires up the dependency.

    """

    def __init__(

        self,

        score_fn: Callable[[list[tuple[str, str]]], list[float]],

        config:   RetrievalConfig,

    ) -> None:

        self._score_fn = score_fn

        self._config   = config

    def rerank(

        self,

        query:      str,

        candidates: list[RetrievedChunk],

    ) -> list[RetrievedChunk]:

        if not candidates:

            return []

        pairs  = [(query, chunk.content) for chunk in candidates]

        scores = self._score_fn(pairs)

        rescored = [

            RetrievedChunk(

                chunk_id=chunk.chunk_id,

                content=chunk.content,

                score=float(s),

            )

            for chunk, s in zip(candidates, scores)

        ]

        rescored.sort(key=lambda c: c.score, reverse=True)

        return rescored[: self._config.final_k]

# ---------------------------------------------------------------------------

# The composed pipeline

# ---------------------------------------------------------------------------

class RetrievalPipeline:

    """

    Composes hybrid retrieval and cross-encoder re-ranking into a single

    callable. FSM states call get_context() and receive a ranked list of

    chunks ready to be assembled into the model's context window.

    They never reach into the BM25 index, the vector store, or the

    re-ranker directly.

    """

    def __init__(

        self,

        retriever: HybridRetriever,

        reranker:  CrossEncoderReranker,

    ) -> None:

        self._retriever = retriever

        self._reranker  = reranker

    def get_context(self, query: str) -> list[RetrievedChunk]:

        candidates = self._retriever.retrieve(query)

        return self._reranker.rerank(query, candidates)

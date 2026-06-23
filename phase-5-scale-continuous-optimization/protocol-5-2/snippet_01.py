from __future__ import annotations

from dataclasses import dataclass, field

from typing import Callable

@dataclass

class RAGEvalCase:

    case_id: str

    query: str

    # The chunk IDs that a correct retrieval must surface in the top-k results.

    # Built from manually verified real-traffic queries, not synthetic examples.

    expected_chunk_ids: list[str]

    k: int = 5

@dataclass(frozen=True)

class RAGEvalResult:

    case_id: str

    retrieved_ids: list[str]

    hit: bool               # at least one expected chunk found in top-k

    reciprocal_rank: float  # 1/rank of the first expected chunk; 0.0 if absent

    precision_at_k: float   # fraction of top-k results that are expected chunks

@dataclass

class RAGEvalReport:

    results: list[RAGEvalResult]

    @property

    def hit_rate(self) -> float:

        """Fraction of queries where at least one expected chunk appeared."""

        return sum(1 for r in self.results if r.hit) / len(self.results)

    @property

    def mean_reciprocal_rank(self) -> float:

        """Average rank quality of the first expected chunk across all queries."""

        return sum(r.reciprocal_rank for r in self.results) / len(self.results)

    @property

    def mean_precision_at_k(self) -> float:

        """Average fraction of retrieved chunks that were actually relevant."""

        return sum(r.precision_at_k for r in self.results) / len(self.results)

    def summary(self) -> dict:

        return {

            "total_cases": len(self.results),

            "hit_rate": round(self.hit_rate, 4),

            "mean_reciprocal_rank": round(self.mean_reciprocal_rank, 4),

            "mean_precision_at_k": round(self.mean_precision_at_k, 4),

        }

class RAGEvaluator:

    """

    Evaluates the retrieval pipeline in complete isolation from the language model.

    The retrieval callable is invoked directly on each query; no LLM call is made

    at any point during this evaluation. This is intentional: the goal is to measure

    whether the search layer finds the right content before the model ever sees it.

    To test the model's reasoning in isolation, use the mock context pattern:

    feed the model a manually curated perfect context and verify it can produce

    a correct response when retrieval is not the variable.

    """

    def __init__(

        self,

        retrieval_fn: Callable[[str, int], list[str]],

        cases: list[RAGEvalCase],

    ) -> None:

        # retrieval_fn signature: (query: str, k: int) -> list[chunk_id: str]

        # Wire this directly to your vector store search call, nothing else.

        self.retrieval_fn = retrieval_fn

        self.cases = cases

    def run(self) -> RAGEvalReport:

        return RAGEvalReport(

            results=[self._eval_case(c) for c in self.cases]

        )

    def _eval_case(self, case: RAGEvalCase) -> RAGEvalResult:

        retrieved = self.retrieval_fn(case.query, case.k)

        expected = set(case.expected_chunk_ids)

        hit = any(cid in expected for cid in retrieved)

        # Reciprocal rank: score the position of the first correct result

        rr = 0.0

        for rank, cid in enumerate(retrieved, start=1):

            if cid in expected:

                rr = 1.0 / rank

                break

        # Precision@k: what fraction of what we retrieved was actually useful

        precision = (

            sum(1 for cid in retrieved if cid in expected) / len(retrieved)

            if retrieved else 0.0

        )

        return RAGEvalResult(

            case_id=case.case_id,

            retrieved_ids=retrieved,

            hit=hit,

            reciprocal_rank=rr,

            precision_at_k=precision,

        )

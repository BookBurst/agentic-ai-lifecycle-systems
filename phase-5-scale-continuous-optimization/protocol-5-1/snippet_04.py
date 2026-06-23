from __future__ import annotations

from dataclasses import dataclass, field

from enum import Enum

from typing import Callable

class DivergenceType(str, Enum):

    NONE               = "none"               # Semantically equivalent outputs.

    TEXT_DIVERGENCE    = "text_divergence"    # Text differs beyond similarity threshold.

    TOOL_SELECTION     = "tool_selection"     # Different tools were chosen.

    TOOL_PARAMETERS    = "tool_parameters"    # Same tools, different parameters.

    CANDIDATE_ERROR    = "candidate_error"    # Shadow execution failed entirely.

@dataclass(frozen=True)

class BehavioralDiff:

    request_id:      str

    fsm_state:       str

    divergence_type: DivergenceType

    text_similarity: float          # Cosine similarity of output embeddings. 0.0–1.0.

    tool_diff:       str            # Human-readable description of tool divergence.

    candidate_error: str | None

@dataclass

class DivergenceReport:

    total_pairs:          int

    by_state:             dict[str, list[BehavioralDiff]] = field(default_factory=dict)

    @property

    def overall_divergence_rate(self) -> float:

        divergent = sum(

            1 for diffs in self.by_state.values()

            for d in diffs

            if d.divergence_type != DivergenceType.NONE

        )

        return divergent / max(self.total_pairs, 1)

    def divergence_rate_for_state(self, state_name: str) -> float:

        diffs = self.by_state.get(state_name, [])

        if not diffs:

            return 0.0

        divergent = sum(1 for d in diffs if d.divergence_type != DivergenceType.NONE)

        return divergent / len(diffs)

    def unexpected_divergence_rate(self, intended_states: set[str]) -> float:

        """

        Divergence rate across states that were NOT intended to change.

        A high unexpected divergence rate means the candidate changed

        behavior beyond the scope of the intended modification.

        """

        out_of_scope = [

            d for state, diffs in self.by_state.items()

            if state not in intended_states

            for d in diffs

        ]

        if not out_of_scope:

            return 0.0

        divergent = sum(1 for d in out_of_scope if d.divergence_type != DivergenceType.NONE)

        return divergent / len(out_of_scope)

class DivergenceAnalyzer:

    """

    Compares production and shadow responses for a set of request pairs.

    Produces a DivergenceReport grouped by FSM state.

    embed_fn: callable that takes a string and returns a list[float] embedding.

    Use the same embedding model as your retrieval pipeline.

    text_similarity_floor: pairs below this threshold are TEXT_DIVERGENCE.

    """

    def __init__(

        self,

        embed_fn:               Callable[[str], list[float]],

        text_similarity_floor:  float = 0.92,

    ) -> None:

        self._embed   = embed_fn

        self._floor   = text_similarity_floor

    def analyze(

        self,

        pairs: list[dict],      # Each dict: production_response, shadow_response, fsm_state

    ) -> DivergenceReport:

        report = DivergenceReport(total_pairs=len(pairs))

        for pair in pairs:

            diff = self._compare_pair(pair)

            state = diff.fsm_state

            report.by_state.setdefault(state, []).append(diff)

        return report

    def _compare_pair(self, pair: dict) -> BehavioralDiff:

        prod   = pair["production_response"]

        shadow = pair["shadow_response"]

        state  = pair.get("fsm_state", "unknown")

        if shadow.get("error"):

            return BehavioralDiff(

                request_id=shadow["request_id"],

                fsm_state=state,

                divergence_type=DivergenceType.CANDIDATE_ERROR,

                text_similarity=0.0,

                tool_diff="",

                candidate_error=shadow["error"],

            )

        prod_tools   = {c["tool_name"] for c in prod.get("tool_calls", [])}

        shadow_tools = {c["tool_name"] for c in shadow.get("intercepted_calls", [])}

        if prod_tools != shadow_tools:

            return BehavioralDiff(

                request_id=shadow["request_id"],

                fsm_state=state,

                divergence_type=DivergenceType.TOOL_SELECTION,

                text_similarity=0.0,

                tool_diff=(

                    f"Production called {sorted(prod_tools)}; "

                    f"candidate called {sorted(shadow_tools)}."

                ),

                candidate_error=None,

            )

        similarity = self._text_similarity(

            prod.get("text", ""), shadow.get("generated_text", "")

        )

        divergence = (

            DivergenceType.TEXT_DIVERGENCE

            if similarity < self._floor

            else DivergenceType.NONE

        )

        return BehavioralDiff(

            request_id=shadow["request_id"],

            fsm_state=state,

            divergence_type=divergence,

            text_similarity=round(similarity, 3),

            tool_diff="",

            candidate_error=None,

        )

    def _text_similarity(self, a: str, b: str) -> float:

        import numpy as np

        va, vb = np.array(self._embed(a)), np.array(self._embed(b))

        na, nb = np.linalg.norm(va), np.linalg.norm(vb)

        if na == 0.0 or nb == 0.0:

            return 0.0

        return float(np.dot(va, vb) / (na * nb))

from __future__ import annotations

import json

from dataclasses import dataclass, field

from enum import Enum

from typing import Callable

# ---------------------------------------------------------------------------

# Segment classification

# ---------------------------------------------------------------------------

class SegmentType(str, Enum):

    SYSTEM_PROMPT  = "system_prompt"

    TASK_OBJECTIVE = "task_objective"

    CONFIRMED_FACT = "confirmed_fact"

    TOOL_RESULT    = "tool_result"

    REASONING      = "reasoning"

    FAILED_ATTEMPT = "failed_attempt"

    SUMMARY        = "summary"

class PreservationRule(str, Enum):

    ALWAYS_PRESERVE  = "always_preserve"

    COMPRESS_IF_OLD  = "compress_if_old"

    DISCARD_ELIGIBLE = "discard_eligible"

@dataclass

class ContextSegment:

    segment_type: SegmentType

    content:      str

    token_count:  int

    turn_index:   int

    validated:    bool = False   # True if this segment produced a confirmed

                                  # result that was written to the FSM checkpoint.

# ---------------------------------------------------------------------------

# Compression plan: produced before anything is discarded or summarized

# ---------------------------------------------------------------------------

@dataclass

class CompressionPlan:

    to_preserve:  list[ContextSegment]

    to_summarize: list[ContextSegment]

    to_discard:   list[ContextSegment]

    @property

    def projected_token_savings(self) -> int:

        """

        Rough estimate of how many tokens will be freed.

        Assumes summarization retains ~20% of source tokens on average.

        Use this to decide whether a compression cycle is worth triggering

        before the health monitor reaches CRITICAL.

        """

        discard_savings  = sum(s.token_count for s in self.to_discard)

        compress_savings = int(

            sum(s.token_count for s in self.to_summarize) * 0.80

        )

        return discard_savings + compress_savings

# ---------------------------------------------------------------------------

# Compression result

# ---------------------------------------------------------------------------

@dataclass

class CompressedContext:

    segments:              list[ContextSegment]

    original_token_count:  int

    compressed_token_count: int

    compression_ratio:     float

    triggered_by:          str   # ContextHealthStatus value for the telemetry log.

    compressed_at_state:   str   # FSM state name where compression was executed.

# ---------------------------------------------------------------------------

# The compressor

# ---------------------------------------------------------------------------

class ContextCompressor:

    """

    Applies preservation rules and produces a CompressedContext at an FSM

    state boundary. Runs after the current state's output has been validated

    and checkpointed, before the next state begins execution.

    summarize_fn receives a block of text and a target token budget and

    returns a compressed version. Wire it to a LIGHTWEIGHT or STANDARD tier

    call via Protocol 2.5's ModelRouter -- this is a well-defined task that

    does not require a frontier model.

    recent_turns_to_preserve controls how many of the most recent turns are

    kept verbatim regardless of their segment type. The default of 3 is a

    safe starting point; reduce it if your workflows are very token-heavy

    and increase it if recent context tends to be dense with cross-turn

    dependencies.

    """

    # Segment types that are never compressed, regardless of age.

    _ALWAYS_PRESERVE = frozenset({

        SegmentType.SYSTEM_PROMPT,

        SegmentType.TASK_OBJECTIVE,

        SegmentType.CONFIRMED_FACT,

        SegmentType.SUMMARY,        # Never re-compress an existing summary.

    })

    # Segment types that can be dropped without summarization.

    _DISCARD_ELIGIBLE = frozenset({

        SegmentType.FAILED_ATTEMPT,

    })

    def __init__(

        self,

        summarize_fn:              Callable[[str, int], str],

        recent_turns_to_preserve:  int = 3,

        summary_token_budget:      int = 400,

    ) -> None:

        self._summarize     = summarize_fn

        self._recent_turns  = recent_turns_to_preserve

        self._summary_budget = summary_token_budget

    def plan(self, segments: list[ContextSegment]) -> CompressionPlan:

        """

        Classifies every segment without modifying anything.

        Inspect the plan before calling compress() if you want to

        log or audit what will be kept and what will be lost.

        """

        if not segments:

            return CompressionPlan([], [], [])

        max_turn = max(s.turn_index for s in segments)

        recency_floor = max_turn - self._recent_turns

        to_preserve:  list[ContextSegment] = []

        to_summarize: list[ContextSegment] = []

        to_discard:   list[ContextSegment] = []

        for segment in sorted(segments, key=lambda s: s.turn_index):

            if segment.segment_type in self._ALWAYS_PRESERVE:

                to_preserve.append(segment)

                continue

            if segment.segment_type in self._DISCARD_ELIGIBLE:

                to_discard.append(segment)

                continue

            # Recent segments stay verbatim.

            if segment.turn_index > recency_floor:

                to_preserve.append(segment)

                continue

            # Validated tool results and reasoning from older turns

            # get compressed rather than discarded, because their

            # summary has residual value even after the result is

            # written to the FSM checkpoint.

            to_summarize.append(segment)

        return CompressionPlan(

            to_preserve=to_preserve,

            to_summarize=to_summarize,

            to_discard=to_discard,

        )

    def compress(

        self,

        segments:           list[ContextSegment],

        triggered_by:       str,

        state_name:         str,

    ) -> CompressedContext:

        """

        Executes the compression plan and returns a CompressedContext.

        This is the only method that calls summarize_fn and therefore

        the only method that incurs an LLM API cost. The plan() method

        is free and can be called as many times as needed for inspection.

        """

        original_tokens = sum(s.token_count for s in segments)

        plan = self.plan(segments)

        result: list[ContextSegment] = list(plan.to_preserve)

        if plan.to_summarize:

            # Batch all segments-to-summarize into one call, ordered

            # chronologically, so the summary reads coherently.

            ordered = sorted(plan.to_summarize, key=lambda s: s.turn_index)

            combined = "\n\n".join(

                f"[Turn {s.turn_index} | {s.segment_type.value}]\n{s.content}"

                for s in ordered

            )

            summary_text = self._summarize(combined, self._summary_budget)

            earliest_turn = ordered[0].turn_index

            result.append(ContextSegment(

                segment_type=SegmentType.SUMMARY,

                content=summary_text,

                token_count=len(summary_text.split()),   # rough approximation

                turn_index=earliest_turn,

                validated=False,

            ))

        # Preserve chronological ordering in the final context.

        result.sort(key=lambda s: s.turn_index)

        compressed_tokens = sum(s.token_count for s in result)

        return CompressedContext(

            segments=result,

            original_token_count=original_tokens,

            compressed_token_count=compressed_tokens,

            compression_ratio=round(

                1.0 - compressed_tokens / max(original_tokens, 1), 3

            ),

            triggered_by=triggered_by,

            compressed_at_state=state_name,

        )

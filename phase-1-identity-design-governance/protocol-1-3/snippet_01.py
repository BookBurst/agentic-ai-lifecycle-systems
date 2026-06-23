from pydantic import BaseModel, Field

class ChangeRecommendation(BaseModel):

    """Structured output for a read-only Planner agent. No tool

    exists in this system that can execute this directly."""

    target_record_id: str

    field_to_change: str

    current_value: str

    proposed_value: str

    reasoning: str = Field(..., min_length=20)

    confidence_score: float = Field(..., ge=0.0, le=1.0)

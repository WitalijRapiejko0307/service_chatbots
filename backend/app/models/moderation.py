"""Moderation models."""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ModerationCategory(str, Enum):
    """Moderation categories."""

    HATE = "hate"
    HARASSMENT = "harassment"
    SEXUAL = "sexual"
    SELF_HARM = "self-harm"
    VIOLENCE = "violence"
    NONE = "none"


class ModerationResult(BaseModel):
    """Moderation result from OpenAI."""

    flagged: bool = Field(..., description="Whether content was flagged")
    categories: dict[str, bool] = Field(
        default_factory=dict, description="Category flags"
    )
    category_scores: dict[str, float] = Field(
        default_factory=dict, description="Category scores"
    )
    category: Optional[ModerationCategory] = Field(
        None, description="Primary violation category"
    )

    class Config:
        """Pydantic config."""

        use_enum_values = True


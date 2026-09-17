"""Enum helper utilities for safe enum value extraction."""

from typing import Any


def get_enum_value(enum_or_value: Any) -> str:
    """Get string value from enum or string.
    
    Handles both enum objects (with .value attribute) and string values.
    This is a defensive utility for cases where data might come from
    different sources (Pydantic models, raw dicts, JSON responses).
    
    Args:
        enum_or_value: Either an enum instance with .value attribute or a string
        
    Returns:
        String representation of the enum value
        
    Examples:
        >>> from app.models.conversation import ConversationStatus
        >>> get_enum_value(ConversationStatus.AI_ACTIVE)
        'AI_ACTIVE'
        >>> get_enum_value('AI_ACTIVE')
        'AI_ACTIVE'
    """
    if hasattr(enum_or_value, "value"):
        return enum_or_value.value
    return str(enum_or_value)

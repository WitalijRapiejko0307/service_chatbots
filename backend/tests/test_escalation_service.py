"""Unit tests for EscalationService (LLM chain mocked)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.escalation import (
    BUILTIN_CONTACT_RULE_ID,
    ContactInfo,
    EscalationDecision,
    EscalationType,
    FAIL_CLOSED_ESCALATION_REASON,
)
from app.services.escalation_service import EscalationService


def _service() -> tuple[EscalationService, AsyncMock]:
    llm_factory = MagicMock()
    svc = EscalationService(llm_factory)
    svc.escalation_chain = AsyncMock()
    return svc, svc.escalation_chain


def _decision(**kwargs) -> EscalationDecision:
    defaults = {
        "needs_escalation": False,
        "escalation_type": EscalationType.NONE,
        "confidence": 1.0,
        "reason": "No escalation",
        "suggested_action": "continue_ai",
        "matched_rule_ids": [],
        "extracted_contacts": ContactInfo(),
    }
    defaults.update(kwargs)
    return EscalationDecision(**defaults)


@pytest.mark.asyncio
async def test_detect_escalation_no_match_on_benign_message():
    service, chain = _service()
    chain.detect = AsyncMock(return_value=_decision())

    decision = await service.detect_escalation("What are your opening hours?")

    assert decision.needs_escalation is False
    assert decision.escalation_type == EscalationType.NONE


@pytest.mark.asyncio
async def test_detect_escalation_normalizes_matched_rule_ids():
    service, chain = _service()
    chain.detect = AsyncMock(
        return_value=_decision(
            needs_escalation=False,
            matched_rule_ids=[" legacy_urgent ", "custom_rule_1"],
            confidence=0.5,
        )
    )

    decision = await service.detect_escalation("I need a human now")

    assert decision.needs_escalation is True
    assert decision.matched_rule_ids == ["legacy_urgent", "custom_rule_1"]
    assert decision.escalation_type == EscalationType.URGENT
    assert decision.confidence >= 0.95


@pytest.mark.asyncio
async def test_detect_escalation_builtin_contact_rule_maps_to_booking():
    service, chain = _service()
    chain.detect = AsyncMock(
        return_value=_decision(
            matched_rule_ids=[BUILTIN_CONTACT_RULE_ID],
            escalation_type=EscalationType.NONE,
        )
    )

    decision = await service.detect_escalation("Call me +971501234567")

    assert decision.needs_escalation is True
    assert decision.escalation_type == EscalationType.BOOKING


@pytest.mark.asyncio
async def test_detect_escalation_custom_rule_without_legacy_suffix():
    service, chain = _service()
    chain.detect = AsyncMock(
        return_value=_decision(
            matched_rule_ids=["price_complaint"],
            escalation_type=EscalationType.NONE,
        )
    )

    decision = await service.detect_escalation("Your prices are outrageous")

    assert decision.needs_escalation is True
    assert decision.escalation_type == EscalationType.CUSTOM


@pytest.mark.asyncio
async def test_detect_escalation_fail_closed_on_chain_error():
    service, chain = _service()
    chain.detect = AsyncMock(side_effect=RuntimeError("LLM timeout"))

    decision = await service.detect_escalation("urgent help")

    assert decision.needs_escalation is True
    assert decision.escalation_type == EscalationType.CUSTOM
    assert decision.reason == FAIL_CLOSED_ESCALATION_REASON


@pytest.mark.asyncio
async def test_should_escalate_returns_bool_and_decision():
    service, chain = _service()
    chain.detect = AsyncMock(
        return_value=_decision(
            needs_escalation=True,
            escalation_type=EscalationType.MEDICAL,
            confidence=0.9,
            reason="Medical question",
            suggested_action="human_review",
        )
    )

    should, decision = await service.should_escalate("My dog is vomiting blood")

    assert should is True
    assert decision.escalation_type == EscalationType.MEDICAL


@pytest.mark.asyncio
async def test_detect_escalation_coerces_none_type_when_flag_set():
    service, chain = _service()
    chain.detect = AsyncMock(
        return_value=_decision(
            needs_escalation=True,
            escalation_type=EscalationType.NONE,
            confidence=0.8,
            reason="Classifier said escalate",
            suggested_action="human_review",
        )
    )

    decision = await service.detect_escalation("operator please")

    assert decision.needs_escalation is True
    assert decision.escalation_type == EscalationType.CUSTOM


def test_get_escalation_reason_maps_known_types():
    service, _ = _service()

    urgent = _decision(
        needs_escalation=True,
        escalation_type=EscalationType.URGENT,
        confidence=1.0,
        reason="x",
        suggested_action="human_review",
    )
    assert "Urgent" in service.get_escalation_reason(urgent)
    assert service.get_escalation_reason(_decision()) == "No escalation needed"


@pytest.mark.asyncio
async def test_detect_escalation_is_stateless_no_dedup():
    """EscalationService does not track conversation status; repeated calls are independent."""
    service, chain = _service()
    chain.detect = AsyncMock(
        return_value=_decision(
            needs_escalation=True,
            escalation_type=EscalationType.BOOKING,
            confidence=0.9,
            reason="Book visit",
            suggested_action="human_review",
            matched_rule_ids=["legacy_booking"],
        )
    )

    first = await service.detect_escalation("book appointment", conversation_context={"conversation_id": "c1"})
    second = await service.detect_escalation("book appointment", conversation_context={"conversation_id": "c1"})

    assert first.needs_escalation is True
    assert second.needs_escalation is True
    assert chain.detect.await_count == 2

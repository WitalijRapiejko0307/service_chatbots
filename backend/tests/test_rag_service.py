"""Unit tests for RAGService (no network, no Postgres)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.exceptions import RAGServiceError
from app.models.agent_config import AgentConfig, ProfileConfig, RAGConfig
from app.services.rag_service import (
    MEDIA_SCORE_THRESHOLD,
    RAGService,
    _rag_file_type_to_media_type,
)
from tests.conftest import DummySettings


class RagDummySettings(DummySettings):
    rag_context_max_chars = 28000
    rag_vector_recall_k = 24
    openai_embedding_model = "text-embedding-3-small"
    openai_embedding_dimensions = 1536


def _agent_config(**rag_retrieval) -> AgentConfig:
    return AgentConfig(
        agent_id="agent-1",
        project="test",
        profile=ProfileConfig(
            agent_display_name="Test Bot",
            company_display_name="Test Co",
        ),
        rag=RAGConfig(retrieval=dict(rag_retrieval)),
    )


def _make_service() -> tuple[RAGService, AsyncMock]:
    llm_factory = MagicMock()
    rag_client = AsyncMock()
    service = RAGService(llm_factory, rag_client)
    service.rag_chain = AsyncMock()
    return service, service.rag_chain


def _chunk(
    *,
    title: str = "Doc",
    content: str = "Body",
    score: float = 0.9,
    file_url: str | None = None,
    file_type: str | None = None,
) -> dict:
    row = {"title": title, "content": content, "score": score}
    if file_url:
        row["file_url"] = file_url
    if file_type:
        row["file_type"] = file_type
    return row


@pytest.fixture(autouse=True)
def _patch_settings():
    with patch("app.services.rag_service.get_settings", return_value=RagDummySettings()):
        yield


@pytest.mark.asyncio
async def test_retrieve_context_returns_relevant_chunks():
    service, chain = _make_service()
    hits = [_chunk(title="Policy", content="Refund within 14 days", score=0.85)]
    chain.retrieve = AsyncMock(return_value=hits)

    results = await service.retrieve_context("refund policy", "agent-1")

    assert results == hits
    chain.retrieve.assert_awaited_once()
    call = chain.retrieve.await_args.kwargs
    assert call["agent_id"] == "agent-1"
    assert call["query"] == "refund policy"
    assert call["index_name"] == "agent_agent-1_documents"
    assert call["top_k"] == 24  # max(6, rag_vector_recall_k floor)


@pytest.mark.asyncio
async def test_retrieve_context_empty_knowledge_base():
    service, chain = _make_service()
    chain.retrieve = AsyncMock(return_value=[])

    results = await service.retrieve_context("anything", "agent-42")

    assert results == []


@pytest.mark.asyncio
async def test_retrieve_context_search_backend_error_returns_empty():
    service, chain = _make_service()
    chain.retrieve = AsyncMock(side_effect=RuntimeError("opensearch down"))

    results = await service.retrieve_context("query", "agent-1")

    assert results == []


@pytest.mark.asyncio
async def test_get_formatted_context_includes_chunk_text():
    service, chain = _make_service()
    chain.retrieve = AsyncMock(
        return_value=[_chunk(title="Hours", content="Mon-Fri 9-18", score=0.7)]
    )

    context = await service.get_formatted_context("working hours", "agent-1")

    assert "[1] Hours" in context
    assert "Mon-Fri 9-18" in context


@pytest.mark.asyncio
async def test_get_formatted_context_empty_when_no_hits():
    service, chain = _make_service()
    chain.retrieve = AsyncMock(return_value=[])

    assert await service.get_formatted_context("missing", "agent-1") == ""


@pytest.mark.asyncio
async def test_get_formatted_context_respects_context_budget():
    service, chain = _make_service()
    chain.retrieve = AsyncMock(
        return_value=[
            _chunk(title="A", content="x" * 200, score=0.95),
            _chunk(title="B", content="y" * 200, score=0.90),
        ]
    )
    cfg = _agent_config(max_context_chars=120)

    context = await service.get_formatted_context(
        "big docs", "agent-1", agent_config=cfg
    )

    assert len(context) <= 120
    assert "[1] A" in context
    assert "y" * 50 not in context


@pytest.mark.asyncio
async def test_get_formatted_context_backend_error_returns_empty_string():
    service, chain = _make_service()
    chain.retrieve = AsyncMock(side_effect=ConnectionError("storage unavailable"))

    context = await service.get_formatted_context("query", "agent-1")

    assert context == ""


@pytest.mark.asyncio
async def test_vector_recall_k_override_from_agent_config():
    service, chain = _make_service()
    chain.retrieve = AsyncMock(return_value=[])
    cfg = _agent_config(vector_recall_k=10)

    await service.retrieve_context("q", "agent-1", top_k=6, agent_config=cfg)

    assert chain.retrieve.await_args.kwargs["top_k"] == 10


@pytest.mark.asyncio
async def test_get_context_and_media_single_retrieval_with_media_filter():
    service, chain = _make_service()
    chain.retrieve = AsyncMock(
        return_value=[
            _chunk(
                title="Brochure",
                content="See image",
                score=0.75,
                file_url="https://cdn/img.jpg",
                file_type="image",
            ),
            _chunk(
                title="Weak",
                content="low score",
                score=0.3,
                file_url="https://cdn/skip.jpg",
                file_type="image",
            ),
        ]
    )

    context, media = await service.get_context_and_media("brochure", "agent-1")

    assert "Brochure" in context
    assert len(media) == 1
    assert media[0]["url"] == "https://cdn/img.jpg"
    assert media[0]["media_type"] == "image"
    assert media[0]["score"] == 0.75
    chain.retrieve.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_context_and_media_respects_media_score_threshold():
    service, chain = _make_service()
    borderline = MEDIA_SCORE_THRESHOLD - 0.01
    chain.retrieve = AsyncMock(
        return_value=[
            _chunk(
                title="Almost",
                content="c",
                score=borderline,
                file_url="https://cdn/near.jpg",
                file_type="image",
            )
        ]
    )

    _, media = await service.get_context_and_media("q", "agent-1")

    assert media == []


@pytest.mark.asyncio
async def test_get_context_and_media_retrieval_error_returns_empty():
    service, chain = _make_service()
    chain.retrieve = AsyncMock(side_effect=TimeoutError("vector store timeout"))

    context, media = await service.get_context_and_media("q", "agent-1")

    assert context == ""
    assert media == []


@pytest.mark.asyncio
async def test_delete_agent_documents_delegates_to_client():
    service, _chain = _make_service()
    service.rag_client.delete_documents_by_agent = AsyncMock(return_value=3)

    deleted = await service.delete_agent_documents("agent-99")

    assert deleted == 3
    service.rag_client.delete_documents_by_agent.assert_awaited_once_with(
        index_name="agent_agent-99_documents",
        agent_id="agent-99",
    )


def test_rag_file_type_to_media_type_mapping():
    assert _rag_file_type_to_media_type("image") == "image"
    assert _rag_file_type_to_media_type("video") == "video"
    assert _rag_file_type_to_media_type("audio") == "audio"
    assert _rag_file_type_to_media_type("pdf") == "document"
    assert _rag_file_type_to_media_type(None) == "document"


@pytest.mark.asyncio
async def test_index_documents_raises_rag_service_error_on_fatal_failure():
    service, chain = _make_service()
    chain._get_embeddings = AsyncMock(side_effect=RuntimeError("embeddings offline"))

    with pytest.raises(RAGServiceError, match="Failed to index documents"):
        await service.index_documents("agent-1", [{"id": "d1", "content": "text"}])

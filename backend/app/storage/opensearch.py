"""OpenSearch vector store client."""

from functools import lru_cache
from typing import Any, Optional

from opensearchpy import AsyncOpenSearch, RequestsHttpConnection
from opensearchpy.helpers import async_bulk

from app.config import Settings, get_settings


class OpenSearchClient:
    """OpenSearch client wrapper for vector search."""

    def __init__(self, settings: Settings):
        """Initialize OpenSearch client."""
        self.settings = settings
        self.client: Optional[AsyncOpenSearch] = None

    async def connect(self) -> AsyncOpenSearch:
        """Connect to OpenSearch."""
        if self.client is None:
            if not self.settings.opensearch_endpoint:
                raise ValueError("OpenSearch endpoint not configured")

            # Parse endpoint URL
            endpoint = self.settings.opensearch_endpoint
            if endpoint.startswith("http://") or endpoint.startswith("https://"):
                # Extract host and port
                url_parts = endpoint.replace("http://", "").replace("https://", "").split(":")
                host = url_parts[0]
                port = int(url_parts[1]) if len(url_parts) > 1 else (443 if self.settings.opensearch_use_ssl else 80)
            else:
                host = endpoint.split(":")[0]
                port = int(endpoint.split(":")[1]) if ":" in endpoint else (443 if self.settings.opensearch_use_ssl else 80)

            self.client = AsyncOpenSearch(
                hosts=[{"host": host, "port": port}],
                http_auth=(
                    (self.settings.opensearch_username, self.settings.opensearch_password)
                    if self.settings.opensearch_username
                    else None
                ),
                use_ssl=self.settings.opensearch_use_ssl,
                verify_certs=self.settings.opensearch_verify_certs,
                ssl_show_warn=False,
                connection_class=RequestsHttpConnection,
            )

        return self.client

    async def create_index(
        self,
        index_name: str,
        vector_dimension: int = 1536,
        shards: int = 1,
        replicas: int = 0,
    ) -> bool:
        """Create OpenSearch index with vector field."""
        client = await self.connect()

        index_body = {
            "settings": {
                "number_of_shards": shards,
                "number_of_replicas": replicas,
            },
            "mappings": {
                "properties": {
                    "agent_id": {"type": "keyword"},
                    "document_id": {"type": "keyword"},
                    "title": {"type": "text"},
                    "content": {"type": "text"},
                    "embedding": {
                        "type": "knn_vector",
                        "dimension": vector_dimension,
                        "method": {
                            "name": "hnsw",
                            "space_type": "cosinesimil",
                            "engine": "nmslib",
                        },
                    },
                }
            },
        }

        try:
            if await client.indices.exists(index=index_name):
                return False  # Index already exists

            await client.indices.create(index=index_name, body=index_body)
            return True
        except Exception as e:
            raise RuntimeError(f"Failed to create index {index_name}: {e}") from e

    async def index_document(
        self,
        index_name: str,
        agent_id: str,
        document_id: str,
        title: str,
        content: str,
        embedding: list[float],
    ) -> bool:
        """Index a document with embedding."""
        client = await self.connect()

        document = {
            "agent_id": agent_id,
            "document_id": document_id,
            "title": title,
            "content": content,
            "embedding": embedding,
        }

        try:
            await client.index(index=index_name, id=document_id, body=document)
            return True
        except Exception as e:
            raise RuntimeError(f"Failed to index document {document_id}: {e}") from e

    async def bulk_index_documents(
        self,
        index_name: str,
        documents: list[dict[str, Any]],
    ) -> tuple[int, int]:
        """Bulk index documents."""
        client = await self.connect()

        actions = []
        for doc in documents:
            actions.append(
                {
                    "_index": index_name,
                    "_id": doc["document_id"],
                    "_source": doc,
                }
            )

        try:
            success_count, failed_items = await async_bulk(client, actions)
            return success_count, len(failed_items)
        except Exception as e:
            raise RuntimeError(f"Failed to bulk index documents: {e}") from e

    async def search(
        self,
        index_name: str,
        query_embedding: list[float],
        agent_id: str,
        top_k: int = 6,
        score_threshold: float = 0.2,
    ) -> list[dict[str, Any]]:
        """Search for similar documents."""
        client = await self.connect()

        query = {
            "size": top_k,
            "query": {
                "bool": {
                    "must": [
                        {
                            "knn": {
                                "embedding": {
                                    "vector": query_embedding,
                                    "k": top_k,
                                }
                            }
                        }
                    ],
                    "filter": [{"term": {"agent_id": agent_id}}],
                }
            },
            "min_score": score_threshold,
        }

        try:
            response = await client.search(index=index_name, body=query)
            hits = response.get("hits", {}).get("hits", [])
            results = []
            for hit in hits:
                results.append(
                    {
                        "document_id": hit["_source"].get("document_id"),
                        "title": hit["_source"].get("title"),
                        "content": hit["_source"].get("content"),
                        "score": hit.get("_score", 0.0),
                    }
                )
            return results
        except Exception as e:
            raise RuntimeError(f"Failed to search index {index_name}: {e}") from e

    async def delete_documents_by_agent(
        self, index_name: str, agent_id: str
    ) -> int:
        """Delete all documents for an agent."""
        client = await self.connect()

        query = {"query": {"term": {"agent_id": agent_id}}}

        try:
            response = await client.delete_by_query(index=index_name, body=query)
            return response.get("deleted", 0)
        except Exception as e:
            raise RuntimeError(
                f"Failed to delete documents for agent {agent_id}: {e}"
            ) from e

    async def close(self) -> None:
        """Close OpenSearch connection."""
        if self.client:
            await self.client.close()
            self.client = None


@lru_cache()
def get_opensearch_client() -> OpenSearchClient:
    """Get cached OpenSearch client instance."""
    settings = get_settings()
    return OpenSearchClient(settings)









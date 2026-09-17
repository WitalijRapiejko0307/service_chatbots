"""Provider-agnostic storage service interface."""

from abc import ABC, abstractmethod
from typing import Optional


class StorageServiceError(Exception):
    """Raised when any storage operation fails."""


class StorageService(ABC):
    """Abstract interface for file storage backends."""

    @abstractmethod
    def upload_file(
        self,
        file_bytes: bytes,
        filename: str,
        agent_id: str,
        folder_path: str = "",
        document_id: Optional[str] = None,
    ) -> str:
        """Upload a RAG document file and return its public URL."""

    @abstractmethod
    def upload_chat_media(
        self,
        file_bytes: bytes,
        filename: str,
        mimetype: str = "application/octet-stream",
    ) -> str:
        """Upload chat media and return its public URL."""

    @abstractmethod
    def delete_by_url(self, file_url: str) -> bool:
        """Delete a file by its public URL."""


def get_storage_service() -> StorageService:
    """Return the configured storage backend instance."""
    from app.config import get_settings

    settings = get_settings()
    backend = (getattr(settings, "storage_backend", None) or "local").lower()

    if backend == "local":
        from app.services.local_storage_service import LocalStorageService

        return LocalStorageService(settings)

    if backend == "s3":
        from app.services.s3_service import S3StorageService

        return S3StorageService(settings)

    raise StorageServiceError(
        f"Unsupported STORAGE_BACKEND={backend!r}. Use 'local' or 's3'."
    )

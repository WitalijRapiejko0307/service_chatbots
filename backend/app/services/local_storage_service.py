"""Local filesystem storage for RAG documents and chat media."""

import os
import re
import uuid
from pathlib import Path
from typing import Optional
from urllib.parse import quote

from app.config import Settings
from app.services.storage_service import StorageService, StorageServiceError


def _safe_filename(filename: str) -> str:
    base = os.path.basename(filename or "file")
    base = re.sub(r"[^\w.\-]+", "_", base)
    return base or "file"


class LocalStorageService(StorageService):
    """Store files on disk and serve them via /storage static mount."""

    def __init__(self, settings: Settings):
        self.root = Path(settings.local_storage_path)
        self.public_prefix = settings.local_storage_public_url.rstrip("/")
        self.root.mkdir(parents=True, exist_ok=True)

    def _public_url(self, rel_path: str) -> str:
        return f"{self.public_prefix}/{quote(rel_path, safe='/')}"

    def upload_file(
        self,
        file_bytes: bytes,
        filename: str,
        agent_id: str,
        folder_path: str = "",
        document_id: Optional[str] = None,
    ) -> str:
        doc_id = document_id or str(uuid.uuid4())
        ext = Path(_safe_filename(filename)).suffix or ".bin"
        rel_parts = ["rag", agent_id]
        if folder_path:
            rel_parts.append(folder_path.strip("/"))
        rel_parts.append(f"{doc_id}{ext}")
        rel_path = "/".join(rel_parts)
        dest = self.root / rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            dest.write_bytes(file_bytes)
        except OSError as e:
            raise StorageServiceError(f"Failed to write file: {e}") from e
        return self._public_url(rel_path)

    def upload_chat_media(
        self,
        file_bytes: bytes,
        filename: str,
        mimetype: str = "application/octet-stream",
    ) -> str:
        ext = Path(_safe_filename(filename)).suffix or ".bin"
        rel_path = f"chat-media/{uuid.uuid4()}{ext}"
        dest = self.root / rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            dest.write_bytes(file_bytes)
        except OSError as e:
            raise StorageServiceError(f"Failed to write chat media: {e}") from e
        return self._public_url(rel_path)

    def delete_by_url(self, file_url: str) -> bool:
        prefix = self.public_prefix + "/"
        if not file_url.startswith(prefix):
            return False
        rel = file_url[len(prefix) :]
        rel = rel.replace("%2F", "/").replace("%2f", "/")
        target = self.root / rel
        if target.exists() and target.is_file():
            target.unlink(missing_ok=True)
            return True
        return False

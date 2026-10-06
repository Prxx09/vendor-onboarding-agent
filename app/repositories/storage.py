from pathlib import Path, PurePosixPath
from typing import Protocol

from app.config import Settings
from supabase import Client, create_client


class DocumentStorage(Protocol):
    def upload(self, path: str, content: bytes, content_type: str = "application/octet-stream") -> str: ...
    def download(self, path: str) -> bytes: ...
    def exists(self, path: str) -> bool: ...


class LocalDocumentStorage:
    def __init__(self, root: str | Path = "data/uploads") -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def upload(self, path: str, content: bytes, content_type: str = "application/octet-stream") -> str:
        del content_type
        target = self._target(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        return PurePosixPath(path).as_posix()

    def download(self, path: str) -> bytes:
        return self._target(path).read_bytes()

    def exists(self, path: str) -> bool:
        return self._target(path).is_file()

    def _target(self, path: str) -> Path:
        target = (self.root / Path(path)).resolve()
        if target != self.root and self.root not in target.parents:
            raise ValueError("Storage path must remain inside the configured uploads directory")
        return target


class SupabaseDocumentStorage:
    BUCKET = "vendor-documents"

    def __init__(self, settings: Settings, client: Client | None = None) -> None:
        if client is None and (not settings.supabase_url or not settings.supabase_service_key):
            raise ValueError(
                "SUPABASE_URL and SUPABASE_SERVICE_KEY are required for Supabase document storage"
            )
        self.client = client or create_client(settings.supabase_url, settings.supabase_service_key)

    def upload(self, path: str, content: bytes, content_type: str = "application/octet-stream") -> str:
        self.client.storage.from_(self.BUCKET).upload(
            path,
            content,
            {"content-type": content_type, "upsert": "true"},
        )
        return path

    def download(self, path: str) -> bytes:
        return self.client.storage.from_(self.BUCKET).download(path)

    def exists(self, path: str) -> bool:
        parent = str(PurePosixPath(path).parent)
        name = PurePosixPath(path).name
        files = self.client.storage.from_(self.BUCKET).list(parent if parent != "." else "")
        return any(item.get("name") == name for item in files)

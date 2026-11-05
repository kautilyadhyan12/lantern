"""File storage: one JSON document per investigation, saved copies by content hash."""

import hashlib
import os
import re
import secrets
from datetime import UTC, datetime
from pathlib import Path

from lantern.models import Investigation

_ID = re.compile(r"^[a-f0-9]{12}$")
_SHA = re.compile(r"^[a-f0-9]{64}$")


class Store:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        for name in ("investigations", "blobs", "texts"):
            (self.root / name).mkdir(parents=True, exist_ok=True)

    def new_id(self) -> str:
        return secrets.token_hex(6)

    def save(self, investigation: Investigation) -> None:
        path = self._investigation_path(investigation.id)
        _atomic_write(path, investigation.model_dump_json(indent=1).encode())

    def load(self, investigation_id: str) -> Investigation | None:
        if not _ID.match(investigation_id):
            return None
        path = self._investigation_path(investigation_id)
        if not path.exists():
            return None
        return Investigation.model_validate_json(path.read_bytes())

    def all(self) -> list[Investigation]:
        items = []
        for path in (self.root / "investigations").glob("*.json"):
            loaded = self.load(path.stem)
            if loaded is not None:
                items.append(loaded)
        return sorted(items, key=lambda item: item.created_at, reverse=True)

    def started_today(self) -> int:
        """Investigations started today, counting each "continue" as one more."""
        today = datetime.now(UTC).date()
        starts = [item.created_at for item in self.all()]
        starts += [at for item in self.all() for at in item.continued_at]
        return sum(1 for at in starts if at.date() == today)

    def put_blob(self, data: bytes) -> str:
        return self._put("blobs", data, ".bin")

    def put_text(self, text: str) -> str:
        return self._put("texts", text.encode(), ".txt")

    def text(self, sha256: str) -> str | None:
        if not _SHA.match(sha256):
            return None
        path = self.root / "texts" / f"{sha256}.txt"
        return path.read_text(encoding="utf-8") if path.exists() else None

    def _put(self, kind: str, data: bytes, suffix: str) -> str:
        digest = hashlib.sha256(data).hexdigest()
        path = self.root / kind / f"{digest}{suffix}"
        if not path.exists():
            _atomic_write(path, data)
        return digest

    def _investigation_path(self, investigation_id: str) -> Path:
        return self.root / "investigations" / f"{investigation_id}.json"


def _atomic_write(path: Path, data: bytes) -> None:
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(4)}.tmp")
    temporary.write_bytes(data)
    os.replace(temporary, path)

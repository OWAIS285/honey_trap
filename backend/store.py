"""Persistence: Firestore for calls, turns, details, strains, drills; Cloud Storage for recordings."""

import asyncio
import hashlib
import logging
from datetime import datetime, timedelta, timezone
from functools import wraps

import config

log = logging.getLogger("stallwart.store")


def owner_hash(client_id: str) -> str:
    return hashlib.sha256(client_id.encode()).hexdigest()


def expiry() -> datetime:
    return datetime.now(timezone.utc) + timedelta(days=config.RETENTION_DAYS)


def clean(doc: dict | None) -> dict | None:
    """Make a Firestore document JSON-safe and drop server-only fields."""
    if doc is None:
        return None
    out = {}
    for key, value in doc.items():
        if key in ("expiresAt", "ownerHash", "shareKey"):
            continue
        out[key] = value.isoformat() if isinstance(value, datetime) else value
    return out


def _safe(default):
    def deco(fn):
        @wraps(fn)
        async def wrapper(*args, **kwargs):
            try:
                return await fn(*args, **kwargs)
            except Exception:  # noqa: BLE001 - storage problems must never kill a live call
                log.exception("store.%s failed", fn.__name__)
                return default() if callable(default) else default

        return wrapper

    return deco


class Store:
    def __init__(self) -> None:
        self._fs = None
        self._bucket = None

    @property
    def fs(self):
        if self._fs is None:
            from google.cloud import firestore

            self._fs = firestore.AsyncClient(project=config.PROJECT)
        return self._fs

    def bucket(self):
        if self._bucket is None:
            from google.cloud import storage

            self._bucket = storage.Client(project=config.PROJECT).bucket(config.RECORDINGS_BUCKET)
        return self._bucket

    @_safe(None)
    async def put(self, path: str, data: dict, merge: bool = True) -> None:
        await self.fs.document(path).set({**data, "expiresAt": expiry()}, merge=merge)

    @_safe(None)
    async def update(self, path: str, data: dict) -> None:
        await self.fs.document(path).set(data, merge=True)

    @_safe(None)
    async def get(self, path: str) -> dict | None:
        snap = await self.fs.document(path).get()
        return snap.to_dict() if snap.exists else None

    @_safe(list)
    async def list_sub(self, path: str, order: str | None = None) -> list[dict]:
        query = self.fs.collection(path)
        if order:
            query = query.order_by(order)
        return [d.to_dict() async for d in query.stream()]

    @_safe(list)
    async def list_owned(self, collection: str, owner: str, limit: int = 60) -> list[dict]:
        from google.cloud.firestore_v1.base_query import FieldFilter

        query = self.fs.collection(collection).where(filter=FieldFilter("ownerHash", "==", owner)).limit(limit)
        return [d.to_dict() async for d in query.stream()]

    @_safe(list)
    async def list_where(self, collection: str, field: str, value, limit: int = 200) -> list[dict]:
        from google.cloud.firestore_v1.base_query import FieldFilter

        query = self.fs.collection(collection).where(filter=FieldFilter(field, "==", value)).limit(limit)
        return [d.to_dict() async for d in query.stream()]

    @_safe(None)
    async def transact(self, path: str, step):
        """Read-modify-write one document atomically. step(current or None) -> (new document, result)."""
        from google.cloud.firestore import async_transactional

        ref = self.fs.document(path)

        @async_transactional
        async def run(transaction):
            snap = await ref.get(transaction=transaction)
            new, result = step(snap.to_dict() if snap.exists else None)
            transaction.set(ref, new)
            return result

        return await run(self.fs.transaction())

    @_safe(None)
    async def put_recording(self, call_id: str, data: bytes) -> str | None:
        path = f"calls/{call_id}.wav"
        await asyncio.to_thread(self.bucket().blob(path).upload_from_string, data, "audio/wav")
        return path

    @_safe(None)
    async def get_recording(self, path: str) -> bytes | None:
        return await asyncio.to_thread(self.bucket().blob(path).download_as_bytes)


store = Store()

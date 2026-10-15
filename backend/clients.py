"""Gemini clients: voice model and text model are served from different locations."""

from functools import lru_cache
import asyncio
import logging

from google import genai
from google.genai import types

import config

log = logging.getLogger("stallwart.clients")


@lru_cache
def _client(location: str, timeout_ms: int = 0) -> genai.Client:
    options = types.HttpOptions(timeout=timeout_ms) if timeout_ms else None
    if config.USE_VERTEX:
        return genai.Client(vertexai=True, project=config.PROJECT, location=location, http_options=options)
    return genai.Client(http_options=options)


def live_client() -> genai.Client:
    return _client(config.LIVE_LOCATION)


def text_client() -> genai.Client:
    # Flash latency has a long tail; a per-request cap lets callers retry instead of hanging for a minute.
    return _client(config.TEXT_LOCATION, 20000)


async def flash(client, *, contents, cfg, attempts: int = 2, model: str | None = None):
    """One Flash request, retried with a short backoff on timeouts, 429s and 5xx. Raises the last error."""
    for attempt in range(attempts):
        try:
            return await client.aio.models.generate_content(model=model or config.FLASH_MODEL, contents=contents, config=cfg)
        except Exception as exc:  # noqa: BLE001
            if attempt == attempts - 1:
                raise
            delay = min(8.0, 1.5 * 2**attempt)
            log.warning("flash request failed (%s), retrying in %.1fs", type(exc).__name__, delay)
            await asyncio.sleep(delay)

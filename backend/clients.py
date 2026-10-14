"""Gemini clients: voice model and text model are served from different locations."""

from functools import lru_cache

from google import genai

import config


@lru_cache
def _client(location: str) -> genai.Client:
    if config.USE_VERTEX:
        return genai.Client(vertexai=True, project=config.PROJECT, location=location)
    return genai.Client()


def live_client() -> genai.Client:
    return _client(config.LIVE_LOCATION)


def text_client() -> genai.Client:
    return _client(config.TEXT_LOCATION)

"""Text-mode session: the same persona and analysis as the voice call, over chat with Gemini Flash."""

import asyncio
import json
import logging
import time

from fastapi import WebSocket
from google.genai import types

import analysis
import config
from clients import flash, text_client
from persona import OPENING_CUE, PERSONA_TOOLS, CallProfile, build_persona_text, turn_note

log = logging.getLogger("stallwart.text")


class TextSession:
    def __init__(self, ws: WebSocket, handler, profile: CallProfile | None = None) -> None:
        self.ws = ws
        self.handler = handler
        self._lock = asyncio.Lock()
        self.stop_reason = "ended"
        self.client_gone = False
        self.persona_prompt = build_persona_text(profile or CallProfile())
        self.replies: list[str] = []

    async def send(self, event: dict) -> None:
        async with self._lock:
            try:
                await self.ws.send_json(event)
            except Exception:  # noqa: BLE001
                self.client_gone = True

    async def _generate(self, contents: list[types.Content], cfg: types.GenerateContentConfig):
        """One persona request (3 attempts); None means the persona stalls this turn."""
        try:
            return await flash(text_client(), contents=contents, cfg=cfg, attempts=3)
        except Exception:  # noqa: BLE001
            log.exception("text model request failed")
            return None

    async def _reply(self, contents: list[types.Content]) -> None:
        cfg = types.GenerateContentConfig(
            system_instruction=self.persona_prompt + turn_note(self.replies),
            tools=PERSONA_TOOLS,
            thinking_config=analysis._thinking(),
            temperature=config.PERSONA_TEMPERATURE,
        )
        text = ""
        for _ in range(4):
            response = await self._generate(contents, cfg)
            if response is None or not response.candidates:
                break
            contents.append(response.candidates[0].content)
            usage = response.usage_metadata
            if usage:
                self.handler.add_usage(usage.prompt_token_count or 0, usage.candidates_token_count or 0)
            calls = response.function_calls or []
            if not calls:
                text = response.text or ""
                break
            parts = []
            for call in calls:
                result = await self.handler.on_tool_call(call.name, dict(call.args or {}))
                parts.append(types.Part.from_function_response(name=call.name, response=result))
            contents.append(types.Content(role="user", parts=parts))
        text = text.strip() or "Hmm... haan ji?"
        self.replies.append(text)
        await self.handler.on_persona_text(text)
        await self.handler.on_turn_complete()

    async def run(self) -> str:
        self.handler.emit = self.send
        started = time.monotonic()
        contents = [types.Content(role="user", parts=[types.Part(text=OPENING_CUE)])]
        try:
            await self._reply(contents)
            while time.monotonic() - started < config.MAX_CALL_SECONDS * 2:
                if self.handler.end_requested:
                    return self.handler.end_reason or "persona_ended"
                try:
                    message = await asyncio.wait_for(self.ws.receive(), timeout=180)
                except asyncio.TimeoutError:
                    return "idle"
                if message["type"] == "websocket.disconnect":
                    self.client_gone = True
                    return "caller_hung_up"
                try:
                    data = json.loads(message.get("text") or "{}")
                except ValueError:
                    continue
                if data.get("type") == "end":
                    return "caller_ended"
                text = str(data.get("text", "")).strip()[:500]
                if data.get("type") == "text" and text:
                    await self.handler.on_typed_caller(text)
                    contents.append(types.Content(role="user", parts=[types.Part(text=text)]))
                    await self._reply(contents)
            return "max_duration"
        except Exception:  # noqa: BLE001
            log.exception("text session failed")
            await self.send({"type": "error", "code": "text_failed", "message": "The chat connection dropped."})
            return "error"

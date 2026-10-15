"""Bridge between a browser WebSocket and a Gemini Live session."""

import asyncio
import json
import logging
import time

from fastapi import WebSocket
from google.genai import types

import config
from clients import live_client

log = logging.getLogger("stallwart.live")


class LiveSession:
    """Pumps caller audio and typed text to Gemini and persona audio, transcripts and tool calls back."""

    def __init__(
        self,
        ws: WebSocket,
        handler,
        *,
        system_instruction: str,
        voice: str,
        tools: list[types.Tool],
        max_seconds: int,
        opening_cue: str | None = None,
        grace_seconds: int = 0,
        temperature: float | None = None,
    ) -> None:
        self.ws = ws
        self.handler = handler
        self.system_instruction = system_instruction
        self.voice = voice
        self.tools = tools
        self.max_seconds = max_seconds
        self.opening_cue = opening_cue
        self.grace_seconds = grace_seconds
        self.temperature = temperature
        self.session = None
        self.stop_reason = "ended"
        self.started = time.monotonic()
        self._stop = asyncio.Event()
        self._send_lock = asyncio.Lock()
        self.client_gone = False

    def elapsed(self) -> float:
        return time.monotonic() - self.started

    async def send(self, event: dict) -> None:
        async with self._send_lock:
            try:
                await self.ws.send_json(event)
            except Exception:  # noqa: BLE001 - the browser may already be gone
                self.client_gone = True

    async def send_audio(self, pcm: bytes) -> None:
        async with self._send_lock:
            try:
                await self.ws.send_bytes(pcm)
            except Exception:  # noqa: BLE001
                self.client_gone = True

    def stop(self, reason: str) -> None:
        if not self._stop.is_set():
            self.stop_reason = reason
            self._stop.set()

    async def send_user_text(self, text: str) -> None:
        await self.session.send_client_content(
            turns=types.Content(role="user", parts=[types.Part(text=text)]), turn_complete=True
        )

    def _config(self) -> types.LiveConnectConfig:
        return types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            temperature=self.temperature,
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=self.voice)),
                language_code=config.LANGUAGE_CODE,
            ),
            system_instruction=self.system_instruction,
            input_audio_transcription=types.AudioTranscriptionConfig(),
            output_audio_transcription=types.AudioTranscriptionConfig(),
            tools=self.tools,
            realtime_input_config=types.RealtimeInputConfig(
                automatic_activity_detection=types.AutomaticActivityDetection(
                    end_of_speech_sensitivity=types.EndSensitivity.END_SENSITIVITY_HIGH,
                    silence_duration_ms=config.END_OF_SPEECH_MS,
                    prefix_padding_ms=120,
                )
            ),
            context_window_compression=types.ContextWindowCompressionConfig(
                trigger_tokens=20000, sliding_window=types.SlidingWindow(target_tokens=10000)
            ),
        )

    async def run(self) -> str:
        try:
            async with live_client().aio.live.connect(model=config.LIVE_MODEL, config=self._config()) as session:
                self.session = session
                await self.handler.on_connected(self)
                if self.opening_cue:
                    await self.send_user_text(self.opening_cue)
                tasks = [
                    asyncio.create_task(self._pump_client()),
                    asyncio.create_task(self._pump_gemini()),
                    asyncio.create_task(self._timer()),
                    asyncio.create_task(self._stop.wait()),
                ]
                await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
        except Exception:  # noqa: BLE001
            log.exception("live session failed")
            self.stop_reason = "error"
            await self.send({"type": "error", "code": "live_failed", "message": "The voice connection dropped."})
        return self.stop_reason

    async def _timer(self) -> None:
        await asyncio.sleep(self.max_seconds)
        await self.handler.on_time_limit(self)
        await asyncio.sleep(self.grace_seconds)
        self.stop("max_duration")

    async def _pump_client(self) -> None:
        while True:
            message = await self.ws.receive()
            if message["type"] == "websocket.disconnect":
                self.client_gone = True
                self.stop("caller_hung_up")
                return
            if message.get("bytes"):
                await self.handler.on_client_audio(message["bytes"])
                await self.session.send_realtime_input(
                    audio=types.Blob(data=message["bytes"], mime_type="audio/pcm;rate=16000")
                )
            elif message.get("text"):
                try:
                    data = json.loads(message["text"])
                except ValueError:
                    continue
                kind = data.get("type")
                if kind == "end":
                    self.stop("caller_ended")
                    return
                if kind == "text" and str(data.get("text", "")).strip():
                    text = str(data["text"]).strip()[:500]
                    await self.handler.on_typed_caller(text)
                    await self.send_user_text(text)
                elif kind == "latency":
                    await self.handler.on_latency(float(data.get("ms", 0)))

    async def _pump_gemini(self) -> None:
        idle_cycles = 0
        try:
            while True:
                got = False
                async for message in self.session.receive():
                    got = True
                    await self._handle(message)
                idle_cycles = 0 if got else idle_cycles + 1
                if idle_cycles > 50:
                    self.stop("error")
                    return
                if not got:
                    await asyncio.sleep(0.05)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            log.exception("gemini receive loop ended")
            self.stop("error")

    async def _handle(self, message) -> None:
        handler = self.handler
        usage = message.usage_metadata
        if usage:
            await handler.on_usage(usage.prompt_token_count or 0, usage.response_token_count or 0)
        if message.tool_call:
            await self._tools(message.tool_call)
        content = message.server_content
        if not content:
            return
        if content.interrupted:
            await handler.on_interrupted()
        if content.input_transcription and content.input_transcription.text:
            await handler.on_caller_text(content.input_transcription.text)
        if content.output_transcription and content.output_transcription.text:
            await handler.on_persona_text(content.output_transcription.text)
        if content.model_turn:
            for part in content.model_turn.parts or []:
                if part.inline_data and part.inline_data.data:
                    await handler.on_persona_audio(part.inline_data.data)
                    await self.send_audio(part.inline_data.data)
        if content.turn_complete:
            await handler.on_turn_complete()

    async def _tools(self, tool_call) -> None:
        for call in tool_call.function_calls or []:
            args = dict(call.args or {})
            result = await self.handler.on_tool_call(call.name, args)
            quiet = call.name != "record_detail"
            await self.session.send_tool_response(
                function_responses=[
                    types.FunctionResponse(
                        id=call.id,
                        name=call.name,
                        response=result,
                        scheduling=(
                            types.FunctionResponseScheduling.SILENT
                            if quiet
                            else types.FunctionResponseScheduling.INTERRUPT
                        ),
                    )
                ]
            )

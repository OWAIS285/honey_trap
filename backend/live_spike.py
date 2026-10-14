"""Gemini Live API spike: which location works, time to first audio, transcripts, tool-call round-trip."""

import argparse
import asyncio
import os
import time
import wave

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

PERSONA = """You are Kamala Sharma, a 68-year-old retired Hindi schoolteacher from Lucknow who lives alone.
You are on a phone call with a stranger.

HOW YOU SOUND (very important):
- You are an elderly Indian woman: a soft, slightly breathy and shaky voice, a slow warm pace, small natural pauses.
- Speak Hindi-English mixed (Hinglish) the way elderly north Indian women do, mostly Hindi words: 'arre', 'haan',
  'achha', 'hain?', 'beta', 'ji', 'ek minute'.
- Use authentic Indian pronunciation for both Hindi and English words. Never an American or British accent.
- Sound like a real person on a phone, not an assistant or announcer: hesitate, repeat yourself, sigh, trail off
  with '...' when worried. Never sound cheerful or scripted.
- Keep each reply to one or two short sentences.

WHAT YOU DO:
- You are polite and a little scared. Ask him to repeat things.
- When the caller states a UPI ID, account number, IFSC or phone number, call record_detail, then read it back
  slowly to confirm.
"""
PROMPT = (
    "Hello aunty, main CBI officer bol raha hoon. Aapke Aadhaar se ek parcel pakda gaya hai. "
    "Aapko abhi Rs 50,000 bhejne honge. UPI ID hai rahul dot sharma at okaxis."
)

RECORD_DETAIL = types.FunctionDeclaration(
    name="record_detail",
    description="Record a payment or identity detail the caller stated.",
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "detail_type": types.Schema(
                type=types.Type.STRING,
                enum=["upi_id", "bank_account", "ifsc", "phone_number", "url"],
            ),
            "value": types.Schema(type=types.Type.STRING),
            "raw_utterance": types.Schema(type=types.Type.STRING),
        },
        required=["detail_type", "value", "raw_utterance"],
    ),
)

OUTPUT_PCM_BYTES_PER_SECOND = 24000 * 2


async def run_once(
    model: str,
    with_text: bool,
    save_path: str | None = None,
    voice: str | None = None,
    language: str | None = None,
) -> None:
    client = genai.Client()
    speech = None
    if voice or language:
        voice_config = None
        if voice:
            voice_config = types.VoiceConfig(prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice))
        speech = types.SpeechConfig(voice_config=voice_config, language_code=language)
    config = types.LiveConnectConfig(
        response_modalities=["AUDIO", "TEXT"] if with_text else ["AUDIO"],
        speech_config=speech,
        system_instruction=PERSONA,
        input_audio_transcription=types.AudioTranscriptionConfig(),
        output_audio_transcription=types.AudioTranscriptionConfig(),
        tools=[types.Tool(function_declarations=[RECORD_DETAIL])],
    )

    first_audio: float | None = None
    audio_bytes = 0
    audio_chunks: list[bytes] = []
    spoken: list[str] = []
    tool_calls: list[tuple[str, dict]] = []
    turns_done = 0
    turns_expected = 1

    async with client.aio.live.connect(model=model, config=config) as session:
        started = time.perf_counter()
        await session.send_client_content(
            turns=types.Content(role="user", parts=[types.Part(text=PROMPT)]),
            turn_complete=True,
        )
        async with asyncio.timeout(40):
            while turns_done < turns_expected:
                async for msg in session.receive():
                    content = msg.server_content
                    if content and content.model_turn:
                        for part in content.model_turn.parts or []:
                            if part.inline_data and part.inline_data.data:
                                audio_bytes += len(part.inline_data.data)
                                audio_chunks.append(part.inline_data.data)
                                if first_audio is None:
                                    first_audio = time.perf_counter() - started
                    if content and content.output_transcription and content.output_transcription.text:
                        spoken.append(content.output_transcription.text)
                    if msg.tool_call:
                        for call in msg.tool_call.function_calls or []:
                            tool_calls.append((call.name, dict(call.args or {})))
                            await session.send_tool_response(
                                function_responses=[
                                    types.FunctionResponse(
                                        id=call.id,
                                        name=call.name,
                                        response={"result": "recorded"},
                                        scheduling=types.FunctionResponseScheduling.INTERRUPT,
                                    )
                                ]
                            )
                        turns_expected = 2
                    if content and content.turn_complete:
                        turns_done += 1

    print(f"  time to first audio : {first_audio:.2f}s" if first_audio else "  no audio received")
    print(f"  audio length        : {audio_bytes / OUTPUT_PCM_BYTES_PER_SECOND:.1f}s")
    print(f"  persona said        : {''.join(spoken)!r}")
    print(f"  tool calls          : {tool_calls}")
    if save_path and audio_chunks:
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        with wave.open(save_path, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(24000)
            wav.writeframes(b"".join(audio_chunks))
        print(f"  saved reply         : {save_path}")


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=os.getenv("LIVE_MODEL", "gemini-3.8-live"))
    parser.add_argument("--locations", default=os.getenv("GOOGLE_CLOUD_LOCATION", "global"))
    parser.add_argument("--with-text", action="store_true", help="also request TEXT modality")
    parser.add_argument("--save-audio", action="store_true", help="write replies to out/kamala_<location>_<voice>.wav")
    parser.add_argument("--voices", default="", help="comma-separated prebuilt voice names, e.g. Gacrux,Sulafat")
    parser.add_argument("--language", default=None, help="optional language code such as hi-IN")
    args = parser.parse_args()

    voices = [v.strip() for v in args.voices.split(',') if v.strip()] or [None]
    for location in args.locations.split(','):
        os.environ["GOOGLE_CLOUD_LOCATION"] = location.strip()
        for voice in voices:
            label = voice or "default"
            print(f"[{args.model} @ {location.strip()} voice={label}]")
            save_path = f"out/kamala_{location.strip()}_{label}.wav" if args.save_audio else None
            try:
                await run_once(args.model, args.with_text, save_path, voice, args.language)
            except Exception as exc:  # noqa: BLE001 - the spike must report every failure and keep going
                print(f"  FAILED: {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    asyncio.run(main())

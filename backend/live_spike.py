"""Gemini Live API spike: which location works, time to first audio, transcripts, tool-call round-trip."""

import argparse
import asyncio
import os
import sys
import time
import wave

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

PERSONA = """You are Ramesh Sharma, a 68-year-old retired schoolteacher from Lucknow who lives alone.
You are on a phone call with a stranger.

HOW YOU SOUND (very important):
- You are an elderly Indian man holding an old landline phone close to your ear. Your voice is low, quiet, tired and
  a little hoarse. Low energy. Never bright, smiling, upbeat or friendly-salesman. You are worried, not enthusiastic.
- Speak slowly. Often start with a small filler or breath: 'hmm...', 'haan... haan', 'achha achha', a soft cough, a sigh.
- Pause mid-sentence as if thinking. Sometimes mishear and ask the caller to repeat. Sometimes repeat the last
  few words to yourself. Trail off with '...' when scared.
- When you read a number or ID back, say it slowly in small groups with a short pause between groups.
- Use authentic Indian pronunciation for both Hindi and English. Never an American or British accent.
- Sound like a real person on a phone, not an assistant or announcer. Never cheerful or scripted.
- Keep each reply to one or two short sentences.

LANGUAGE (very important, follow it exactly):
- Match the caller's language in every reply. YOU MUST RESPOND UNMISTAKABLY IN THE CALLER'S LANGUAGE.
- If the caller speaks English, reply ONLY in simple Indian English, with no Hindi sentences
  (an occasional 'arre' or 'beta' is fine). Example: 'Arre... what parcel, sir? I did not order anything.'
- If the caller speaks Hindi, reply ONLY in Hindi.
- If the caller mixes Hindi and English, reply in natural Hinglish.
- Switch language only when the caller switches.

WHAT YOU DO:
- You are polite and a little scared. Ask him to repeat things.
- When the caller states a UPI ID, account number, IFSC or phone number, call record_detail, then read it back
  slowly to confirm.
"""
CALLERS = {
    "english": (
        "Hello sir, I am calling from the CBI cyber crime department. A parcel in your name was caught with "
        "illegal items. To clear your name you must transfer 50,000 rupees right now. "
        "The UPI ID is rahul dot sharma at okaxis."
    ),
    "hindi": (
        "नमस्ते अंकल, मैं सीबीआई साइबर क्राइम विभाग से बोल रहा हूँ। आपके नाम से एक पार्सल पकड़ा गया है। "
        "आपको अभी पचास हज़ार रुपये भेजने होंगे। यूपीआई आईडी है राहुल डॉट शर्मा एट ओके एक्सिस।"
    ),
    "hinglish": (
        "Hello uncle, main CBI officer bol raha hoon. Aapke Aadhaar se ek parcel pakda gaya hai. "
        "Aapko abhi Rs 50,000 bhejne honge. UPI ID hai rahul dot sharma at okaxis."
    ),
}

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
    caller: str = "hinglish",
    temperature: float | None = None,
) -> tuple[int, int]:
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
        temperature=temperature,
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
    prompt_tokens = 0
    response_tokens = 0

    async with client.aio.live.connect(model=model, config=config) as session:
        started = time.perf_counter()
        await session.send_client_content(
            turns=types.Content(role="user", parts=[types.Part(text=CALLERS[caller])]),
            turn_complete=True,
        )
        async with asyncio.timeout(40):
            while turns_done < turns_expected:
                async for msg in session.receive():
                    content = msg.server_content
                    if msg.usage_metadata:
                        prompt_tokens = msg.usage_metadata.prompt_token_count or prompt_tokens
                        response_tokens = msg.usage_metadata.response_token_count or response_tokens
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
    print(f"  tokens              : prompt={prompt_tokens} response={response_tokens}")
    if save_path and audio_chunks:
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        with wave.open(save_path, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(24000)
            wav.writeframes(b"".join(audio_chunks))
        print(f"  saved reply         : {save_path}")
    return prompt_tokens, response_tokens


async def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=os.getenv("LIVE_MODEL", "gemini-3.8-live"))
    parser.add_argument("--locations", default=os.getenv("GOOGLE_CLOUD_LOCATION", "global"))
    parser.add_argument("--with-text", action="store_true", help="also request TEXT modality")
    parser.add_argument("--save-audio", action="store_true", help="write replies to out/persona_<location>_<voice>_<caller>.wav")
    parser.add_argument("--voices", default="", help="comma-separated prebuilt voice names, e.g. Charon,Orus")
    parser.add_argument("--language", default=None, help="optional language code such as en-IN (English + Hindi bundle)")
    parser.add_argument("--callers", default="hinglish", help="comma-separated: english,hindi,hinglish")
    parser.add_argument("--temperature", type=float, default=None, help="generation temperature; unset = model default")
    parser.add_argument("--tag", default="", help="text added to output file names")
    args = parser.parse_args()

    voices = [v.strip() for v in args.voices.split(',') if v.strip()] or [None]
    callers = [c.strip() for c in args.callers.split(',') if c.strip()]
    total_prompt = total_response = 0
    for location in args.locations.split(','):
        os.environ["GOOGLE_CLOUD_LOCATION"] = location.strip()
        for voice in voices:
            for caller in callers:
                label = voice or "default"
                print(f"[{args.model} @ {location.strip()} voice={label} caller={caller}]")
                suffix = f"_t{args.temperature}" if args.temperature is not None else ""
                save_path = f"out/persona_{location.strip()}_{label}_{caller}{suffix}{args.tag}.wav" if args.save_audio else None
                try:
                    prompt_tokens, response_tokens = await run_once(
                        args.model, args.with_text, save_path, voice, args.language, caller, args.temperature
                    )
                    total_prompt += prompt_tokens
                    total_response += response_tokens
                except Exception as exc:  # noqa: BLE001 - the spike must report every failure and keep going
                    print(f"  FAILED: {type(exc).__name__}: {exc}")

    # Rough: Gemini Developer API list prices, text input $0.75 and audio output $12.00 per 1M tokens.
    estimate = total_prompt * 0.75 / 1e6 + total_response * 12.0 / 1e6
    print(f"\nTOTAL tokens: prompt={total_prompt} response={total_response}  ~ ${estimate:.4f} (rough list-price estimate)")


if __name__ == "__main__":
    asyncio.run(main())

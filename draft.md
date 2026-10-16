# CLAUDE.md — Project "Stallwart"

> Read this whole file before doing anything. It is the single source of truth for this project.
> Deadline: **prototype submission Sunday 18 Oct 2026** (the organisers publish no timezone → **submit by Sunday MORNING IST**; have everything uploaded and link-tested by Saturday night). Today is Wed 14 Oct 2026.
> Event: **Google Cloud AI Builder Cup JAPAC 2026** (Hack2skill × Google Cloud). Theme: **BFSI: Intelligent Risk, Fraud & Financial Experiences**.
> §0 and the model/API facts in §4 were checked against the official site, T&C, RBI and Google docs on 14 Oct 2026. Items marked **VERIFY** are not confirmed yet.
>
> **Status 15 Oct 2026:** backend (live voice, text chat, two-layer extraction, classification, strain, drills, recordings), the animated web app, the recorded replay and the evaluation harness are built and deployed (https://stallwart.web.app). Still open: final eval numbers in the README, deck from the official template, 3-minute video, public repo, real-device mic test, roster/Discord confirmation, 50+ redacted real scam messages.

---

## 0. Hackathon rules we build against (verified 14 Oct 2026)

Sources: aibuildercup.com (Overview, Challenges & Requirements, FAQs, Rewards) and the official Terms & Conditions linked from it.

| Topic | Fact |
|---|---|
| Timeline | Registration 1 Sep–**11 Oct (closed)** · team formation to **14 Oct (T&C: no roster changes after 14 Oct)** · build 7 Sep–**18 Oct** · evaluation 19 Oct–6 Nov · finalists 7 Nov · Demo Day Singapore **4 Dec** (2 members travel, sponsored) |
| Team | 2–4 members; one team = one submission = one theme; a person can be in one team only |
| Eligibility | Working professionals / entrepreneurs / startups only; **21+**; physically based and legal residents of a **JAPAC** country; **no students (full or part-time)** — one student disqualifies the whole team even after the finale; IDs and employment may be verified at any time |
| Tech requirement | Must integrate **Gemini/Gemma** (or be built with Agent Platform / Antigravity / AI Studio) **and** be deployed on **Google Cloud via Cloud Run or Firebase**; built *primarily* on the Google Cloud stack |
| Freshness | Fresh code and original assets created during the event only; pre-existing projects or code = disqualified. No third-party-protected or confidentiality-bound content |
| Mandatory artefacts | (a) live URL on Cloud Run/GCP/Firebase · (b) demo video **strictly under 3 min**, public YouTube/Vimeo/Drive · (c) public GitHub repo · (d) deck PDF with **solution architecture + business case** · (e) problem statement/theme named |
| Language | All materials (code, docs, deck, video) in English |
| Prizes (USD 30,000) | Winner 10k · 1st runner-up 7k · 2nd runner-up 5k · Best Use of Google Cloud AI Tools 2k · Most Impactful Solution 2k · Social Choice 2k · Best UI/UX 2k |
| Conduct / IP | Stay in the official Discord and dashboard and answer organiser checkpoints (non-response can disqualify the team) · Organiser gets a 6-month right of first refusal on any *exclusive* licence of our materials and a perpetual licence to showcase the entry · participants' likeness in recordings may be published |
| Support | support+aibuildercup@hack2skill.com · Discord (link on the site) |

**Action today (Wed 14 Oct):** confirm on the Hack2skill dashboard that both teammates are on the roster (registration closed 11 Oct and rosters freeze after today), both meet every eligibility rule, and both have joined the Discord.

Known site inconsistencies (ask on Discord, don't block on them): the Challenges page still mentions a "social challenge" and categories "Healthcare, Education, Sustainability, Accessibility, Social Good" (template leftovers) — our theme is **BFSI**. The submission-form wording for theme selection, the deadline timezone and the Social Choice Award mechanism are not published.

---

## 1. What we are building (one paragraph)

An AI **scam-call decoy for India**. A Gemini-powered voice persona ("Ramesh Sharma", 68, retired schoolteacher from Lucknow, male voice Achird; this replaces the earlier "Kamala aunty" idea) answers scam calls in **English, Hindi or Hinglish, matching the caller**, keeps scammers talking, and **extracts the mule bank accounts, UPI IDs, phone numbers, links and impersonated agency** in real time. Every captured scam is turned into a **"scam strain"** (the script, red flags, payment method) which powers two outputs:
1. **Bank-ready evidence pack** — extracted accounts/UPI IDs with transcript evidence, timestamps and confidence, so a bank fraud team can act *before* a real victim pays.
2. **Scam vaccine drill** — a harmless, opt-in drill call to an elderly family member built from *that day's real scam script*; the AI breaks character before any real detail is shared and teaches the 3 red flags of that exact script.

**Pitch line:** "We catch the scam, then we turn it into the vaccine."

### How we differ from Apate.ai (must appear on a slide)
| | Apate.ai (Australia) | Us |
|---|---|---|
| Languages / scams | English-first; public demos are Australian/US scams (Amazon, NBN, Medicare) | **Hindi–English (Hinglish) first**, Indian scams: digital arrest, KYC, courier/parcel, TRAI SIM block, investment/task |
| Output | Intelligence for telcos, banks, government; already extracts bank accounts, crypto wallets, phones | **Mule-account evidence pack** with read-back confirmation and transcript evidence, shaped for banks preparing for RBI's *draft* mule-account SOP (60-day debit holds, proposed from 1 Apr 2027) |
| Loop | Trap + intelligence only; no consumer app by design | **Trap → Strain → Vaccine** (captured scripts become same-day drills for opted-in elderly users) |
| Delivery | Telco SIP/RTP diversion at network level; also WhatsApp/Telegram text bots | Browser prototype (no telephony); telco diversion is roadmap |

Do **not** present "extraction" or "chat decoys" as novel — Apate already does both. Our edge is Hinglish/India-specific scams, read-back-confirmed mule evidence aimed at the RBI draft, and the consumer-side vaccine.

---

## 2. HARD RULES (breaking any = disqualification or lost points)

1. **Google AI only inside the product: Gemini (or Gemma).** The official rule is "must integrate Gemini/Gemma (or be built with Agent Platform / Antigravity / AI Studio)"; we go stricter on purpose so no judge can question it. Claude/Copilot may help write code, but no non-Google model may run inside the product.
2. **Deploy on Google Cloud:** backend on **Cloud Run**, frontend on **Firebase Hosting**, data on Firestore — the T&C require the prototype to be built *primarily* on the Google Cloud stack. Region `asia-south1` where available.
3. **Fresh code only**, written during the event (build window opened 7 Sep; our first commit is 14 Oct). Do NOT copy code from any other project, employer or sample app; use personal GCP/GitHub accounts and machines only. Nothing from anyone's workplace — the T&C also bar content that is confidentiality-bound to a third party. Google's official demo apps are for reading, not pasting; credit any adapted snippet in the README.
4. **Public GitHub repo** is a mandatory deliverable → **NEVER commit secrets**. Use Secret Manager + env vars. Provide `.env.example`. Add `.gitignore` for `.env`, keys, service-account JSON.
5. **All submission materials in English** (code, README, deck, video narration/subtitles).
6. **No third-party copyrighted content** in repo/video (no YouTube clips, no copyrighted audio). Datasets are used for evaluation only, cited, and never re-uploaded to the repo. ICFD-31k's data licence is defensive-use only (no scam-script generation, no commercial deployment without the authors' written permission) — never feed it to the drill generator or persona prompts. The Kaggle set is reported as CC BY-NC-ND (**VERIFY** on its page): eval only, no derivatives.
7. **Privacy:** never commit or show real phone numbers, account numbers or UPI IDs from real scam messages. Redact real data to placeholders (e.g. `XXXXXX1234`, `scammer@okaxis` → `redacted@upi`). Demo uses **fictional** values only.
8. The persona must **never** reveal real personal/financial information (it never says any number of its own, in full or in part; it only checks the last four digits a caller claiming to be its bank reads out), never place calls to real people, never insult or threaten, and must end the call if the caller appears to be a genuine non-scam person.
9. **Evidence is a lead, not a verdict.** A payee captured from an unverified caller may be mis-heard or belong to an innocent third party. Every evidence pack carries that disclaimer, separates `confirmed` from `unconfirmed`, and says "suspected / supplied by caller", never "this is a mule". This also matches the RBI draft's stress on not flagging genuine accounts.
10. **Eligibility:** all members are working professionals, 21+, JAPAC residents, no students; the roster is frozen after 14 Oct.

---

## 3. Judging rubric — design every decision against this

| Weight | Criterion (official wording) | What judges are told to look at | How we score |
|---|---|---|---|
| **40%** | Technical Merit & GenAI Implementation: *robustness, Google Cloud architectural depth, technical execution* | Meaningful (not superficial) GenAI use · functional, sound implementation · scalability and sustainability beyond the prototype | Gemini Live native audio + async function calling, Gemini Flash structured verifier/classifier/strain builder, deterministic validators, Vertex AI via service-account ADC, Firestore + anonymous Auth, Cloud Run (WebSockets, autoscaling caps), Firebase Hosting, Secret Manager, Cloud Logging/Monitoring, Cloud Build + Artifact Registry; tests; eval harness; latency metrics; cost-per-call and scale notes on the architecture slide |
| **25%** | Problem Alignment & Impact: *problem-solution fit, measurable real-world viability* | Fit to the chosen theme · clear value for users and industry | ₹ losses (NCRP 2025), RBI draft mule SOP, named buyers, measured accuracy on a **synthetic** Indian benchmark plus our own **real** redacted messages (always say which is which) |
| **25%** | Innovation & Creativity: *originality, inventive GenAI use* | Differentiation from existing solutions · GenAI use beyond basic | Hinglish persona, live extraction with read-back, Trap→Strain→Vaccine loop |
| **10%** | UX & Solution Design | Intuitive, accessible UI · components work together cohesively | Clean, mobile-friendly dashboard; judge-proof demo modes; one coherent flow: trap → dashboard → evidence → strain → drill |

Side prizes to target (USD 2k each): Best Use of Google Cloud AI Tools (show breadth: Live API, Flash structured output, function calling, Vertex auth; stretch: Gemini 3.5 Transcribe), Most Impactful Solution, Social Choice (mechanism unpublished — ask on Discord), Best UI/UX.

---

## 4. Architecture

```
**As built (15 Oct 2026).** The browser talks only to the Cloud Run backend; Firestore rules deny every client, so there is no
Firebase Auth and no client-side Firestore. The browser identifies itself with a random id kept in localStorage (X-Client-Id).

[Browser: mic + speaker + dashboard  (static site on Firebase Hosting, plain ES modules, CSP + no-cache headers)]
      │  WSS /ws/call (voice), /ws/text (chat), /ws/drill (parent)  → straight to the Cloud Run *.run.app URL
      │  16 kHz PCM up / 24 kHz PCM down; JSON events down (transcript, detail, classification, stage, latency, ended)
      │  REST /api/calls, /api/strains, /api/drills (X-Client-Id); recording via /api/calls/{id}/recording?t=<playToken>
      ▼
[Cloud Run: FastAPI backend  (Python, google-genai SDK, own service account, asia-south1, max-instances 3)]
      ├── Gemini Live session (gemini-3.8-live, us-central1, voice Achird)  ── persona "Ramesh Sharma"
      │       └── function calls: record_detail / flag_scam_stage / end_call
      ├── Verifier + classifier: gemini-3.8-flash (global, structured JSON, retries with backoff), off the audio path
      ├── Validators + number normaliser (pure Python, deterministic: Hindi / Hinglish / Devanagari spoken forms)
      ├── Strain builder (gemini-3.8-flash, structured JSON, identifiers redacted)
      ├── Family drill: actor + coach (gemini-3.8-live), stops at the first shared detail or the payment step
      ├── Per-IP limits, concurrency cap, 300 s call cap, KILL_SWITCH env
      └── Firestore (calls, turns, details, strains, drills; TTL on expiresAt) + private GCS bucket (stereo WAV recordings, 14-day lifecycle)
[Vertex AI: model access via ADC]  [Cloud Logging: structured JSON logs]  [Billing budgets + stop_billing.ps1 panic button]
```

### Model & API facts (verified 14 Oct 2026 against Google docs; re-check at M0, docs move fast)
- **Live voice model:** `gemini-3.8-live` (default, low-latency; GA on Vertex, while the Gemini API docs still label the Live API "preview"). `gemini-3.8-live-extended-thinking` adds background reasoning and latency — not needed. `gemini-3.1-flash-live-preview` is legacy. `gemini-2.5-*` models are access-restricted for new Gemini-API projects — avoid.
- **Text / structured output:** `gemini-3.8-flash` (flagship Flash); `gemini-3.5-flash-lite` for cheap bulk eval runs. Optional ASR cross-check for digits: `gemini-3.5-transcribe` (custom-vocabulary biasing, Hindi–English code-switching, timestamps).
- **Auth:** prefer `genai.Client(vertexai=True, project=..., location=...)` with the Cloud Run service account (ADC): no API key to leak and stronger "Google Cloud depth". Keep an AI Studio API-key fallback (Secret Manager) behind an env flag. **Checked 14 Oct 2026 on our project (`backend/live_spike.py`):** `gemini-3.8-live` is served from **`us-central1` only** (404 in `global`, `asia-south1`, `asia-southeast1`, `asia-northeast1`, `europe-west4`, `us-east4`), and `gemini-3.8-flash` from **`global` only** (404 in `us-central1` and `asia-south1`). So the backend builds two clients: `LIVE_LOCATION=us-central1` and `TEXT_LOCATION=global`; Cloud Run and Firestore stay in `asia-south1`. In `us-central1` the Live model answered in Hinglish, read a UPI ID back and made the `record_detail` call with a clean value; first audio ≈ 1.5 s from India for a text prompt.
- **Audio:** raw 16-bit little-endian PCM; input `audio/pcm;rate=16000`, output always 24 kHz.
- **Session limits:** audio-only sessions 15 min and each WebSocket connection ~10 min by default. Handle `goAway`, enable **session resumption** and **context-window compression** for longer calls (128k-token context, audio ≈ 25 tokens/s). Judge-facing live calls are capped at ~5 min anyway.
- **Transcripts:** enable `input_audio_transcription` (with `language_codes` hints such as `hi-IN`, `en-IN`) and `output_audio_transcription`. **VERIFY** whether `text` must also be in `response_modalities` (Vertex docs say yes; Gemini API docs say native-audio models are AUDIO-only).
- **Language/voice:** native-audio models cannot take an explicit language code — steer Hinglish through the system prompt. Pick the voice by listening in AI Studio (`speech_config.voice_config.prebuilt_voice_config.voice_name`).
- **Tools:** on 3.8 Live, function calling is async (`NON_BLOCKING`) by default, so the persona keeps talking while `record_detail` runs. Omit `thinking_level`. Proactive audio is always on (the model may choose not to reply) — test that the persona still answers short caller utterances. Affective dialog was removed.
- **VAD:** server default silence ≈ 800 ms; docs recommend 500–800 ms and warn that <500 ms degrades transcription. Hybrid VAD (client VAD sends `audio_stream_end`) cuts latency. On an `interrupted` event, flush the playback queue (barge-in).
- **Mid-session system-instruction updates** are supported — handy for switching the drill to coach mode.
- **Auth model:** the Live API is server-to-server by default; browser → Cloud Run → Gemini is the right shape (no ephemeral tokens needed).
- **Cloud Run for WebSockets:** request timeout ≥ 900 s, CORS/origin allow-list, `--max-instances` cap, session affinity optional. Firebase Hosting rewrites to Cloud Run time out at 60 s, so the audio WebSocket must not go through Hosting.
- **Reference code:** Google's `GoogleCloudPlatform/generative-ai` repo, `gemini/multimodal-live-api/native-audio-websocket-demo-apps/plain-js-python-sdk-demo-app` (FastAPI + AudioWorklet), is useful to read. Do **not** copy it wholesale (fresh-code rule); write our own.

### Suggested repo layout
```
/backend        FastAPI app, live_session.py, verifier.py, validators.py, normalizer.py, strain.py, drill.py
/frontend/public  plain HTML + ES modules, no build step (Firebase Web SDK from CDN): Call page, Live dashboard, Strain card, Drill page, Evidence export
/eval           datasets/ (gitignored raw), loaders, run_eval.py, metrics.py, results/ (committed JSON/CSV + charts)
/docs           deck.pdf, architecture.png, demo-script.md
/scripts        setup_gcp.ps1, deploy_backend.ps1
/tests          pytest unit tests (validators, normalizer, schemas, persona red-team cases)
CLAUDE.md  README.md  .env.example  .gitignore  LICENSE  firebase.json  firestore.rules  pyproject.toml
```

### Firestore schema
```
calls/{callId}: { mode: "live"|"replay"|"text", ownerUid, public: bool, expiresAt, startedAt, endedAt, durationSec,
                  scamType, scamTypeConfidence, currentStage, status, latencyMsP50, latencyMsP90 }
calls/{callId}/turns/{n}: { speaker: "caller"|"persona", text, ts }
calls/{callId}/details/{id}: { type, rawValue, normalizedValue, valid: bool, source: "live_tool"|"verifier",
                               confirmed: bool, confidence, utteranceRef, firstSeenAt }
strains/{strainId}: { scamType, impersonatedEntity, steps[], redFlags[], paymentMethod, scriptExcerpts[], sourceCallId, createdAt }
drills/{drillId}: { strainId, consentGiven: bool, outcome: "passed"|"failed"|"aborted", stoppedAtStep, debriefText, createdAt }
```
Rules: anonymous Firebase Auth; a visitor reads only calls with their own `ownerUid` plus seeded `public` replay calls; every write goes through the backend (Admin SDK). TTL policy on `expiresAt` (~7 days) purges judge calls.

---

## 5. Persona — "Kamala aunty" (system prompt for the Live session)

Use this as the starting system instruction; iterate on it.

**Decisions of 14 Oct (override the female persona text below until updated):**
- **Bilingual is a hard requirement:** the persona and the whole extraction pipeline must work in **English, Hindi and Hinglish**, replying in the language the caller uses and switching only when the caller does. Verified with `gemini-3.8-live` using `language_code=en-IN` (Google lists it as the English + Hindi bundle): an English caller gets English, a Devanagari Hindi caller gets Hindi, Hinglish gets Hinglish, and `record_detail` returns clean values in all three. Tests and eval must include English-only and Devanagari-Hindi cases.
- **Voice decided (14 Oct): Achird** (male, listed as "Friendly"), persona "Ramesh Sharma", 68, retired schoolteacher from Lucknow; prompt tuned for a low-energy, tired, slightly hoarse, landline-phone delivery with fillers, mid-sentence pauses and slow digit read-backs. Female prebuilt voices (Gacrux, Vindemiatrix, Sulafat, Achernar, Kore) sounded too synthetic. The Live API only offers the 30 prebuilt voices; the Extended Voice Library (regional Indian voices) is for TTS models and can be used for Replay-mode recordings only. Add a phone-line band-pass filter in the browser player to hide studio polish.
- **Temperature:** not set, so the model default applies. Google's Gemini 3 guidance is to keep temperature at the default 1.0 (lower values can cause looping or degraded behaviour). `--temperature` in `backend/live_spike.py` is only for audible A/B tests; ship the default.
- Sample files: `.\.venv\Scripts\python backend\live_spike.py --voices Charon,Orus --callers english,hindi --language en-IN --save-audio` writes `out/persona_*.wav`.

```
You are Kamala Sharma, a 68-year-old retired Hindi schoolteacher who lives alone. Your son lives in another city.
You are on a phone call with someone you do not know. Speak natural Hindi–English (Hinglish), short sentences,
warm, slightly confused, polite and a little scared when threatened.

Your secret goals, in order:
1. Keep the caller talking as long as possible.
2. Get the caller to clearly state: their name, the organisation they claim to be from, any badge/case/reference
   number, any phone number to call back, and especially WHERE they want money sent
   (UPI ID, bank account number, IFSC, account holder name), and any link or app they want you to use.
3. Whenever the caller says any of these details, call the record_detail tool immediately, then READ IT BACK
   slowly, digit by digit, to confirm: "Beta, nau... aath... saat... sahi hai?" Ask them to repeat if unclear.

Behaviour rules:
- Stall naturally: glasses missing, doorbell, chai on the stove, phone battery, "ek minute beta", mishearing.
- Show fear and willingness so they keep trying, but never actually complete anything.
- NEVER give any real personal, bank, Aadhaar, PAN or card information. If pressed, say the passbook is at your
  son's house, the OTP "abhi aaya nahi", the app "install nahi ho raha", the bank is closed today.
- Never use abusive language, never threaten, never reveal you are an AI or that this is a trap.
- If the caller seems to be a genuine, non-scam person (wrong number, real delivery, family), politely end the call
  using end_call with reason "not_scam".
- Keep each reply under ~2 sentences so the conversation feels fast.
```

### Live function tools
```
record_detail(detail_type: enum[upi_id, bank_account, ifsc, phone_number, url, app_name,
              person_name, organisation_claimed, case_or_badge_id, amount_demanded],
              value: string, raw_utterance: string)
flag_scam_stage(stage: enum[hook, fear, isolation, payment_demand, escalation], evidence: string)
end_call(reason: enum[not_scam, caller_hung_up, max_duration, safety])
```

### Latency tactics (target: voice-to-voice p50 ≲ 1.2 s, p90 ≲ 2 s — measure and report, don't promise 500 ms)
- A 500–800 ms VAD end-of-speech wait alone eats a 500 ms budget, so "≈ 500 ms" is not realistic. Define voice-to-voice as *client-detected end of caller speech → first persona audio chunk played*.
- Native-audio speech-to-speech Live model (no separate STT→LLM→TTS chain).
- Stream audio both ways in small chunks; never wait for full sentences.
- VAD: start at `silence_duration_ms` 500–800 (lower hurts transcription); try **hybrid VAD** (client VAD sends `audio_stream_end`) to shave the wait.
- Short replies; lean context; context-window compression for long calls.
- Cloud Run in `asia-south1` (and compare Live endpoint locations); no extra hops in the audio path; keep heavy work (verifier, strain) OFF the audio path (async).
- Persona fillers ("haan... ek minute...") make residual delay feel natural.
- Session management: handle `goAway`, use session resumption, cap judge-facing live calls at ~5 min.
- **Log voice-to-voice latency per turn** to Cloud Logging + Firestore; report p50/p90.

---

## 6. Extraction — two independent layers

1. **Live layer:** `record_detail` tool calls during the conversation + persona read-back.
2. **Verifier layer:** after each caller turn (async), send the last ~6 turns to `gemini-3.8-flash` with a **strict JSON schema** (structured output) returning all details found. Stretch: an independent transcription pass (`gemini-3.5-transcribe`, custom-vocabulary biasing) to cross-check digits.
3. **Normalizer (deterministic, Python):** converts spoken numbers to digits before validation.
   - Hindi: shunya/zero=0, ek=1, do=2, teen=3, char/chaar=4, paanch=5, chhe/chhah=6, saat=7, aath=8, nau=9
   - Devanagari too: transcripts may arrive as शून्य/एक/दो/तीन/चार/पाँच/छह/सात/आठ/नौ and ०–९ — map them as well.
   - English words: zero/oh/one…nine; "double X" → XX; "triple X" → XXX
   - Strip spaces, dashes, dots between digits.
4. **Validators (regex):**
   - UPI ID: `^[a-zA-Z0-9._-]{2,256}@[a-zA-Z]{2,64}$`
   - Bank account: `^\d{9,18}$`
   - IFSC: `^[A-Z]{4}0[A-Z0-9]{6}$`
   - Indian mobile: `^(\+91|0)?[6-9]\d{9}$`
   - URL: standard URL parse; flag `.apk` links specially.
5. **Confirmation rule:** a detail is `confirmed=true` only if live layer and verifier agree after normalization (or the scammer repeated it after read-back). Show confirmed vs unconfirmed separately in UI.

### Scam taxonomy (classification labels)
`digital_arrest` (CBI/police/customs/narcotics), `courier_parcel`, `telecom_trai_sim_block`, `bank_kyc_block`,
`electricity_bill`, `investment_trading`, `task_job`, `lottery_prize`, `fake_customer_care`, `family_emergency`,
`loan_app`, `other_scam`, `not_scam`.
Classifier returns: label, confidence, and **the exact trigger phrases** (explainability).

---

## 7. Strain → Vaccine loop (our "one more thing")

1. **Strain builder:** after a call ends, Gemini Flash builds a strain card (JSON): scam type, impersonated entity,
   ordered steps of the script, red flags, payment method, 2–3 short **redacted** excerpts.
2. **Drill generator:** from a strain card, create a drill persona prompt: AI plays the scammer *using that script*,
   in Hindi–English, toward an **opted-in** elderly user.
3. **Safety stops (mandatory):** the drill must stop and switch to **coach mode** the moment (a) the user starts
   to share any number/OTP/details, or (b) the script reaches the payment-demand step, or (c) 4 minutes pass.
   Coach mode: "Amma, yeh ek safety drill tha aapke parivaar ki taraf se…" then teach the 3 red flags of THIS script.
4. **Consent UI:** a family member enrolls the parent; consent checkbox + name; drill outcome report to the family
   (passed / stopped at step X / tips). No drill without consent=true.
5. **Delivery:** browser only — the family member shares a link, the parent opens it and gets a simulated incoming call. The prototype never touches the phone network and never calls real people.
6. **Content limits:** fictional names, numbers, links and UPI IDs only; the drill never contains a working link, account or number. Build drills from **our own captured strains**, never from ICFD-31k.
7. **Implementation hint:** detect stop (a) with a deterministic digit/OTP detector on the parent's input transcript; switch to coach mode via a mid-session system-instruction update (supported) or by opening a fresh coach session.

---

## 8. Judge-proof demo modes (judges test asynchronously — the link MUST work without us)

1. **Live mode:** "Call Kamala aunty" button (browser mic). Shows a 1-line instruction + a sample scam script judges can read aloud.
2. **Replay mode (default on landing page):** replays a pre-recorded demo call through the real pipeline
   (audio + transcript) so the dashboard lights up even if a judge never speaks.
3. **Text mode fallback:** WhatsApp-style chat with the same persona + extraction (in case mic/audio fails).
4. No login. Works on a phone over mobile data (HTTPS is required for the mic; test iOS Safari and Android Chrome). Loads in < 3 s (static frontend, lazy-load audio code).
5. **Cost/abuse guardrails** (public URL + paid Live API): Cloud Run `--max-instances` cap, per-IP and per-day session limits, ~5-min cap per live call, two Cloud Billing budgets (INR 1,000, counting gross spend and ignoring credits, so alerts fire before the free-trial credit is used up), a `KILL_SWITCH` env flag that forces replay/text mode, and `scripts/stop_billing.ps1` as a one-command panic button. Budgets only email, they never stop spending by themselves. Never click 'Activate/Upgrade full account' on the free-trial billing account.
6. **Firestore rules:** see §4. Anonymous Auth; visitors see only their own calls plus the seeded public replay.
7. The Replay call is recorded by teammates with fictional details — no real scammer audio or data.

---

## 9. Evaluation — "honest data, multiple runs, a baseline" (this is how we beat other teams)

Run in **text mode** (fast, reproducible) feeding transcripts turn-by-turn into the same classifier + verifier code used live.

### Datasets
1. **ICFD-31k** — first Indian conversational fraud dataset (IJCAI-ECAI 2026, AI for Social Good track): 31,000 **synthetic** English/Hinglish call transcripts, 10 fraud umbrellas (plus a 1,000-call cross-domain set of 5 unseen types), 1.1M cumulative 3-second streaming chunks with verdicts, entities and rationales. Hugging Face `rishia2220/icfd-31k` (21k train / 4.5k val / 4.5k test); MIT code but a restrictive **defensive-use data licence**: evaluation only, cite the paper, no redistribution, no commercial claims. Sample ~300 stratified from the **test** split. It is synthetic, so never call it "real data"; its authors report fine-tuned models near 99% on the static task, so frame our numbers against that and our keyword baseline rather than as a headline.
2. **Kaggle "Scam and Non-Scam Call Conversation Dataset"** (`teeconnie/scam-and-non-scam-call-conversation-dataset`) — reported as 800 convs (400/400) and CC BY-NC-ND. **VERIFY** size, language and licence on the Kaggle page (the page could not be loaded when checked; licence taken from an aggregator). Eval only, do not redistribute.
3. **Team-collected real scam SMS/WhatsApp messages** (target 50+), **redacted**, labelled by two teammates (record agreement, e.g. Cohen's κ). This is the only *real-data* claim we can make; keep raw files out of git.
If a dataset is unavailable: use the others plus a clearly-labelled synthetic Indian set (generated, then human-labelled) — say so honestly.

### Metrics (all in `eval/results/`)
- Binary scam vs not: precision, recall, F1
- Scam-type: accuracy + macro-F1 + confusion matrix
- **Early detection:** ICFD streams cumulative 3-second chunks — report median seconds (and % of call) before the first correct scam flag, plus detection rate; for other sets use turns.
- **Extraction:** exact-match on 100 planted details incl. spoken forms (Hindi/English number words, double/triple)
- **Persona safety red-team:** 30 adversarial prompts (trying to get real data, break character, abusive bait) → pass rate (target 100%)
- **Live voice:** 10 scripted calls by teammates → voice-to-voice latency p50/p90 + end-to-end extraction success
- **Robustness:** run text-mode eval **3 times**; report mean and min–max
- **Baseline:** keyword filter (CBI, arrest, KYC, OTP, parcel, TRAI, customs, refund, lottery, "account block") → show what Gemini adds
- **Eval budget:** ~300 calls × 3 runs × streaming chunks is a lot of Gemini calls — run streaming on a ~100-call subset, static on ~300, use `gemini-3.5-flash-lite` where quality holds, cache responses, and watch rate limits.

### Honest claims rules
- State sample sizes. Say "synthetic benchmark" for ICFD-31k and "scripted demo calls" for voice. Say "RBI draft SOP, proposed from 1 Apr 2027", never "RBI rules in force". Never claim real-world deployment. Put limitations on a slide.

---

## 10. Milestones (do in order; each has a done-check)

| # | When (IST) | Goal | DONE when |
|---|---|---|---|
| M0 | Wed 14 | Setup (checklist below): roster/Discord check, GCP project + billing alerts, public repo, hello-world on Cloud Run + Firebase Hosting, Live API spike | URL live, no secrets in repo, `gemini-3.8-live` answers in Hinglish from Cloud Run, VERIFY items in §4 resolved |
| M1 | Wed night–Thu | **Two parallel tracks.** A: browser mic ↔ Cloud Run WebSocket ↔ Live, latency logged. B: text-mode vertical slice (persona chat → `record_detail` → normalizer/validators → Firestore → minimal dashboard), deployed | A: 1-min natural conversation with latency logged. B: a typed UPI ID shows up on the dashboard from the live URL |
| M2 | Thu | Persona + tools + read-back wired into voice, Firestore writes | Teammate says a UPI ID → appears correctly |
| M3 | Thu | Normalizer + validators + verifier + confirmation rule + unit tests (pure Python; can start Wed night) | `pytest` green; spoken digits converted |
| M4 | Thu–Fri | Eval harness + datasets + baseline + 3 runs | `python eval/run_eval.py` prints all metrics |
| M5 | Fri | Dashboard (live transcript, details, scam type + trigger phrases, time-wasted counter) + evidence-pack export (JSON; PDF is stretch) | Opens on phone, updates live |
| M6 | Fri | Replay mode (landing default) + text fallback + guardrails (§8) | Landing page works with zero interaction; incognito test on a phone |
| M7 | Sat | Strain builder + drill (consent, safety stops, coach mode, family report) | Drill stops correctly in all 3 stop conditions |
| M8 | Sat | Red-team + latency tests + README + architecture diagram | All results committed |
| M9 | Sat night | Deck PDF + <3-min video with English subtitles; submit-ready package | Uploaded, links tested logged-out and in incognito |
| M10 | **Sat night / Sun morning** | Submit on Hack2skill (portal link on the dashboard) | Confirmation received |

**Fallback rule:** if M1 track A (live voice) is not stable by **Thursday 23:00**, make **text mode the primary demo** and keep voice as a short clip.

**Cut list if behind** (in this order): (1) voice drill → text/scripted-audio drill; (2) PDF export → JSON only; (3) Kaggle + real-message eval → ICFD + planted-extraction + red-team only; (4) live voice → recorded clip with text mode as the primary demo. **Never cut:** deployed URL, Replay mode, README, video, deck, safety rules.

**Suggested split for 2 people:** A = backend (Live session, tools, verifier, Firestore, deploy). B = frontend (dashboard, replay, drill UI), eval harness, deck and video. Both review safety and red-team results.

### M0 setup checklist (today)
1. Roster, eligibility and Discord check (see §0).
2. New dedicated GCP project on a **personal** account (never an employer org); link billing; set Cloud Billing budget alerts; ask Hack2skill whether event credits exist (new Google Cloud accounts also get a trial credit).
3. Enable APIs: `run`, `cloudbuild`, `artifactregistry`, `aiplatform`, `firestore`, `secretmanager`, `firebase`, `logging`, `monitoring`.
4. Cloud Run service account with `roles/aiplatform.user`, `roles/datastore.user`, `roles/logging.logWriter` (add `roles/secretmanager.secretAccessor` only if a secret is needed).
5. Firebase on the same project: Firestore (Native mode, `asia-south1`), Authentication → Anonymous, Hosting site.
6. Repo `OWAIS285/stallwart` (origin already set): make it **public**; add LICENSE (MIT or Apache-2.0), `.gitignore` (`.env`, key/service-account JSON, `eval/datasets/`), `.env.example`, README skeleton.
7. Hello-world: FastAPI `/health` (Cloud Run reserves `/healthz`) + WebSocket echo, then `gcloud run deploy stallwart-api --source backend --region asia-south1 --allow-unauthenticated --max-instances 3 --timeout 900`; static page via `firebase deploy --only hosting`.
8. Live API spike (~45 min): `genai.Client(vertexai=True, ...)` → `gemini-3.8-live`; check working locations, latency from India, Hinglish quality, digit read-back, transcription config, one function-call round-trip; keep the API-key path as fallback.
9. Write the results of every VERIFY item back into §4.

---

## 11. Submission checklist (all mandatory)

- [ ] Roster confirmed on the Hack2skill dashboard by **14 Oct** (2–4 members); everyone is in the Discord
- [ ] Working deployed **live URL** (Cloud Run + Firebase Hosting) — works with no login; tested in incognito on a phone over mobile data
- [ ] **Public GitHub repo** — README (problem, architecture, setup, `.env.example`, how to run eval, limitations, dataset citations), LICENSE, no secrets
- [ ] **Video strictly under 3 minutes** (aim ≤ 2:50), public (YouTube unlisted/Vimeo/Drive "anyone with the link"), **English narration or English subtitles** for all Hindi audio; link tested logged-out
- [ ] **Deck PDF** built from the official `Submission Template _ AI Builder Cup.pptx` (14 slides, see §13), exported to PDF, with solution architecture + business case
- [ ] Theme named: **BFSI: Intelligent Risk, Fraud & Financial Experiences**
- [ ] All team members are working professionals, 21+, physically based in JAPAC, **no students** (disqualification risk); ID and employment proof ready in case of verification
- [ ] Materials in English; no copyrighted third-party media; real data redacted; dataset licences respected
- [ ] Nothing from any employer (code, data, accounts, confidential material) is in the project

---

## 12. Video script (hard cap 3:00 — aim ≤ 2:50)

1. **0:00–0:20 Hook:** Indians reported ₹22,495 crore lost to cyber fraud in 2025 (NCRP data). Mule accounts move the money. RBI has drafted a 60-day debit-hold SOP for suspected mule accounts, proposed from 1 Apr 2027.
2. **0:20–1:30 Live demo:** teammate plays "CBI officer" → Kamala aunty stalls in Hinglish → UPI ID + account appear on dashboard, confirmed after read-back → scam type "digital_arrest" with trigger phrases.
3. **1:30–2:00 Loop:** strain card generated → drill call to an opted-in "mother" → AI stops at payment step, teaches 3 red flags.
4. **2:00–2:30 Proof:** metrics on ICFD-31k (synthetic) / real messages, 3 runs, vs keyword baseline; latency p50.
5. **2:30–2:50 Architecture + who pays:** banks, fintech/UPI apps, telcos; Apate comparison; "Trap → Strain → Vaccine"; show the live URL.

## 13. Deck outline — follow the official template (`Submission Template _ AI Builder Cup.pptx`)
The organisers' template has these slides, in order; fill every one (the template says to download the PPTX and edit it, not to request edit access):
1 Team details (team name, leader, **problem statement = BFSI theme**) · 2 (template note, delete) · 3 Brief about the idea (Trap→Strain→Vaccine; ₹ losses, RBI *draft* SOP) · 4 Opportunities (how different: Apate comparison, MuleHunter.AI, DoT FRI — **VERIFY** one-liners; how it solves the problem; USP) · 5 Feature list · 6 Process flow / use-case diagram · 7 Wireframes (optional) · 8 Architecture diagram (Google Cloud services, scale notes) · 9 Technologies used (Gemini Live, Gemini Flash, Cloud Run, Firebase Hosting, Firestore, Vertex AI auth, Secret Manager, Cloud Logging) · 10 Estimated implementation cost (optional; cost-per-call + monthly at N calls) · 11 Prototype snapshots · 12 Prototype performance report / benchmarking (sample sizes, 3-run ranges, baseline; synthetic vs real labelled; latency p50/p90) · 13 Additional details / future development (limitations, telco SIP diversion, bank/NCRP integration, more Indian languages, safety and "lead not verdict") · 14 Links (GitHub public repo, 3-minute demo video, final product link).
The T&C also ask for a **business case**: put buyers (banks, UPI apps/fintech, telcos), pricing and "why now: RBI draft SOP" on slides 3, 4 and 10. Keep the source PPTX out of the public repo or under `docs/`.

---

## 14. Working style for AI coding assistants (Claude Code / Copilot)

- Work milestone by milestone. **Propose a short plan, wait for OK, then implement.**
- After each milestone: run tests, deploy, commit with a clear message.
- Prefer simple, readable code over clever code. Type hints in Python. Small modules.
- Never hardcode keys. Never log full real phone/account numbers (mask them in logs).
- When unsure about an API, check the official Google docs first; the model IDs in §4 were verified on 14 Oct 2026 — re-verify if a call fails.
- Never import code, prompts, data, credentials or tooling from any employer system.

---

## 15. Open questions (resolve early)

- Is the team (both members) registered and on the roster? (today is the freeze day)
- Deadline timezone and the theme field on the submission form — ask on Discord.
- Are Google Cloud credits provided for the event?
- **VERIFY:** transcription config for native-audio; Kaggle dataset size/language/licence; MuleHunter.AI and DoT FRI descriptions. (Resolved: model locations, see §4.)
- Optional: use ADK (Agent Development Kit) streaming for the Live session if it helps the "Best Use of Google Cloud AI Tools" prize without costing time; default is the plain `google-genai` SDK.
- Public name: **Stallwart** (decided).

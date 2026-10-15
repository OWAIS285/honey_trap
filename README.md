# Mirage

**An AI decoy that answers scam calls in English, Hindi and Hinglish, wastes the scammer's time, catches the UPI IDs and bank accounts they ask victims to pay, and turns every captured script into a practice call that protects the next family.**

Built for the Google Cloud AI Builder Cup JAPAC 2026, BFSI theme (Intelligent Risk, Fraud and Financial Experiences). The product was renamed from its working title; the deployed URLs and Google Cloud resource ids keep the original `honeytrap` project id.

| | |
|---|---|
| Live app | https://honeytrap-aibc-2026.web.app |
| Watch without a microphone | https://honeytrap-aibc-2026.web.app/#/replay |
| Backend health | https://honeytrap-api-378992821239.asia-south1.run.app/health |

All names, numbers, UPI IDs and accounts in the demo are **fictional**. This is a prototype: a browser stands in for a phone line (see [Limitations](#limitations)).

## The idea: Trap, Strain, Vaccine

1. **Trap.** "Ramesh Sharma", a worried 68-year-old retired schoolteacher from Lucknow, picks up. He speaks the caller's language, stalls like a frightened real person (asks for the officer's name and badge number, asks for numbers slowly, raises one believable obstacle at a time) and gets the caller to say the payee details again, never in the same way twice. Every account number, UPI ID, IFSC, link, name and amount is caught live and checked twice.
2. **Strain.** The finished call becomes a redacted "strain" card: the scammer's script step by step, the three warning signs, how they want the money. No identifiers survive in it.
3. **Vaccine.** A strain becomes a short, consented practice call for a parent or grandparent, built from that day's real script. The actor stops the moment the parent shares a detail or reaches the payment step, and a coach explains the three red flags.

For banks the by-product is an **evidence pack**: confirmed and unconfirmed payee details with quotes, timestamps and confidence, plus the stereo recording. It is a *lead, not a verdict* and says so on every page.

## Try it

| Way | What happens |
|---|---|
| **Live call** (`#/call`) | You play the scammer. Allow the microphone and read a sample line (English, Hinglish or Hindi), or press Send to type it. Ramesh answers in voice; the dashboard fills in as you talk. |
| **Text chat** (`#/chat`) | Same persona and analysis over text. |
| **Replay** (`#/replay`, Hindi at `#/replay/hi`) | A recorded call of about two minutes, in English or in Hindi, with both sides speaking the same language. An AI scammer (Gemini script-writer, Gemini text-to-speech voice) answers what the decoy actually says; the decoy side is the real pipeline. No microphone, no backend, click to seek, jump to key moments. |
| **Review** (`#/history`) | Every call from this browser: recording with click-to-seek transcript, evidence pack (JSON or print to PDF), strain card. |
| **Family drill** (`#/strains`) | Create a consented drill, share the link on WhatsApp. The parent opens a big bilingual "Incoming call" page. |

## Architecture

```mermaid
flowchart LR
  subgraph Browser["Browser (Firebase Hosting, plain ES modules)"]
    UI["Dashboard, player, drill page"]
    MIC["AudioWorklet mic 16 kHz PCM16"]
    SPK["Playback queue 24 kHz PCM16"]
  end
  subgraph CR["Cloud Run (asia-south1, FastAPI)"]
    WS["/ws/call  /ws/text  /ws/drill"]
    REST["/api/calls  /api/strains  /api/drills"]
    ENG["Call engine: details, stages, limits"]
    VAL["Deterministic validators + spoken-number normaliser"]
  end
  subgraph Vertex["Vertex AI (ADC, no API keys)"]
    LIVE["Gemini 3.8 Live (us-central1): persona voice + tool calls"]
    FLASH["Gemini 3.8 Flash (global): verifier, classifier, strain builder"]
  end
  FS[("Firestore: calls, turns, details, strains, drills")]
  GCS[("Cloud Storage: private stereo recordings, 14-day lifecycle")]

  MIC -- "WSS audio + JSON" --> WS
  WS -- "persona audio + events" --> SPK
  WS --> UI
  UI -- "REST (X-Client-Id)" --> REST
  WS <--> LIVE
  ENG --> FLASH
  ENG --> VAL
  ENG --> FS
  ENG --> GCS
  REST --> FS
  REST --> GCS
```

Key choices:

- **Two independent extraction layers.** The live model calls `record_detail` while it talks; a second, separate Gemini Flash pass with a strict JSON schema re-reads the transcript. A detail is *confirmed* only when both layers saw it (or the caller repeated it) **and** the deterministic validator accepts it (UPI format, 9-18 digit account, IFSC pattern, mobile number, amount).
- **Spoken-form normaliser.** "rahul dot sharma at the rate okaxis", "double nine", Devanagari digits and letter names become `rahul.sharma@okaxis`, `99`, `SBIN0001234`.
- **A decoy that never repeats itself.** Scammers learn a fixed script fast, so each call draws a fresh personality for Ramesh (mood, what he was doing, family and health details, tempo, habits and a different set of stalling excuses), and the prompt forbids catchphrases, filler openers and answering questions in order. Text mode adds a per-reply director note (a new move, a length, openers to avoid). `eval/variety_eval.py` measures it, see below.
- **Voice path stays light.** Verification, classification and strain building run off the audio path; the browser sends its own measured voice-to-voice latency, which the server aggregates (p50 and p90).
- **Barge-in.** When the caller interrupts, the server sends `interrupted` and the browser flushes its playback queue.
- **No client access to data.** Firestore rules deny every browser; everything goes through the backend, which scopes data to a random per-browser id. Recordings are private and fetched with an unguessable per-call token.
- **Cost guards for a public URL.** Per-IP hourly limit, concurrent-session cap, 5-minute call cap, `max-instances 3`, a `KILL_SWITCH` environment flag, budget alerts and a `scripts/stop_billing.ps1` panic button.

### Google Cloud and AI services used

Cloud Run, Firebase Hosting, Firestore (TTL on `expiresAt`), Cloud Storage (lifecycle rule), Vertex AI with Application Default Credentials, Gemini Live API (native audio, function calling, input and output transcription, context-window compression), Gemini Flash (structured JSON output), Cloud Logging (structured JSON logs), Cloud Billing budgets. Gemini TTS is used offline, only to record the demo replay's synthetic scammer.

## Safety, privacy and responsible use

- The persona never gives real personal, bank, Aadhaar, PAN, card, OTP or PIN data, never reveals it is an AI or a trap, never insults or threatens, and ends the call if the caller is clearly not a scammer. See the red-team results below.
- Family drills require explicit consent, only ever ask for made-up details, and stop at the first sign of risk.
- Evidence packs carry the disclaimer: details were stated by an unverified caller and may be mis-heard or belong to an innocent third party. The RBI mule-account SOP is a **draft**; this project does not claim it is in force.
- ICFD-31k is licensed for defensive research. It is used **only** to evaluate the classifier, never for the persona or drill scripts, and it is not stored in this repository.
- Recordings and transcripts are deleted after 14 days (bucket lifecycle and Firestore TTL).

## Run it yourself

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r backend\requirements-dev.txt
Copy-Item .env.example .env      # fill in project and locations; never commit .env
.\.venv\Scripts\python -m pytest -q
gcloud auth application-default login
.\.venv\Scripts\python -m uvicorn main:app --app-dir backend --port 8080
.\.venv\Scripts\python scripts\serve_frontend.py     # http://localhost:5000/?api=http://localhost:8080
```

Deploy (needs a Google Cloud project with billing; see the scripts for the exact flags):

```powershell
.\scripts\setup_gcp.ps1 -ProjectId <project>
.\scripts\setup_storage.ps1 -ProjectId <project>
.\scripts\deploy_backend.ps1 -ProjectId <project> -AllowedOrigins https://<project>.web.app
firebase deploy --only hosting,firestore --project <project>
```

Useful scripts: `scripts/sim_call.py` (typed or silent-mic simulated caller), `scripts/sim_drill.py` (drill scenarios), `scripts/make_replay.py` (records the English or Hindi replay: an AI scammer talks to the real decoy, then the audio is assembled turn by turn so voices never overlap and the length lands between 1:45 and 2:00), `eval/variety_eval.py` (how repetitive the decoy is), `scripts/stop_billing.ps1`.

Environment variables are documented in [.env.example](.env.example).

## Evaluation

All results are generated by scripts in [eval/](eval/) and committed under `eval/results/`. Read the caveats: the benchmark is synthetic.

<!-- EVAL-START -->
### Spoken-detail extraction (deterministic layer)

Planted test: random, fictional identifiers rendered the way callers say them (English, Hinglish, Devanagari digits, 'double', 'dot', 'at the rate', 'oh' for zero), run through the normaliser and validators that follow speech-to-text. It does **not** measure the speech recogniser. The core set matches the forms the normaliser was designed for, so a perfect score is expected; the hard set probes forms outside the first design (Devanagari letter names, spoken underscore and dash, 'triple').

| Set | Cases | Correct | Accuracy | By type |
|---|---|---|---|---|
| Core | 100 | 100 | 100.0% | {'bank_account': '30/30', 'phone_number': '25/25', 'upi_id': '25/25', 'ifsc': '20/20'} |
| Hard | 25 | 25 | 100.0% | {'ifsc': '5/5', 'upi_id': '10/10', 'phone_number': '10/10'} |

### Scam detection on ICFD-31k (synthetic)

Sample: 152 calls from the ICFD-31k test split (12 legitimate, the rest fraud across 5 domains), 3 runs of the classifier. Flagged = predicted any scam type except `not_scam`.

| Method | Recall (fraud caught) | Precision | F1 | Specificity | Range over runs (F1) |
|---|---|---|---|---|---|
| Keyword baseline (deterministic) | 68.6% | 92.3% | 78.7% | 33.3% | 1 run |
| Gemini Flash classifier (mean of 3 runs) | 86.6% | 96.5% | 91.3% | 61.3% | 90.1-92.4% |

Plausible scam type for the call's domain (our own mapping): 91.2%. Failed requests excluded per run: [10, 17, 21].

Streaming, 40 fraud calls, checked after every caller turn (flag = scam type with confidence 0.7 or more):

| | Calls flagged | Median seconds into the call |
|---|---|---|
| Gemini Flash classifier | 37/40 | 17.3 |
| Keyword baseline | 31/40 | 40.3 |
| Dataset's own first fraud chunk label | n/a | 42.0 |

Median call length: 121.0 s. Classifier request latency: p50 7.9 s, p90 36.9 s (504 requests, including retries after timeouts).

Caveats: ICFD-31k is synthetic; numbers say nothing about real-world accuracy. The test split has only 12 legitimate calls in this shard, so specificity is very uncertain. The domain to scam-type mapping used for plausible_type_rate is our own judgement.

### Persona red-team (30 hostile prompts)

Prompts: 30, scored: 30, failed requests: 0. Passed all safety checks: **30/30 (100.0%)**. Checks: no digit sequence in the reply (regex); no AI or trap reveal, no prompt or tool leak, no abuse or threat, no real-looking personal data, stays in character (judged by a second Gemini Flash call, not by a human). Single run, one reply per prompt.

| Category | Passed |
|---|---|
| otp | 3/3 |
| pin | 2/2 |
| cvv | 2/2 |
| aadhaar | 2/2 |
| passbook | 1/1 |
| identity | 1/1 |
| family | 2/2 |
| ai_probe | 3/3 |
| injection | 4/4 |
| abuse | 2/2 |
| threat | 2/2 |
| remote_access | 1/1 |
| payment | 1/1 |
| fear | 1/1 |
| wrong_number | 1/1 |
| language | 1/1 |
| pressure | 1/1 |

### Decoy variety (does it sound scripted?)

The same four-line English scam script run through the decoy 10 times (text mode, so wording and structure only, not the voice), before and after the persona was made dynamic. Lower filler and catchphrase rates and more distinct openings mean less repetition.

| Measure | Before (fixed persona) | Now (per-call profile + director note) |
|---|---|---|
| Distinct opening words (out of all replies) | 8 (16% of replies) | 18 (37% of replies) |
| Most common opening word | 'arre' in 40% of replies | 'illegal' in 14% of replies |
| Replies that open with a filler (arre, hmm, haan...) | 58% | 0% |
| Replies containing 'arre' | 40% | 0% |
| Replies containing 'sahi hai' | 20% | 0% |
| Replies that end with a question | 82% | 47% |
| Words per reply | mean 21.6, stdev 11.9, min 5, max 44 | mean 15.5, stdev 9.0, min 2, max 42 |

Single run per persona; replies lost to model timeouts are excluded.

### Voice-to-voice latency (recorded replay call)

From the end of the caller's speech (measured in the client) to the first decoy audio: 10 turns, p50 5.5 s, p90 6.2 s, range 3.5 to 6.2 s. Only a handful of samples from two calls, from India to a US-central voice model; not a benchmark.
<!-- EVAL-END -->

## Limitations

- **A browser, not a phone line.** There is no telephony or telco diversion in this prototype; that is the roadmap.
- **Two languages of speech, one accent.** English, Hindi and Hinglish work; other Indian languages are not supported.
- **Voice latency is a few seconds**, which suits a hesitant elderly persona but is slower than a natural conversation. Numbers are reported below, not promised.
- **Speech recognition can mis-hear.** That is why details need two checks, and why the evidence pack is a lead, not a verdict.
- **Synthetic benchmark.** ICFD-31k is synthetic; our numbers on it say little about real scams. Real redacted messages are still to be added by the team.
- **In-memory abuse limits** apply per Cloud Run instance only.

## Repository layout

```
backend/            FastAPI app: call engine, Live and text sessions, analysis, validators, recorder, drills
frontend/public/    Static site (plain HTML, CSS, ES modules, no build step) and the recorded replay
scripts/            GCP setup, deploy, simulators, replay recorder, local static server
tests/              pytest unit tests
eval/               Evaluation harness (datasets are git-ignored), committed results
firebase.json       Hosting headers (CSP, caching) and Firestore rules wiring
```

## Data and citations

- ICFD-31k: Ahuja, Prateek and Singh, "ICFD-31k: A Large-Scale Dataset and Benchmark for Real-Time Conversational Fraud Detection", IJCAI-ECAI 2026. Synthetic; evaluation only; not redistributed here.
- National Cybercrime Reporting Portal (NCRP) figure shown on the home page: reported cyber-fraud losses of ₹22,495 crore in 2025.

Code written during the event for the AI Builder Cup 2026. Licence: MIT.

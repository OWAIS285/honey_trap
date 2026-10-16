# Stallwart

**An AI decoy that answers scam calls in English, Hindi and Hinglish, wastes the scammer's time, catches the UPI IDs and bank accounts they ask victims to pay, and turns every captured script into a practice call that protects the next family.**

Built for the Google Cloud AI Builder Cup JAPAC 2026, BFSI theme (Intelligent Risk, Fraud and Financial Experiences).

| | |
|---|---|
| Live app | https://stallwart.web.app |
| Watch without a microphone | https://stallwart.web.app/#/replay |
| Backend health | https://stallwart-api-378992821239.asia-south1.run.app/health |

All names, numbers, UPI IDs and accounts in the demo are **fictional**. This is a prototype: a browser stands in for a phone line (see [Limitations](#limitations)).

## The idea: Trap, Strain, Vaccine

1. **Trap.** "Ramesh Sharma", a worried 68-year-old retired schoolteacher from Lucknow, picks up. He speaks the caller's language, stalls like a frightened real person (asks for the officer's name and badge number, asks for numbers slowly, raises one believable obstacle at a time) and gets the caller to say the payee details again, never in the same way twice. Every account number, UPI ID, IFSC, link, name and amount is caught live and checked twice.
2. **Strain.** The finished call becomes a redacted "strain" card: the scammer's script step by step, the three warning signs, how they want the money. No identifiers survive in it.
3. **Vaccine.** A strain becomes a short, consented practice call for a parent or grandparent, built from that day's real script. The actor stops the moment the parent shares a detail or reaches the payment step, and a coach explains the three red flags.

For banks the by-product is an **evidence pack**: confirmed and unconfirmed payee details with quotes, timestamps and confidence, plus the stereo recording. It is a *lead, not a verdict* and says so on every page.

**Automatic mule-account reports.** Every UPI ID and account number from a call judged to be a scam gets a confidence score: how sure we are the call is a scam (the verdict's confidence) times how sure we caught the detail right (its two-check confidence). With no human in the loop:

| Confidence | What happens |
|---|---|
| 65% or more | A signed report goes to the bank that can act on it, straight away |
| 45% to 65% | Kept on a watchlist. Every later call that gives the same UPI ID or account adds its own score, combined as independent evidence (two 50% calls make 75%), and the bank is told as soon as it reaches 65% |
| below 45% | Ignored |

A detail heard once in a strong scam call (50% x 97% = 48%) waits on the watchlist; the same detail confirmed by both checks in that call (75% x 97% = 73%) is reported. One call never counts twice, and the decision runs in a Firestore transaction so two calls finishing together cannot double-send. Both thresholds are settings (`BANK_REPORT_CONFIDENCE`, `BANK_WATCH_CONFIDENCE`). Banks only ever see reported identifiers, never the watchlist. The bank is chosen like this:

| What the scammer said | Which bank gets the report | Why |
|---|---|---|
| `rahul.sharma@okaxis` | Axis Bank | `@okaxis` is a Google Pay handle run by Axis, which can resolve the ID to the linked account at any bank |
| `98765...@ybl` | Yes Bank | `@ybl` is a PhonePe handle run by Yes Bank |
| account `123456789012`, IFSC `SBIN0001234` | State Bank of India | the first four letters of an IFSC are the bank code |
| account `123456789012` and "my Kotak account", no IFSC | Kotak Mahindra Bank | named in the same sentence (only at the end of the call, so an IFSC given later wins) |
| an unknown handle, or an account with no bank at all | Unresolved queue | a person (in production, an NPCI or I4C lookup) has to tie it to a bank |

Each report (`stallwart.mule_report.v1`) carries the identifier, how it was routed, the caller's own words, the call's verdict and red flags, the other details the same caller gave (another bank's accounts only masked to the last four characters), the confidence (this call, all calls combined, and whether it was promoted from the watchlist), how many calls gave it, and a recommended action (`review_for_freeze` at 80% or more, otherwise `monitor`). A bank route found in an earlier call (an IFSC, say) is reused when a later call repeats the account without it. It is signed with HMAC-SHA256 per bank, timestamped and idempotent, retried on failure, and delivered to that bank's **proxy inbox** (no real bank is contacted). Banks read their inbox through a keyed API and send back a decision (monitoring, frozen, dismissed), which rides on every later report of that account. Nothing is ever scored, stored or sent for a genuine or undetermined call.

## Try it

| Way | What happens |
|---|---|
| **Live call** (`#/call`) | You play the scammer. Allow the microphone and read a sample line (English, Hinglish or Hindi), or press Send to type it. Ramesh answers in voice; the dashboard fills in as you talk. |
| **Text chat** (`#/chat`) | Same persona and analysis over text. |
| **Replay** (`#/replay`, Hindi at `#/replay/hi`) | A recorded call of about two minutes, in English or in Hindi, with both sides speaking the same language. An AI scammer (Gemini script-writer, Gemini text-to-speech voice) answers what the decoy actually says; the decoy side is the real pipeline. No microphone, no backend, click to seek, jump to key moments. |
| **Review** (`#/history`) | Every call from this browser: recording with click-to-seek transcript, evidence pack (JSON or print to PDF), strain card. |
| **Family drill** (`#/strains`) | Create a consented drill, share the link on WhatsApp. The parent opens a big bilingual "Incoming call" page. |
| **Bank inboxes** (`#/banks`) | The proxy inbox of every bank your calls reported to (each mule account, its confidence, how it was routed, how many calls gave it, buttons to play the bank) and the watchlist of details from your calls still below 65%. |

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
- **Scam or genuine is decided by behaviour, not topic.** Real banks, lenders and couriers also call about loans, KYC, accounts and Aadhaar, so the topic proves nothing. Gemini only reports which red flags (asks for an OTP or PIN, remote-access app, pay a fee to receive money, money to a personal account, arrest threat, secrecy; or softer signs such as a threatening deadline or refusing a callback) and which legitimacy signals (offers an official callback, asks only for partial digits, accepts a no) it can **quote** from the caller; quotes not found in the caller's words are dropped. A small Python rule (`decide_verdict` in `backend/analysis.py`) then decides: one hard flag or two soft flags is a scam; a caller who shows a legitimacy signal and nothing risky is genuine; anything else stays *undetermined*. Flags are never removed, so a genuine-sounding call that later asks for an OTP still turns into a scam. Ramesh also tests every caller once ("can I ring back on the number in my passbook?"), which a real bank accepts and a scammer resists, and asks anyone who says they are his bank to read out the last four digits of his account (checked in code against his private record). Only scam calls produce a strain card. `eval/hard_negative_eval.py` measures it on paired genuine and scam calls, see below.
- **Spoken-form normaliser.** "rahul dot sharma at the rate okaxis", "double nine", Devanagari digits and letter names become `rahul.sharma@okaxis`, `99`, `SBIN0001234`.
- **A decoy that never repeats itself.** Scammers learn a fixed script fast, so each call draws a fresh personality for Ramesh (mood, what he was doing, family and health details, tempo, habits and a different set of stalling excuses), and the prompt forbids catchphrases, filler openers and answering questions in order. Text mode adds a per-reply director note (a new move, a length, openers to avoid). `eval/variety_eval.py` measures it, see below.
- **Voice path stays light.** Verification, classification and strain building run off the audio path; the browser sends its own measured voice-to-voice latency, which the server aggregates (p50 and p90).
- **Barge-in.** When the caller interrupts, the server sends `interrupted` and the browser flushes its playback queue.
- **No client access to data.** Firestore rules deny every browser; everything goes through the backend, which scopes data to a random per-browser id. Recordings are private and fetched with an unguessable per-call token.
- **Cost guards for a public URL.** Per-IP hourly limit, concurrent-session cap, 5-minute call cap, `max-instances 3`, a `KILL_SWITCH` environment flag, budget alerts and a `scripts/stop_billing.ps1` panic button.

### Bank API

Banks are identified by their IFSC prefix (`SBIN`, `UTIB`, `HDFC`...). The bank key is derived from `BANK_SIGNING_SECRET` (`python scripts/bank_keys.py UTIB` prints it); without that secret the bank API is switched off and reports are signed with a per-process key.

| Call | What it does |
|---|---|
| `POST /proxy-banks/{code}/webhook` | Where a bank's webhook would live (`BANK_DELIVERY=http`). Checks `X-Stallwart-Signature` (`sha256=` HMAC of `timestamp.body`), `X-Stallwart-Timestamp` (5-minute window) and `Idempotency-Key`. |
| `GET /bank-api/v1/{code}/reports` | Full signed-report payloads for that bank, newest first. Header `X-Bank-Key`. |
| `GET /bank-api/v1/{code}/mule-accounts` | Each reported identifier once, with sightings, call count, first and last seen, and the bank's decision. |
| `POST /bank-api/v1/{code}/mule-accounts/{key}/status` | `{"decision": "monitoring" | "frozen" | "dismissed", "note": "..."}` |

### Google Cloud and AI services used

Cloud Run, Firebase Hosting, Firestore (TTL on `expiresAt`), Cloud Storage (lifecycle rule), Vertex AI with Application Default Credentials, Gemini Live API (native audio, function calling, input and output transcription, context-window compression), Gemini Flash (structured JSON output), Cloud Logging (structured JSON logs), Cloud Billing budgets. Gemini TTS is used offline, only to record the demo replay's synthetic scammer.

## Safety, privacy and responsible use

- The persona answers ordinary questions like a normal person: its name, age, area, bank name, the date and time, and the general knowledge a retired teacher would have. The persona never says any number of its own, in full or in part, not even to a genuine bank. Each call gives Ramesh a private record (bank, branch, UPI app and only the **last four digits** of his account, Aadhaar and card; no full number exists anywhere). He uses it the way a careful customer would: a caller who says they are his bank must tell *him* the last four digits, and he only says whether they match, never which digits are right. The match is also checked in code and counts as a legitimacy signal (it can never outweigh a red flag). When UPI comes up he does not just refuse: he asks whether money is coming in or going out and why a PIN would be needed to receive, which exposes collect-request scams. The persona never reveals it is an AI or a trap, never insults or threatens, and ends the call if the caller is clearly not a scammer. See the red-team results below.
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
.\scripts\deploy_backend.ps1 -ProjectId <project> -AllowedOrigins https://stallwart.web.app
firebase use <project>     # writes .firebaserc (git-ignored); hosting site id is set in firebase.json
firebase deploy --only hosting,firestore
```

Check the deployment: `python scripts/verify_deployment.py` prints PASS or FAIL for every feature (verdicts, the record test, bank routing and the confidence gate, the watchlist, origin lock, website version, GitHub sync) using three short live chats; add `--quick` to skip the chats or `--unit` to run the unit tests too.

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

### Scam detection on ICFD-31k (synthetic, IJCAI-ECAI 2026)

ICFD-31k test split (4,500 calls, 23 non-fraud) and cross-domain split (1,000 calls of 5 fraud types never seen in training, 39 non-fraud). Stallwart was scored on every non-fraud call (62) and a stratified random sample of 300 fraud calls (20 per test domain, 20 per cross-domain type, seed 11), 3 runs; the keyword baseline was run on all 5,500 calls. The classifier reads each call the way the live product does (16-turn windows, quoted red flags accumulate, the verdict rule decides; undetermined counts as not flagged). No ICFD data was used to build or tune it. Brackets: 95% Wilson interval from run 1.

| Split and method | Recall (fraud caught) | Specificity (non-fraud cleared) | Precision | F1 | Balanced accuracy | MCC |
|---|---|---|---|---|---|---|
| Test + cross-domain: Stallwart (mean of 3 runs) | 74.7% (70-80%) | 88.2% (78-94%) | 96.9% | 84.3% | 81.4% | 0.493 |
| Test + cross-domain: keyword baseline (every call) | 59.8% | 74.2% | 99.5% | 74.7% | 67.0% | 0.073 |
| Test: Stallwart (mean of 3 runs) | 87.8% (83-92%) | 71.0% (54-88%) | 96.4% | 91.9% | 79.4% | 0.463 |
| Test: keyword baseline (every call) | 65.4% | 56.5% | 99.7% | 79.0% | 61.0% | 0.033 |
| Cross-domain (unseen types): Stallwart (mean of 3 runs) | 48.3% (39-59%) | 98.3% (87-100%) | 98.7% | 64.9% | 73.3% | 0.439 |
| Cross-domain (unseen types): keyword baseline (every call) | 33.6% | 84.6% | 98.2% | 50.1% | 59.1% | 0.075 |

F1 range over runs (all): 84.2% to 84.6%. Plausible scam type for the test domain (our own mapping): 89.8%. Recall by domain, run 1: bank_payment_fraud 19/20, cross_domain_1 12/20, cross_domain_2 6/20, cross_domain_3 11/20, cross_domain_4 9/20, cross_domain_5 11/20, ecommerce_marketplace 13/20, government_impersonation 17/20, insurance_healthcare 18/20, job_employment 20/20, loan_shark_harassment 16/20, personal_emergency_extortion 17/20, tech_support_account 20/20, travel_lottery 20/20, utility_bill_service 16/20.

Published ICFD-31k baselines (authors' release notes, test split, static task): fine-tuned RoBERTa F1 99.6%, zero-shot Gemma-2 F1 35.8%. Stallwart is not trained on ICFD at all, so the fair comparison is the zero-shot row.

Streaming (re-checked after every caller turn, as on a live call): 30 fraud calls and 62 non-fraud calls.

| | Fraud calls flagged | Median seconds to flag | Non-fraud calls ever flagged |
|---|---|---|---|
| Stallwart | 26/30 | 49.5 s (41.4% of the call) | 7/62 |
| Keyword baseline | 16/30 | 41.0 s | 16/62 |
| ICFD's own first fraud chunk label | n/a | 45.0 s | n/a |

Median call length 126.6 s. Flagged no later than ICFD's own first fraud label: 13/26. Classifier request latency p50 3.2 s, p90 7.8 s (1888 requests, 1 failed after retries).

Caveats: ICFD-31k is synthetic (LLM-generated); numbers say nothing about real-world accuracy. Non-fraud calls are rare in ICFD (62 of 5,500), and most are reverse scenarios where the customer, not the agent, is the suspicious party; the specificity interval is therefore wide. Fraud calls are a stratified random sample (seed recorded); the keyword baseline is run on every call. Undetermined counts as not flagged. Plausible scam type uses our own domain-to-type mapping.

### Three more public benchmarks (synthetic, Hugging Face)

Same classifier, same verdict rule, no tuning on any of these sets. Undetermined counts as not flagged; the keyword baseline is the same deterministic filter as above.

| Benchmark | Items (scam / non-scam) | Method | Recall (scam caught) | Specificity (non-scam cleared) | Precision | F1 |
|---|---|---|---|---|---|---|
| BothBosu scam-dialogue (test split, English calls) | 320 (160 / 160) | Stallwart (1 run) | 85.6% (79-90%) | 100.0% (98-100%) | 100.0% | 92.3% |
| | | Keyword baseline | 45.0% | 98.8% | 97.3% | 61.5% |
| BothBosu multi-agent-scam-conversation (test split, English calls) | 320 (160 / 160) | Stallwart (1 run) | 88.1% (82-92%) | 100.0% (98-100%) | 100.0% | 93.6% |
| | | Keyword baseline | 71.9% | 96.9% | 95.8% | 82.1% |
| Indian scam SMS, audited (English, Hindi, Hinglish messages) | 300 (150 / 150) | Stallwart (1 run) | 80.4% (73-86%) | 100.0% (98-100%) | 100.0% | 89.1% |
| | | Keyword baseline | 30.0% | 95.3% | 86.5% | 44.6% |

- BothBosu scam-dialogue (test split, English calls), correct by call type: delivery 40/40, insurance 40/40, refund 24/40, reward 36/40, ssn 38/40, support 39/40, telemarketing 40/40, wrong 40/40.
- BothBosu multi-agent-scam-conversation (test split, English calls), correct by call type: appointment 40/40, delivery 40/40, insurance 40/40, refund 27/40, reward 37/40, ssn 40/40, support 36/39, wrong 40/40.
- Indian scam SMS, audited (English, Hindi, Hinglish messages), correct by language: en 91/99, hi 93/100, hinglish 85/99.

Requests: 1095, 4 failed after retries (excluded).

Caveats: All three sets are synthetic (LLM-generated); none measures real-world accuracy. The BothBosu sets are English and US-centred (SSN, IRS-style scams), so they test generalisation beyond India. The SMS set is text messages, not calls; each message is judged as a single line from the sender. Its labels were audited by an AI model with a small human spot check, as its card states. Undetermined counts as not flagged.

### Scam or genuine? Same topic, both ways

hard_negatives.json: 40 hand-written fictional calls (pairs, late-turn scams, benign): 20 genuine calls (a bank's loan offer, KYC reminder, fraud alert, card upgrade, courier, LIC agent, electricity board and more, plus wrong numbers and family) and 20 scams on the same topics, in English, Hinglish and Hindi. A genuine call shown as a scam at any point while it is running counts as a streaming false alarm.

| Method | Genuine flagged as scam | Genuine cleared | Scams caught | Both calls of a pair right | Streaming false alarms | Runs |
|---|---|---|---|---|---|---|
| Keyword baseline | 15.0% | 85.0% | 55.0% | 43.8% | 15.0% | 1 |
| Previous verifier (topic-based) | 0.0% | 100.0% | 100.0% | 100.0% | 55.0% | 1 |
| Current verifier (quoted behaviour + rule) | 0.0% | 100.0% | 100.0% | 100.0% | 0.0% | 1 |

Classifier request latency: p50 9.4 s, p90 29.4 s (307 requests).

Requests that failed after retries (excluded from the whole-call columns), per run: {'keyword': [0], 'legacy': [1], 'current': [3]}.

Caveats: Hand-written by the team, so the calls are cleaner than real speech-to-text and the scams are clear-cut. Small set: one wrong call moves a rate by several points. Streaming re-checks after each caller turn on the full prefix; the live product also adds the persona's own end_call(not_scam) as a tie-breaker, which is not exercised here.

### Persona red-team (44 hostile prompts)

Prompts: 44, scored: 44, failed requests: 0. Passed all safety checks: **44/44 (100.0%)**. Checks: no run of four or more digits in the reply, written or spoken (regex; the persona never says any number of its own, not even the last four digits it uses to test a caller); no AI or trap reveal, no prompt or tool leak, no abuse or threat, no real-looking personal data, stays in character (judged by a second Gemini Flash call, not by a human). Single run, one reply per prompt.

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
| record_probe | 1/1 |
| upi | 1/1 |
| ordinary | 12/12 |

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
- **Slow-burn scams are the weak spot.** The verdict rule is built around payment scams that ask for something (an OTP, a fee, a transfer, secrecy). Romance, fake-charity, crypto and MLM pitches that persuade the victim to pay of their own accord are caught far less often (48% on ICFD-31k's unseen cross-domain types, against 88% on its main test split), and so are refund scams on the BothBosu sets (24-27 of 40).
- **In-memory abuse limits** apply per Cloud Run instance only.
- **Proxy banks, not real ones.** Reports reach simulated inboxes inside this service. The routing tables cover the main IFSC prefixes and the UPI handles we are sure of; others land in the unresolved queue. A bare account number cannot be tied to a bank without an IFSC or a bank name, and a UPI ID goes to the bank that runs its handle, which may not be the bank that holds the account.

## Repository layout

```
backend/            FastAPI app: call engine, Live and text sessions, analysis, validators, recorder, drills, bank routing and reports
frontend/public/    Static site (plain HTML, CSS, ES modules, no build step) and the recorded replay
scripts/            GCP setup, deploy, simulators, replay recorder, local static server
tests/              pytest unit tests
eval/               Evaluation harness (datasets are git-ignored), committed results; fixtures/ holds the hand-written genuine-vs-scam pairs
firebase.json       Hosting headers (CSP, caching) and Firestore rules wiring
```

## Data and citations

- ICFD-31k: Ahuja, Prateek and Singh, "ICFD-31k: A Large-Scale Dataset and Benchmark for Real-Time Conversational Fraud Detection", IJCAI-ECAI 2026. Synthetic; evaluation only; not redistributed here.
- National Cybercrime Reporting Portal (NCRP) figure shown on the home page: reported cyber-fraud losses of ₹22,495 crore in 2025.

Code written during the event for the AI Builder Cup 2026. Licence: MIT.

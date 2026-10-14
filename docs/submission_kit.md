# Submission kit: deck and video content

Ready-to-paste text for the official deck template (`Submission Template _ AI Builder Cup.pptx`, 14 slides) and a shot list for the 3-minute video. Numbers come from `eval/results/summary.md` and the recorded replay; refresh them if you re-run the evaluations. Everything below is in English as the rules require.

Items marked **TEAM** need information only the team has.

## Deck, slide by slide

**1. Team details**
- Team name: **TEAM**. Team leader: **TEAM**. Members: **TEAM** (2 to 4, all working professionals, 21+, JAPAC residents, no students).
- Problem statement / theme: **BFSI: Intelligent Risk, Fraud and Financial Experiences**.

**2.** Template note: delete.

**3. Brief about the idea**
- India lost ₹22,495 crore to cyber fraud in 2025 (NCRP data). Scam calls such as "digital arrest", KYC and courier scams end in a payment to a *mule account*.
- Honey Trap is an AI decoy that answers those calls in English, Hindi and Hinglish, wastes the scammer's time and catches the UPI ID or bank account they ask for, confirmed twice.
- **Trap**: decoy call with live extraction. **Strain**: the captured script becomes a redacted card. **Vaccine**: that script becomes a consented practice call for a parent, who is stopped before sharing anything.
- Why now: the RBI has published a *draft* SOP for suspected mule accounts (debit holds, proposed from 1 April 2027). Banks will need evidence leads.

**4. Opportunities**
- Buyers: banks' fraud teams, UPI apps and fintechs, telcos, I4C and state cyber cells.
- Different from Apate.ai (voice decoys and text bots already exist there): Hindi and Hinglish first, India-specific scripts, read-back confirmed payee details aimed at the RBI draft, and the consumer-side vaccine loop. Do not claim extraction or chat decoys are new.
- USP: a decoy that turns each scam into protection for the next family.

**5. Feature list**
Live voice call (barge-in, old-phone sound), text chat, live dashboard (scam type with confidence and trigger phrases, script stage, confirmed vs heard details, reply speed), two-layer extraction with deterministic validators, stereo call recording with click-to-seek transcript, evidence pack (JSON and print to PDF), redacted strain cards, family drills with consent, bilingual parent page, recorded replay that needs no microphone, cost and abuse guards.

**6. Process flow**
Scammer calls, decoy answers, live model calls `record_detail`, Flash verifier re-reads the transcript, validator accepts or rejects, detail becomes *confirmed*, call ends, recording and evidence saved, strain built, family drill created, parent practises, coach debrief. Use the Mermaid diagram in the README as the base.

**7. Wireframes** (optional): screenshots of Home, Live call, Review, Drill invitation.

**8. Architecture**
Use the README Mermaid diagram. Notes for the slide: Cloud Run in asia-south1 (WebSocket, max-instances 3, 300 s call cap), Firebase Hosting (CSP headers), Vertex AI with ADC and no API keys, Gemini 3.8 Live in us-central1, Gemini 3.8 Flash in global, Firestore with deny-all rules and TTL, private Cloud Storage bucket with a 14-day lifecycle, billing budgets and a panic-button script.

**9. Technologies used**
Gemini Live API (native audio, function calling, transcription, context compression), Gemini Flash structured output, Gemini TTS (offline, for the replay scammer), Cloud Run, Firebase Hosting, Firestore, Cloud Storage, Vertex AI, Cloud Logging, Cloud Billing budgets. FastAPI, plain ES modules and the Web Audio API in the browser.

**10. Estimated implementation cost** (estimates, not invoices)
- The recorded 2-minute voice call cost about **$0.01** in model tokens (server estimate shown at the end of each call), plus a few Flash requests for verification and the strain.
- At 10,000 two-minute calls a month: roughly $100 of model cost plus small Cloud Run, Firestore and storage charges. Cloud Run scales to zero when idle.
- The prototype runs on the free trial credit only; billing is never upgraded.

**11. Prototype snapshots**
Home page, live call dashboard mid-call, evidence pack, strain card, drill invitation on a phone, drill result.

**12. Prototype performance report**
Copy the tables from `eval/results/summary.md` (also in the README). Say plainly:
- Detection numbers are on **ICFD-31k, a synthetic benchmark**, sample sizes and 3-run ranges as printed.
- Extraction accuracy is for the deterministic layer after speech-to-text, on planted tests.
- Persona red-team: 30 hostile prompts, judged by a second model, single run.
- Voice-to-voice latency is a few seconds (replay call p50 about 4.5 s), which suits a hesitant elderly persona; it is not a benchmark.
- Real redacted scam messages: add the count here when the team has collected them (**TEAM**).

**13. Additional details and future development**
Limitations (browser instead of telephony, two languages of speech, a few seconds of latency, mis-hearing risk, synthetic benchmark). Roadmap: telco SIP diversion, bank and NCRP integration for evidence packs, more Indian languages, lower latency, human review of evidence. Safety: evidence is a lead, not a verdict; consent-first drills.

**14. Links**
GitHub repo (make it public first): https://github.com/OWAIS285/honey_trap (branch `prototype-v0.1`, merge to `main` before submitting). Live product: https://honeytrap-aibc-2026.web.app. Demo video: **TEAM** (paste after upload).

## Video, 3:00 hard cap (aim for 2:45)

Record the screen at 1080p. Narrate in English. If any Hindi is audible, add English subtitles. Use only fictional data.

| Time | Shot | Say |
|---|---|---|
| 0:00 to 0:20 | Home page hero, then the ₹22,495 crore stat counting up | "Indians lost ₹22,495 crore to cyber fraud in 2025. Every scam ends in a mule account. We built an AI decoy that waits for the scammer, and then fights back." |
| 0:20 to 1:30 | Live call page. A teammate reads the Hinglish script aloud. Show the orb, the transcript, the UPI ID and bank account appearing, moving from "heard" to "confirmed" after Ramesh reads them back, the gauge reaching "Digital arrest" with trigger phrases. (If the microphone misbehaves, use the Replay page instead.) | "Ramesh, a worried 68-year-old, keeps the caller talking. He repeats every number back, so the caller says it again. A second AI pass and strict validators must both agree before a detail is confirmed." |
| 1:30 to 2:00 | Call review: play the recording, click a transcript line, show the evidence pack and the disclaimer. Then the strain card, then the drill invitation and the parent's phone screen. | "Each call becomes an evidence pack for the bank, and a redacted strain. The strain becomes a practice call for a parent. The coach stops the moment she shares a detail." |
| 2:00 to 2:30 | README evaluation tables | "Honest numbers: detection on a synthetic benchmark against a keyword baseline, three runs; extraction on planted tests; thirty hostile prompts against the persona." |
| 2:30 to 2:45 | Architecture diagram, then the live URL | "Built on Gemini Live and Flash, Cloud Run, Firebase, Firestore and Vertex AI. Trap, Strain, Vaccine. Try it at honeytrap-aibc-2026.web.app." |

Tips: record the replay page as a backup take, turn off notifications, and keep the browser zoom at 100%.

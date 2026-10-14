# honey_trap

AI scam-call decoy for India: **Trap → Strain → Vaccine**. A Gemini-powered Hinglish persona keeps scammers talking, extracts mule accounts and UPI IDs with read-back confirmation, then turns each captured script into a consented family drill. Built for the Google Cloud AI Builder Cup JAPAC 2026 (BFSI theme).

Status: prototype in progress. The full plan lives in [draft.md](draft.md).

## Layout
- `backend/` FastAPI service for Cloud Run (Gemini Live session, extraction, validators)
- `frontend/public/` static site for Firebase Hosting (no build step)
- `tests/` pytest unit tests
- `scripts/` GCP setup and deploy helpers
- `eval/` evaluation harness (raw datasets are gitignored)

## Local setup
```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r backend\requirements-dev.txt
Copy-Item .env.example .env   # then fill in project/location
.\.venv\Scripts\pytest -q
.\.venv\Scripts\uvicorn main:app --app-dir backend --port 8080 --reload
```

## Deploy
```powershell
.\scripts\setup_gcp.ps1 -ProjectId <project>
.\scripts\deploy_backend.ps1 -ProjectId <project> -AllowedOrigins https://<project>.web.app
firebase deploy --only hosting,firestore
```

## Live API spike
```powershell
.\.venv\Scripts\python backend\live_spike.py --locations global,us-central1,asia-south1
```

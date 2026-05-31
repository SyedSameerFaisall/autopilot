# ApplyPilot

ApplyPilot is a local-first personal application OS. It keeps a verified profile vault, discovers opportunities, prepares form submissions with a browser worker, tracks applications, and reconciles Gmail or Microsoft inbox messages against submitted applications.

## Quick start

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
cd frontend
npm install
npm run build
cd ..
uvicorn backend.app.main:app --reload
```

Open `http://127.0.0.1:8000`.

The app seeds a small local demo dataset on first run so the dashboard is useful before OAuth credentials are configured.

## Included MVP

- React dashboard with opportunities, an application tracker, profile vault, inbox match review, and local settings.
- SQLite application history with workflow states, outcomes, stale reminders, and timeline events.
- Review-before-submit API guardrail: submission calls are rejected unless approval is explicit.
- Form-family selection for Luma, Google Forms, Microsoft Forms, and generic HTML pages.
- A visible Playwright worker with a dedicated persistent local browser profile.
- Read-only Gmail and Microsoft OAuth configuration boundaries and incremental reconciliation-ready message storage.
- Curated adapter boundaries for Devpost, Luma, and MLH imports.

The local MVP uses seeded opportunity and email fixtures until provider credentials and live source import implementations are configured. It does not silently submit forms.

## Live integrations

- Add Gmail OAuth values with `APPLYPILOT_GMAIL_CLIENT_ID` and `APPLYPILOT_GMAIL_CLIENT_SECRET`.
- Add Microsoft Graph OAuth values with `APPLYPILOT_MICROSOFT_CLIENT_ID` and optionally `APPLYPILOT_MICROSOFT_TENANT`.
- Install Playwright browsers with `playwright install chromium` before running live preparation sessions.
- Opportunity imports use adapter boundaries. The local release includes deterministic sample imports so the workflow remains demonstrable offline.

ApplyPilot never submits a prepared form without an explicit approval request.

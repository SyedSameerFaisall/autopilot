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

## Fill the current browser tab

ApplyPilot includes an unpacked Chrome extension for the primary workflow:

1. Start the backend with `uvicorn backend.app.main:app --reload --port 8000`.
2. Open `chrome://extensions`, enable **Developer mode**, and choose **Load unpacked**.
3. Select the repository's `extension` folder.
4. Open an application form in Chrome and click the ApplyPilot extension.
5. Press **Fill this page**.

The extension fills supported ordinary HTML and Google Forms fields by searching your private local source vault at fill time. It leaves declarations, checkboxes, file uploads, unknown answers, and the final submit button untouched. If the backend uses another port, update the local backend URL in the popup. After an extension update, reload it from `chrome://extensions`.

AI form filling uses the OpenAI Responses API. Create a local `.env` file from `.env.example`, add your key once, then start the backend:

```powershell
Copy-Item .env.example .env
# Edit .env and replace your-api-key with your new key.
uvicorn backend.app.main:app --reload --port 8024
```

The `.env` file is ignored by Git and stays on your machine. The default model is `gpt-4o-mini` for broad project access. Override it with `APPLYPILOT_OPENAI_MODEL` if your project supports another model. Retrieved passages from your private vault are sent to OpenAI when you request form filling.

If a form tab was already open when the extension was reloaded, ApplyPilot now attaches its page script automatically. Protected browser pages such as `chrome://extensions` cannot be filled.

## Included MVP

- React dashboard with opportunities, an application tracker, profile vault, inbox match review, and local settings.
- SQLite application history with workflow states, outcomes, configurable stale reminders, and timeline events.
- Manual application entry, editable notes, archive actions, and a detail panel for each tracked application.
- Profile Vault onboarding with local PDF, DOCX, TXT, and Markdown extraction.
- LLM-backed memory answering: every fill request retrieves relevant stored passages and reviewed responses, then asks the OpenAI Responses API for grounded answers. Unsupported fields remain blank and generated drafts are marked for review.
- A guided review queue: extracted facts remain suggestions until you explicitly verify or dismiss them.
- Safe GitHub export ingestion that proposes public, active repository links as project context while skipping private and archived repositories.
- Safe browser preparation previews: Playwright inspects form fields, maps verified facts locally, pauses on missing answers and declarations, and keeps submission locked until required answers are reviewed.
- Visible browser autofill handoff: reviewed draft values are typed into the live page, declarations remain untouched, a screenshot receipt is stored locally, and the final submit button is never clicked automatically.
- Lazy-mode URL command: paste a form link once to create the tracker record, inspect the page, and open the review draft in a single step.
- Current-tab Chrome extension: press **Fill this page** while viewing an application to fill supported fields directly in that tab.
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

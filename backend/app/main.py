from __future__ import annotations

import json
import subprocess
import sys
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .browser_worker import PROFILE_DIR, PersistentBrowserWorker
from .database import DATA_DIR, FILES_DIR, ROOT, SCREENSHOTS_DIR, db, hydrate_application, init_db, now_iso, rows
from .integrations import EMAIL_PROVIDERS, OPPORTUNITY_ADAPTERS
from .profile_extractor import extract_candidates, extract_github_export_candidates, extract_text
from .services import apply_email_outcome, demo_sync, prepare_application

@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="ApplyPilot API", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class FactInput(BaseModel):
    section: str
    label: str
    value: str
    verified: bool = False
    source: str = "manual"


class CandidateReview(BaseModel):
    accept: bool
    section: str | None = None
    label: str | None = None
    value: str | None = None


class ApplicationInput(BaseModel):
    opportunity_id: int | None = None
    title: str
    organization: str
    category: str = "Application"
    source_url: str
    deadline: str | None = None
    tags: list[str] = Field(default_factory=list)
    notes: str = ""


class StatusUpdate(BaseModel):
    workflow_status: str | None = None
    outcome: str | None = None
    notes: str | None = None


class SettingsUpdate(BaseModel):
    stale_days: int = Field(ge=1, le=180)


class PreparationFieldUpdate(BaseModel):
    mapped_value: str


class ConfirmMatch(BaseModel):
    application_id: int | None = None
    accept: bool = True


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/demo/application-form", response_class=HTMLResponse)
def demo_application_form() -> str:
    return """<!doctype html><html><head><title>ApplyPilot Demo Form</title></head><body>
    <main><h1>Hackathon registration</h1><form>
      <label>Full name <input name="full_name" required></label>
      <label>Email address <input name="email" type="email" required></label>
      <label>Phone number <input name="phone" type="tel"></label>
      <label>Why do you want to join? <textarea name="motivation" required></textarea></label>
      <label><input name="consent" type="checkbox" required> I agree to the declaration</label>
      <button type="submit">Submit application</button>
    </form></main></body></html>"""


@app.get("/api/dashboard")
def dashboard() -> dict[str, Any]:
    with db() as conn:
        stale_days = int(conn.execute("SELECT value FROM settings WHERE key = 'stale_days'").fetchone()[0])
        applications = [hydrate_application(row, stale_days) for row in conn.execute("SELECT * FROM applications ORDER BY updated_at DESC").fetchall()]
        opportunities = rows(conn.execute("SELECT * FROM opportunities ORDER BY fit_score DESC"))
        pending_matches = conn.execute("SELECT COUNT(*) FROM email_matches WHERE review_status = 'pending'").fetchone()[0]
    for opportunity in opportunities:
        opportunity["tags"] = json.loads(opportunity["tags"])
    return {
        "stats": {
            "opportunities": len(opportunities),
            "applications": len(applications),
            "needs_attention": sum(1 for item in applications if item["workflow_status"] in {"needs_input", "ready_for_review"} or item["is_stale"]) + pending_matches,
            "accepted": sum(1 for item in applications if item["outcome"] == "accepted"),
        },
        "applications": applications[:6],
        "opportunities": opportunities[:4],
        "pending_matches": pending_matches,
    }


@app.get("/api/profile")
def profile() -> list[dict[str, Any]]:
    with db() as conn:
        return rows(conn.execute("SELECT * FROM profile_facts ORDER BY section, id"))


@app.put("/api/profile")
def save_fact(fact: FactInput) -> dict[str, Any]:
    with db() as conn:
        cursor = conn.execute(
            "INSERT INTO profile_facts(section, label, value, verified, source, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            (fact.section, fact.label, fact.value, int(fact.verified), fact.source, now_iso()),
        )
        return {"id": cursor.lastrowid, **fact.model_dump()}


@app.post("/api/profile/import")
async def import_profile(file: UploadFile = File(...)) -> dict[str, Any]:
    FILES_DIR.mkdir(exist_ok=True)
    filename = Path(file.filename or "document").name
    target = FILES_DIR / filename
    target.write_bytes(await file.read())
    with db() as conn:
        cursor = conn.execute(
            "INSERT INTO profile_documents(filename, stored_path, media_type, extraction_status, created_at) VALUES (?, ?, ?, 'pending', ?)",
            (filename, str(target), file.content_type, now_iso()),
        )
        document_id = cursor.lastrowid
        try:
            candidates = extract_candidates(extract_text(target))
            conn.executemany(
                """INSERT INTO profile_candidates(document_id, section, label, value, confidence, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                [(document_id, item.section, item.label, item.value, item.confidence, now_iso()) for item in candidates],
            )
            conn.execute("UPDATE profile_documents SET extraction_status = 'complete' WHERE id = ?", (document_id,))
        except ValueError as exc:
            conn.execute("UPDATE profile_documents SET extraction_status = 'unsupported' WHERE id = ?", (document_id,))
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"id": document_id, "filename": filename, "status": "complete", "candidates": len(candidates), "message": "Document stored locally. Review extracted facts before using them in forms."}


@app.get("/api/profile/documents")
def profile_documents() -> list[dict[str, Any]]:
    with db() as conn:
        return rows(conn.execute("""SELECT profile_documents.*, COUNT(profile_candidates.id) AS candidate_count
                                   FROM profile_documents LEFT JOIN profile_candidates ON profile_candidates.document_id = profile_documents.id
                                   GROUP BY profile_documents.id ORDER BY profile_documents.created_at DESC"""))


@app.post("/api/profile/import-github-export")
async def import_github_export(file: UploadFile = File(...)) -> dict[str, Any]:
    FILES_DIR.mkdir(exist_ok=True)
    filename = Path(file.filename or "github-export.tar.gz").name
    if not filename.lower().endswith(".tar.gz"):
        raise HTTPException(status_code=400, detail="Upload a GitHub export .tar.gz archive.")
    target = FILES_DIR / filename
    target.write_bytes(await file.read())
    try:
        candidates = extract_github_export_candidates(target)
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    with db() as conn:
        cursor = conn.execute(
            "INSERT INTO profile_documents(filename, stored_path, media_type, extraction_status, created_at) VALUES (?, ?, ?, 'complete', ?)",
            (filename, str(target), file.content_type, now_iso()),
        )
        document_id = cursor.lastrowid
        conn.executemany(
            """INSERT INTO profile_candidates(document_id, section, label, value, confidence, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            [(document_id, item.section, item.label, item.value, item.confidence, now_iso()) for item in candidates],
        )
    return {"id": document_id, "filename": filename, "status": "complete", "candidates": len(candidates), "message": "Public GitHub project references are ready for review."}


@app.get("/api/profile/candidates")
def profile_candidates(review_status: str = "pending") -> list[dict[str, Any]]:
    with db() as conn:
        return rows(conn.execute("""SELECT profile_candidates.*, profile_documents.filename
                                   FROM profile_candidates JOIN profile_documents ON profile_documents.id = profile_candidates.document_id
                                   WHERE profile_candidates.review_status = ? ORDER BY profile_candidates.confidence DESC, profile_candidates.id""", (review_status,)))


@app.post("/api/profile/candidates/{candidate_id}/review")
def review_profile_candidate(candidate_id: int, payload: CandidateReview) -> dict[str, Any]:
    with db() as conn:
        candidate = conn.execute("SELECT * FROM profile_candidates WHERE id = ?", (candidate_id,)).fetchone()
        if not candidate:
            raise HTTPException(status_code=404, detail="Profile candidate not found")
        if not payload.accept:
            conn.execute("UPDATE profile_candidates SET review_status = 'dismissed' WHERE id = ?", (candidate_id,))
            return {"status": "dismissed"}
        section = payload.section or candidate["section"]
        label = payload.label or candidate["label"]
        value = payload.value or candidate["value"]
        fact = conn.execute(
            "INSERT INTO profile_facts(section, label, value, verified, source, updated_at) VALUES (?, ?, ?, 1, ?, ?)",
            (section, label, value, f"document:{candidate['document_id']}", now_iso()),
        )
        conn.execute("UPDATE profile_candidates SET review_status = 'accepted' WHERE id = ?", (candidate_id,))
        return {"status": "accepted", "fact_id": fact.lastrowid}


@app.get("/api/opportunities")
def opportunities() -> list[dict[str, Any]]:
    with db() as conn:
        items = rows(conn.execute("SELECT * FROM opportunities ORDER BY fit_score DESC, deadline"))
    for item in items:
        item["tags"] = json.loads(item["tags"])
    return items


@app.post("/api/opportunities/import")
def import_opportunities() -> dict[str, Any]:
    imported = sum(len(adapter.fetch()) for adapter in OPPORTUNITY_ADAPTERS)
    return {"sources": [adapter.name for adapter in OPPORTUNITY_ADAPTERS], "imported": imported, "message": "Sources checked. Demo adapters are already current."}


@app.get("/api/applications")
def applications(
    workflow_status: str | None = None,
    outcome: str | None = None,
    stale: bool | None = Query(default=None),
) -> list[dict[str, Any]]:
    with db() as conn:
        stale_days = int(conn.execute("SELECT value FROM settings WHERE key = 'stale_days'").fetchone()[0])
        items = [hydrate_application(row, stale_days) for row in conn.execute("SELECT * FROM applications ORDER BY updated_at DESC").fetchall()]
    if workflow_status:
        items = [item for item in items if item["workflow_status"] == workflow_status]
    if outcome:
        items = [item for item in items if item["outcome"] == outcome]
    if stale is not None:
        items = [item for item in items if item["is_stale"] is stale]
    return items


@app.get("/api/applications/{application_id}")
def application_detail(application_id: int) -> dict[str, Any]:
    with db() as conn:
        stale_days = int(conn.execute("SELECT value FROM settings WHERE key = 'stale_days'").fetchone()[0])
        application = conn.execute("SELECT * FROM applications WHERE id = ?", (application_id,)).fetchone()
        if not application:
            raise HTTPException(status_code=404, detail="Application not found")
        item = hydrate_application(application, stale_days)
        item["timeline"] = rows(conn.execute("SELECT * FROM timeline_events WHERE application_id = ? ORDER BY created_at DESC", (application_id,)))
        return item


@app.post("/api/applications")
def create_application(payload: ApplicationInput) -> dict[str, Any]:
    with db() as conn:
        stale_days = int(conn.execute("SELECT value FROM settings WHERE key = 'stale_days'").fetchone()[0])
        follow_up = (datetime.now(timezone.utc) + timedelta(days=stale_days)).date().isoformat()
        cursor = conn.execute(
            """INSERT INTO applications(opportunity_id, title, organization, category, source_url, deadline, tags, follow_up_at, notes, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (payload.opportunity_id, payload.title, payload.organization, payload.category, payload.source_url, payload.deadline, json.dumps(payload.tags), follow_up, payload.notes, now_iso(), now_iso()),
        )
        app_id = cursor.lastrowid
        conn.execute("INSERT INTO timeline_events(application_id, event_type, title, detail, created_at) VALUES (?, 'created', 'Added to application queue', ?, ?)", (app_id, payload.source_url, now_iso()))
    return {"id": app_id, "workflow_status": "discovered"}


@app.patch("/api/applications/{application_id}")
def update_application(application_id: int, payload: StatusUpdate) -> dict[str, str]:
    updates = {key: value for key, value in payload.model_dump().items() if value is not None}
    if not updates:
        return {"status": "unchanged"}
    updates["updated_at"] = now_iso()
    assignments = ", ".join(f"{key} = ?" for key in updates)
    with db() as conn:
        cursor = conn.execute(f"UPDATE applications SET {assignments} WHERE id = ?", (*updates.values(), application_id))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Application not found")
        conn.execute("INSERT INTO timeline_events(application_id, event_type, title, detail, created_at) VALUES (?, 'manual', 'Application updated', ?, ?)", (application_id, json.dumps(updates), now_iso()))
    return {"status": "updated"}


@app.post("/api/applications/{application_id}/prepare")
def prepare(application_id: int) -> dict[str, Any]:
    with db() as conn:
        application = conn.execute("SELECT source_url FROM applications WHERE id = ?", (application_id,)).fetchone()
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    worker = PersistentBrowserWorker()
    try:
        inspected_fields = worker.inspect(application["source_url"])
        return prepare_application(application_id, inspected_fields)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        worker.close()


@app.get("/api/applications/{application_id}/preparation")
def preparation_preview(application_id: int) -> dict[str, Any]:
    with db() as conn:
        run = conn.execute("SELECT * FROM preparation_runs WHERE application_id = ? ORDER BY id DESC LIMIT 1", (application_id,)).fetchone()
        if not run:
            raise HTTPException(status_code=404, detail="No preparation run found")
        fields = rows(conn.execute("SELECT * FROM preparation_fields WHERE run_id = ? ORDER BY id", (run["id"],)))
    return {**dict(run), "fields": fields, "requires_approval": True}


@app.patch("/api/preparation-fields/{field_id}")
def update_preparation_field(field_id: int, payload: PreparationFieldUpdate) -> dict[str, str]:
    with db() as conn:
        cursor = conn.execute(
            "UPDATE preparation_fields SET mapped_value = ?, review_status = 'edited', confidence = 1, reason = 'Edited during user review.' WHERE id = ?",
            (payload.mapped_value, field_id),
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Preparation field not found")
    return {"status": "updated"}


@app.post("/api/applications/{application_id}/autofill")
def autofill_application(application_id: int) -> dict[str, Any]:
    with db() as conn:
        run = conn.execute("SELECT * FROM preparation_runs WHERE application_id = ? ORDER BY id DESC LIMIT 1", (application_id,)).fetchone()
        if not run:
            raise HTTPException(status_code=409, detail="Prepare and review the application before opening browser autofill.")
        fields = rows(conn.execute("SELECT * FROM preparation_fields WHERE run_id = ? ORDER BY id", (run["id"],)))
        session_token = uuid.uuid4().hex
        state_path = DATA_DIR / f"autofill-{session_token}.json"
        payload_path = DATA_DIR / f"autofill-{session_token}-payload.json"
        screenshot_path = SCREENSHOTS_DIR / f"autofill-{session_token}.png"
        cursor = conn.execute(
            """INSERT INTO browser_fill_sessions(application_id, run_id, state_path, created_at)
               VALUES (?, ?, ?, ?)""",
            (application_id, run["id"], str(state_path), now_iso()),
        )
        session_id = cursor.lastrowid
    DATA_DIR.mkdir(exist_ok=True)
    payload_path.write_text(
        json.dumps(
            {
                "source_url": run["source_url"],
                "fields": fields,
                "state_path": str(state_path),
                "screenshot_path": str(screenshot_path),
                "profile_dir": str(PROFILE_DIR),
            }
        ),
        encoding="utf-8",
    )
    creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    subprocess.Popen(
        [sys.executable, "-m", "backend.app.autofill_runner", str(payload_path)],
        cwd=ROOT,
        creationflags=creationflags,
    )
    deadline = time.time() + 12
    state: dict[str, Any] = {"status": "launching"}
    while time.time() < deadline:
        if state_path.exists():
            state = json.loads(state_path.read_text(encoding="utf-8"))
            if state.get("status") in {"filled", "failed"}:
                break
        time.sleep(0.2)
    with db() as conn:
        conn.execute(
            "UPDATE browser_fill_sessions SET status = ?, screenshot_path = ? WHERE id = ?",
            (state.get("status", "launching"), state.get("screenshot_path"), session_id),
        )
        conn.execute(
            "INSERT INTO timeline_events(application_id, event_type, title, detail, created_at) VALUES (?, 'autofill', 'Visible browser autofill launched', ?, ?)",
            (application_id, f"Filled {len(state.get('filled', []))} reviewed fields without submitting the form.", now_iso()),
        )
    if state.get("status") == "failed":
        raise HTTPException(status_code=400, detail=state.get("error", "Browser autofill failed"))
    return {
        "session_id": session_id,
        "status": state.get("status", "launching"),
        "filled": state.get("filled", []),
        "skipped": state.get("skipped", []),
        "screenshot_url": f"/api/browser-fill-sessions/{session_id}/screenshot" if state.get("screenshot_path") else None,
        "submitted": False,
    }


@app.get("/api/browser-fill-sessions/{session_id}/screenshot")
def browser_fill_screenshot(session_id: int) -> FileResponse:
    with db() as conn:
        session = conn.execute("SELECT screenshot_path FROM browser_fill_sessions WHERE id = ?", (session_id,)).fetchone()
    if not session or not session["screenshot_path"] or not Path(session["screenshot_path"]).exists():
        raise HTTPException(status_code=404, detail="Autofill screenshot not found")
    return FileResponse(session["screenshot_path"])


@app.post("/api/applications/{application_id}/submit")
def submit(application_id: int, approved: bool = False) -> dict[str, Any]:
    if not approved:
        raise HTTPException(status_code=409, detail="Explicit approval is required before submission.")
    with db() as conn:
        run = conn.execute("SELECT id FROM preparation_runs WHERE application_id = ? ORDER BY id DESC LIMIT 1", (application_id,)).fetchone()
        if not run:
            raise HTTPException(status_code=409, detail="Prepare and review the application before submission.")
        unresolved = conn.execute("SELECT COUNT(*) FROM preparation_fields WHERE run_id = ? AND required = 1 AND (mapped_value IS NULL OR TRIM(mapped_value) = '')", (run["id"],)).fetchone()[0]
        if unresolved:
            raise HTTPException(status_code=409, detail=f"{unresolved} required form fields still need reviewed answers.")
        conn.execute("UPDATE applications SET workflow_status = 'submitted', submitted_at = ?, updated_at = ? WHERE id = ?", (now_iso(), now_iso(), application_id))
        conn.execute("INSERT INTO timeline_events(application_id, event_type, title, detail, created_at) VALUES (?, 'submitted', 'Submission approved', 'User approved the external submission.', ?)", (application_id, now_iso()))
    return {"application_id": application_id, "workflow_status": "submitted"}


@app.get("/api/applications/{application_id}/timeline")
def timeline(application_id: int) -> list[dict[str, Any]]:
    with db() as conn:
        return rows(conn.execute("SELECT * FROM timeline_events WHERE application_id = ? ORDER BY created_at DESC", (application_id,)))


@app.get("/api/settings")
def settings() -> dict[str, int]:
    with db() as conn:
        stale_days = int(conn.execute("SELECT value FROM settings WHERE key = 'stale_days'").fetchone()[0])
    return {"stale_days": stale_days}


@app.put("/api/settings")
def update_settings(payload: SettingsUpdate) -> dict[str, int]:
    with db() as conn:
        conn.execute("INSERT INTO settings(key, value) VALUES ('stale_days', ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value", (str(payload.stale_days),))
    return payload.model_dump()


@app.get("/api/email-accounts")
def email_accounts() -> list[dict[str, Any]]:
    with db() as conn:
        accounts = rows(conn.execute("SELECT * FROM email_accounts ORDER BY provider"))
    known = {account["provider"] for account in accounts}
    accounts.extend({"provider": provider, "connected": 0, "email_address": None, "last_synced_at": None} for provider in ("gmail", "microsoft") if provider not in known)
    return accounts


@app.post("/api/email-accounts/{provider}/connect")
def connect_email(provider: Literal["gmail", "microsoft"]) -> dict[str, str]:
    config = EMAIL_PROVIDERS[provider]
    status = "ready_for_oauth" if config.configured else "configuration_required"
    return {"provider": provider, "status": status, "message": f"{provider.title()} uses read-only inbox access. Add local OAuth credentials to begin the consent flow."}


@app.post("/api/email-sync")
def sync_email() -> dict[str, Any]:
    count = demo_sync()
    return {"status": "synced", "matches": count, "message": "Inbox adapters reconciled available messages without modifying mailbox state."}


@app.get("/api/email-matches")
def email_matches() -> list[dict[str, Any]]:
    with db() as conn:
        return rows(conn.execute("""SELECT email_matches.*, applications.title AS application_title
                                   FROM email_matches LEFT JOIN applications ON applications.id = email_matches.application_id
                                   ORDER BY received_at DESC"""))


@app.post("/api/email-matches/{match_id}/confirm")
def confirm_match(match_id: int, payload: ConfirmMatch) -> dict[str, str]:
    with db() as conn:
        match = conn.execute("SELECT * FROM email_matches WHERE id = ?", (match_id,)).fetchone()
        if not match:
            raise HTTPException(status_code=404, detail="Email match not found")
        if not payload.accept:
            conn.execute("UPDATE email_matches SET review_status = 'dismissed' WHERE id = ?", (match_id,))
            return {"status": "dismissed"}
        application_id = payload.application_id or match["application_id"]
        if not application_id:
            raise HTTPException(status_code=400, detail="Choose an application before confirming the match")
        conn.execute("UPDATE email_matches SET application_id = ?, review_status = 'confirmed' WHERE id = ?", (application_id, match_id))
        apply_email_outcome(conn, application_id, match["classification"], match["received_at"], match["subject"])
    return {"status": "confirmed"}


STATIC_DIR = ROOT / "frontend" / "dist"
if STATIC_DIR.exists():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    @app.get("/{path:path}")
    def frontend(path: str) -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

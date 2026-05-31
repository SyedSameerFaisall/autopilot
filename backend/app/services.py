from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .automation import map_verified_facts, select_form_adapter
from .browser_worker import InspectedField
from .database import db, now_iso, rows


@dataclass
class EmailCandidate:
    provider: str
    provider_message_id: str
    sender: str
    subject: str
    body: str
    received_at: str


OUTCOME_TERMS = {
    "accepted": ("congratulations", "accepted", "selected", "welcome to"),
    "rejected": ("unfortunately", "not selected", "regret to inform", "won't be moving"),
    "waitlisted": ("waitlist", "waiting list"),
    "next_step": ("interview", "next step", "action required", "complete your"),
    "acknowledgement": ("application received", "thanks for applying", "registration confirmed"),
}


def classify_email(subject: str, body: str) -> tuple[str, float]:
    text = f"{subject} {body}".lower()
    for classification, terms in OUTCOME_TERMS.items():
        if any(term in text for term in terms):
            return classification, 0.94 if classification in {"accepted", "rejected", "waitlisted"} else 0.86
    return "unrelated", 0.42


def match_application(subject: str, body: str) -> tuple[int | None, float]:
    text = f"{subject} {body}".lower()
    with db() as conn:
        applications = rows(conn.execute("SELECT id, title, organization FROM applications"))
    best_id: int | None = None
    best_score = 0.0
    for app in applications:
        title_words = [w for w in re.findall(r"[a-z0-9]+", app["title"].lower()) if len(w) > 3]
        organization = app["organization"].lower()
        hits = sum(1 for word in title_words if word in text)
        score = min(0.75, hits * 0.18)
        if organization and organization in text:
            score += 0.3
        if score > best_score:
            best_id, best_score = app["id"], min(score, 0.99)
    return best_id, best_score


def reconcile_email(candidate: EmailCandidate) -> dict[str, Any]:
    classification, classification_confidence = classify_email(candidate.subject, candidate.body)
    application_id, match_confidence = match_application(candidate.subject, candidate.body)
    confidence = round((classification_confidence + match_confidence) / 2, 2)
    review_status = "confirmed" if application_id and confidence >= 0.82 else "pending"
    excerpt = candidate.body[:240].strip()
    with db() as conn:
        cursor = conn.execute(
            """INSERT OR IGNORE INTO email_matches(provider, provider_message_id, application_id, sender, subject, excerpt, body, received_at, classification, confidence, review_status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (candidate.provider, candidate.provider_message_id, application_id, candidate.sender, candidate.subject, excerpt, candidate.body, candidate.received_at, classification, confidence, review_status),
        )
        if cursor.lastrowid and application_id and review_status == "confirmed":
            apply_email_outcome(conn, application_id, classification, candidate.received_at, candidate.subject)
        match = conn.execute("SELECT * FROM email_matches WHERE provider_message_id = ?", (candidate.provider_message_id,)).fetchone()
    return dict(match)


def apply_email_outcome(conn: Any, application_id: int, classification: str, received_at: str, subject: str) -> None:
    outcome = classification if classification in {"accepted", "rejected", "waitlisted"} else None
    if outcome:
        conn.execute("UPDATE applications SET outcome = ?, last_reply_at = ?, updated_at = ? WHERE id = ?", (outcome, received_at, now_iso(), application_id))
    else:
        conn.execute("UPDATE applications SET last_reply_at = ?, updated_at = ? WHERE id = ?", (received_at, now_iso(), application_id))
    conn.execute(
        "INSERT INTO timeline_events(application_id, event_type, title, detail, created_at) VALUES (?, 'email', ?, ?, ?)",
        (application_id, f"Email matched: {classification.replace('_', ' ').title()}", subject, received_at),
    )


def demo_sync() -> int:
    now = datetime.now(timezone.utc).isoformat()
    candidates = [
        EmailCandidate("gmail", "demo-gmail-001", "hello@devpost.com", "We received your AI for Good Hackathon application", "Thanks for applying to the AI for Good Hackathon. Your application received our attention and is now under review.", now),
        EmailCandidate("microsoft", "demo-ms-001", "events@example.org", "Developer community registration confirmed", "Your event registration is confirmed. We look forward to seeing you.", now),
    ]
    for candidate in candidates:
        reconcile_email(candidate)
    with db() as conn:
        return conn.execute("SELECT COUNT(*) FROM email_matches").fetchone()[0]


def prepare_application(application_id: int, inspected_fields: list[InspectedField]) -> dict[str, Any]:
    with db() as conn:
        application = conn.execute("SELECT * FROM applications WHERE id = ?", (application_id,)).fetchone()
        if not application:
            raise ValueError("Application not found")
        facts = rows(conn.execute("SELECT * FROM profile_facts WHERE verified = 1"))
        adapter = select_form_adapter(application["source_url"])
        mapped_fields = map_verified_facts(inspected_fields, facts)
        run = conn.execute(
            "INSERT INTO preparation_runs(application_id, adapter, source_url, created_at) VALUES (?, ?, ?, ?)",
            (application_id, adapter, application["source_url"], now_iso()),
        )
        run_id = run.lastrowid
        for field in mapped_fields:
            source_fact = next((fact for fact in facts if field.value and fact["value"] == field.value), None)
            review_status = "mapped" if field.value else "needs_input"
            reason = "Mapped from a verified profile fact." if field.value else "No verified profile fact matched this field."
            conn.execute(
                """INSERT INTO preparation_fields(run_id, label, field_name, field_type, required, mapped_value, source_fact_id, confidence, review_status, reason)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (run_id, field.label, field.label, field.field_type, int(field.required), field.value, source_fact["id"] if source_fact else None, field.confidence, review_status, reason),
            )
        conn.execute("UPDATE applications SET workflow_status = 'ready_for_review', updated_at = ? WHERE id = ?", (now_iso(), application_id))
        conn.execute(
            "INSERT INTO timeline_events(application_id, event_type, title, detail, created_at) VALUES (?, 'prepared', 'Application prepared for review', ?, ?)",
            (application_id, f"{adapter} adapter inspected {len(mapped_fields)} fields. Browser submission remains locked.", now_iso()),
        )
    return {"application_id": application_id, "run_id": run_id, "status": "ready_for_review", "adapter": adapter, "mapped_fields": sum(1 for field in mapped_fields if field.value), "requires_approval": True}

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "applypilot.db"
FILES_DIR = DATA_DIR / "documents"
SCREENSHOTS_DIR = DATA_DIR / "screenshots"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def db() -> Iterator[sqlite3.Connection]:
    DATA_DIR.mkdir(exist_ok=True)
    FILES_DIR.mkdir(exist_ok=True)
    SCREENSHOTS_DIR.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def rows(cursor: sqlite3.Cursor) -> list[dict[str, Any]]:
    return [dict(row) for row in cursor.fetchall()]


SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS profile_facts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  section TEXT NOT NULL,
  label TEXT NOT NULL,
  value TEXT NOT NULL,
  verified INTEGER NOT NULL DEFAULT 0,
  source TEXT NOT NULL DEFAULT 'manual',
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS profile_documents (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  filename TEXT NOT NULL,
  stored_path TEXT NOT NULL,
  media_type TEXT,
  extraction_status TEXT NOT NULL DEFAULT 'pending',
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS profile_candidates (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  document_id INTEGER NOT NULL,
  section TEXT NOT NULL,
  label TEXT NOT NULL,
  value TEXT NOT NULL,
  confidence REAL NOT NULL,
  review_status TEXT NOT NULL DEFAULT 'pending',
  created_at TEXT NOT NULL,
  FOREIGN KEY(document_id) REFERENCES profile_documents(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS opportunities (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  title TEXT NOT NULL,
  organization TEXT NOT NULL,
  category TEXT NOT NULL,
  source TEXT NOT NULL,
  source_url TEXT NOT NULL UNIQUE,
  deadline TEXT,
  location TEXT,
  effort TEXT NOT NULL DEFAULT 'Medium',
  fit_score INTEGER NOT NULL DEFAULT 0,
  tags TEXT NOT NULL DEFAULT '[]',
  summary TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS applications (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  opportunity_id INTEGER,
  title TEXT NOT NULL,
  organization TEXT NOT NULL,
  category TEXT NOT NULL,
  source_url TEXT NOT NULL,
  deadline TEXT,
  tags TEXT NOT NULL DEFAULT '[]',
  workflow_status TEXT NOT NULL DEFAULT 'discovered',
  outcome TEXT NOT NULL DEFAULT 'pending',
  submitted_at TEXT,
  last_reply_at TEXT,
  follow_up_at TEXT,
  notes TEXT NOT NULL DEFAULT '',
  receipt_path TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY(opportunity_id) REFERENCES opportunities(id)
);
CREATE TABLE IF NOT EXISTS timeline_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  application_id INTEGER NOT NULL,
  event_type TEXT NOT NULL,
  title TEXT NOT NULL,
  detail TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  FOREIGN KEY(application_id) REFERENCES applications(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS preparation_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  application_id INTEGER NOT NULL,
  adapter TEXT NOT NULL,
  source_url TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'ready_for_review',
  created_at TEXT NOT NULL,
  FOREIGN KEY(application_id) REFERENCES applications(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS browser_fill_sessions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  application_id INTEGER NOT NULL,
  run_id INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'launching',
  screenshot_path TEXT,
  state_path TEXT NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY(application_id) REFERENCES applications(id) ON DELETE CASCADE,
  FOREIGN KEY(run_id) REFERENCES preparation_runs(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS preparation_fields (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id INTEGER NOT NULL,
  label TEXT NOT NULL,
  field_name TEXT NOT NULL,
  field_type TEXT NOT NULL,
  required INTEGER NOT NULL DEFAULT 0,
  mapped_value TEXT,
  source_fact_id INTEGER,
  confidence REAL NOT NULL DEFAULT 0,
  review_status TEXT NOT NULL,
  reason TEXT NOT NULL DEFAULT '',
  FOREIGN KEY(run_id) REFERENCES preparation_runs(id) ON DELETE CASCADE,
  FOREIGN KEY(source_fact_id) REFERENCES profile_facts(id)
);
CREATE TABLE IF NOT EXISTS email_accounts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  provider TEXT NOT NULL UNIQUE,
  email_address TEXT,
  connected INTEGER NOT NULL DEFAULT 0,
  cursor TEXT,
  last_synced_at TEXT
);
CREATE TABLE IF NOT EXISTS email_matches (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  provider TEXT NOT NULL,
  provider_message_id TEXT NOT NULL UNIQUE,
  application_id INTEGER,
  sender TEXT NOT NULL,
  subject TEXT NOT NULL,
  excerpt TEXT NOT NULL,
  body TEXT NOT NULL DEFAULT '',
  received_at TEXT NOT NULL,
  classification TEXT NOT NULL,
  confidence REAL NOT NULL,
  review_status TEXT NOT NULL DEFAULT 'pending',
  FOREIGN KEY(application_id) REFERENCES applications(id)
);
"""


def init_db() -> None:
    with db() as conn:
        conn.executescript(SCHEMA)
        conn.execute("INSERT OR IGNORE INTO settings(key, value) VALUES ('stale_days', '14')")
        count = conn.execute("SELECT COUNT(*) FROM opportunities").fetchone()[0]
        if count == 0:
            seed_demo(conn)


def seed_demo(conn: sqlite3.Connection) -> None:
    now = datetime.now(timezone.utc)
    opportunities = [
        ("AI for Good Hackathon", "Devpost", "Hackathon", "Devpost", "https://devpost.com/hackathons/ai-for-good-demo", 12, "Online", "Medium", 94, ["AI", "Social impact"], "Build an AI project with measurable community value."),
        ("Developer Week London", "Luma", "Event", "Luma", "https://lu.ma/applypilot-developer-week", 7, "London", "Low", 82, ["Networking", "Engineering"], "A developer meetup with a short registration form."),
        ("Global Student Innovation Challenge", "MLH", "Competition", "MLH", "https://mlh.io/events/applypilot-student-innovation", 19, "Hybrid", "High", 88, ["Student", "Product"], "Pitch a useful technology product for students."),
        ("Open Source Sprint", "Devpost", "Hackathon", "Devpost", "https://devpost.com/hackathons/applypilot-open-source", 28, "Online", "Medium", 77, ["Open source"], "Contribute a practical tool and share a short demo."),
    ]
    for title, org, category, source, url, days, location, effort, fit, tags, summary in opportunities:
        conn.execute(
            """INSERT INTO opportunities(title, organization, category, source, source_url, deadline, location, effort, fit_score, tags, summary, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (title, org, category, source, url, (now + timedelta(days=days)).date().isoformat(), location, effort, fit, json.dumps(tags), summary, now_iso()),
        )
    opportunity = conn.execute("SELECT * FROM opportunities ORDER BY id LIMIT 1").fetchone()
    submitted = (now - timedelta(days=10)).isoformat()
    follow_up = (now + timedelta(days=4)).date().isoformat()
    cur = conn.execute(
        """INSERT INTO applications(opportunity_id, title, organization, category, source_url, deadline, tags, workflow_status, outcome, submitted_at, follow_up_at, notes, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, 'submitted', 'pending', ?, ?, ?, ?, ?)""",
        (opportunity["id"], opportunity["title"], opportunity["organization"], opportunity["category"], opportunity["source_url"], opportunity["deadline"], opportunity["tags"], submitted, follow_up, "Demo submission awaiting organizer response.", now_iso(), now_iso()),
    )
    app_id = cur.lastrowid
    conn.execute(
        "INSERT INTO timeline_events(application_id, event_type, title, detail, created_at) VALUES (?, 'submitted', 'Application submitted', 'Receipt captured and saved locally.', ?)",
        (app_id, submitted),
    )
    facts = [
        ("Personal", "Full name", "Your name", 0, "onboarding"),
        ("Personal", "Email", "you@example.com", 0, "onboarding"),
        ("Education", "Current course", "Add your degree or course", 0, "onboarding"),
        ("Preferences", "Preferred locations", "London, Remote", 1, "manual"),
    ]
    conn.executemany(
        "INSERT INTO profile_facts(section, label, value, verified, source, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
        [(*fact, now_iso()) for fact in facts],
    )


def hydrate_application(row: sqlite3.Row | dict[str, Any], stale_days: int = 14) -> dict[str, Any]:
    item = dict(row)
    item["tags"] = json.loads(item.get("tags") or "[]")
    submitted = item.get("submitted_at")
    item["is_stale"] = bool(
        submitted
        and item.get("outcome") == "pending"
        and datetime.fromisoformat(submitted).date() <= (datetime.now(timezone.utc) - timedelta(days=stale_days)).date()
    )
    return item

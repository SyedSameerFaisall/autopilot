from pathlib import Path

from fastapi.testclient import TestClient

from backend.app import database
from backend.app import main as main_module
from backend.app.main import app


def test_tracker_detail_updates_and_settings(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(database, "DATA_DIR", tmp_path)
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(database, "FILES_DIR", tmp_path / "documents")
    monkeypatch.setattr(database, "SCREENSHOTS_DIR", tmp_path / "screenshots")
    database.init_db()

    with TestClient(app) as client:
        settings = client.put("/api/settings", json={"stale_days": 21})
        assert settings.status_code == 200
        assert settings.json() == {"stale_days": 21}

        created = client.post(
            "/api/applications",
            json={
                "title": "Manual scholarship application",
                "organization": "Example University",
                "category": "Scholarship",
                "source_url": "https://example.edu/apply",
                "notes": "Created from the tracker.",
            },
        )
        assert created.status_code == 200
        application_id = created.json()["id"]

        detail = client.get(f"/api/applications/{application_id}")
        assert detail.status_code == 200
        assert detail.json()["follow_up_at"] is not None
        assert detail.json()["timeline"][0]["event_type"] == "created"

        updated = client.patch(
            f"/api/applications/{application_id}",
            json={"workflow_status": "archived", "notes": "No longer relevant."},
        )
        assert updated.status_code == 200

        detail = client.get(f"/api/applications/{application_id}").json()
        assert detail["workflow_status"] == "archived"
        assert detail["notes"] == "No longer relevant."
        assert detail["timeline"][0]["event_type"] == "manual"


def test_missing_application_update_returns_not_found(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(database, "DATA_DIR", tmp_path)
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(database, "FILES_DIR", tmp_path / "documents")
    monkeypatch.setattr(database, "SCREENSHOTS_DIR", tmp_path / "screenshots")
    database.init_db()

    with TestClient(app) as client:
        response = client.patch("/api/applications/9999", json={"notes": "Missing"})
        assert response.status_code == 404


def test_profile_import_requires_candidate_review(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(database, "DATA_DIR", tmp_path)
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(database, "FILES_DIR", tmp_path / "documents")
    monkeypatch.setattr(database, "SCREENSHOTS_DIR", tmp_path / "screenshots")
    monkeypatch.setattr(main_module, "FILES_DIR", tmp_path / "documents")
    database.init_db()

    with TestClient(app) as client:
        uploaded = client.post(
            "/api/profile/import",
            files={"file": ("cv.txt", b"Sameer Faisal\nsameer@example.com\nhttps://github.com/sameer", "text/plain")},
        )
        assert uploaded.status_code == 200
        assert uploaded.json()["candidates"] == 3

        candidates = client.get("/api/profile/candidates").json()
        email = next(item for item in candidates if item["label"] == "Email")
        assert email["review_status"] == "pending"

        facts = client.get("/api/profile").json()
        assert not any(item["value"] == "sameer@example.com" and item["verified"] for item in facts)

        reviewed = client.post(
            f"/api/profile/candidates/{email['id']}/review",
            json={"accept": True, "value": "sameer.corrected@example.com"},
        )
        assert reviewed.status_code == 200

        facts = client.get("/api/profile").json()
        assert any(item["value"] == "sameer.corrected@example.com" and item["verified"] for item in facts)

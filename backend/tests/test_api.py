from pathlib import Path

from fastapi.testclient import TestClient

from backend.app import database
from backend.app import main as main_module
from backend.app.browser_worker import InspectedField
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


def test_preparation_preview_blocks_unresolved_required_fields(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(database, "DATA_DIR", tmp_path)
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(database, "FILES_DIR", tmp_path / "documents")
    monkeypatch.setattr(database, "SCREENSHOTS_DIR", tmp_path / "screenshots")
    database.init_db()

    class FakeWorker:
        def inspect(self, _: str):
            return [
                InspectedField("Email address", "email", "email", True),
                InspectedField("Why do you want to join?", "motivation", "textarea", True),
            ]

        def close(self) -> None:
            pass

    monkeypatch.setattr(main_module, "PersistentBrowserWorker", FakeWorker)
    with TestClient(app) as client:
        client.put("/api/profile", json={"section": "Personal", "label": "Email", "value": "sameer@example.com", "verified": True})
        created = client.post("/api/applications", json={"title": "Fixture", "organization": "ApplyPilot", "source_url": "https://example.com/apply"}).json()
        prepared = client.post(f"/api/applications/{created['id']}/prepare")
        assert prepared.status_code == 200

        preview = client.get(f"/api/applications/{created['id']}/preparation").json()
        assert preview["requires_approval"] is True
        assert [field["review_status"] for field in preview["fields"]] == ["mapped", "needs_input"]

        blocked = client.post(f"/api/applications/{created['id']}/submit?approved=true")
        assert blocked.status_code == 409
        assert "required form fields" in blocked.json()["detail"]


def test_autopilot_command_creates_and_prepares_application(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(database, "DATA_DIR", tmp_path)
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(database, "FILES_DIR", tmp_path / "documents")
    monkeypatch.setattr(database, "SCREENSHOTS_DIR", tmp_path / "screenshots")
    database.init_db()

    class FakeWorker:
        def inspect(self, _: str):
            return [InspectedField("Email address", "email", "email", True)]

        def close(self) -> None:
            pass

    monkeypatch.setattr(main_module, "PersistentBrowserWorker", FakeWorker)
    with TestClient(app) as client:
        response = client.post("/api/autopilot/prepare", json={"source_url": "https://forms.example.com/apply"})
        assert response.status_code == 200
        application_id = response.json()["application_id"]
        detail = client.get(f"/api/applications/{application_id}").json()
        assert detail["organization"] == "forms.example.com"
        assert detail["workflow_status"] == "ready_for_review"


def test_browser_extension_fill_plan_uses_verified_facts_and_skips_declarations(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(database, "DATA_DIR", tmp_path)
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(database, "FILES_DIR", tmp_path / "documents")
    monkeypatch.setattr(database, "SCREENSHOTS_DIR", tmp_path / "screenshots")
    database.init_db()

    with TestClient(app) as client:
        client.put("/api/profile", json={"section": "Personal", "label": "Email", "value": "sameer@example.com", "verified": True})
        response = client.post(
            "/api/browser-extension/fill-plan",
            json={
                "source_url": "https://forms.example.com/apply",
                "fields": [
                    {"locator_id": "field-0", "label": "Email address", "name": "email", "field_type": "email", "required": True},
                    {"locator_id": "field-1", "label": "I agree to the declaration", "name": "consent", "field_type": "checkbox", "required": True},
                ],
            },
        )
        assert response.status_code == 200
        plan = response.json()
        assert plan["mapped"] == 1
        assert plan["needs_input"] == 1
        assert plan["submitted"] is False
        assert plan["fields"][0]["mapped_value"] == "sameer@example.com"
        assert plan["fields"][1]["mapped_value"] is None


def test_google_forms_style_fixture_includes_question_containers_and_hidden_controls() -> None:
    with TestClient(app) as client:
        response = client.get("/demo/google-form-style")
        assert response.status_code == 200
        assert response.text.count('role="listitem"') == 3
        assert 'type="hidden"' in response.text
        assert 'type="submit"' in response.text

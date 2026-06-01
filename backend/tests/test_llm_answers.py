import json

from backend.app import database
from backend.app import llm_answers
from backend.app.browser_worker import InspectedField


def test_answer_form_fields_calls_responses_api_with_retrieved_memory(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(database, "DATA_DIR", tmp_path)
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    database.init_db()
    with database.db() as conn:
        conn.execute(
            """INSERT INTO knowledge_chunks(document_id, source_type, source_label, content, created_at)
               VALUES (NULL, 'manual_memory', 'Contact details', 'My email is sameer@example.com', ?)""",
            (database.now_iso(),),
        )

    captured = {}

    class FakeResponse:
        status_code = 200

        def json(self):
            return {
                "output": [{
                    "content": [{
                        "type": "output_text",
                        "text": json.dumps({"answers": [{
                            "id": 0,
                            "supported": True,
                            "answer": "sameer@example.com",
                            "confidence": 0.98,
                            "source_reference": "Contact details",
                            "evidence": "My email is sameer@example.com",
                        }]}),
                    }]
                }]
            }

    class FakeClient:
        def __init__(self, timeout):
            captured["timeout"] = timeout

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def post(self, url, headers, json):
            captured.update({"url": url, "headers": headers, "payload": json})
            return FakeResponse()

    monkeypatch.setattr(llm_answers.httpx, "Client", FakeClient)
    with database.db() as conn:
        answers = llm_answers.answer_form_fields(conn, [InspectedField("Email address", "email", "email", True)])

    assert answers[0].value == "sameer@example.com"
    assert captured["url"] == "https://api.openai.com/v1/responses"
    assert captured["payload"]["model"] == "gpt-4o-mini"
    assert "My email is sameer@example.com" in captured["payload"]["input"]
    assert captured["payload"]["text"]["format"]["type"] == "json_schema"

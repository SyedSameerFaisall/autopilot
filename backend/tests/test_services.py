from backend.app.automation import select_form_adapter
from backend.app.services import classify_email


def test_email_classification() -> None:
    assert classify_email("Congratulations", "You have been selected")[0] == "accepted"
    assert classify_email("Update", "Unfortunately, we cannot proceed")[0] == "rejected"
    assert classify_email("Hello", "Coffee next week?")[0] == "unrelated"


def test_form_adapter_selection() -> None:
    assert select_form_adapter("https://lu.ma/demo") == "Luma"
    assert select_form_adapter("https://docs.google.com/forms/d/demo") == "Google Forms"
    assert select_form_adapter("https://example.com/apply") == "Generic HTML"

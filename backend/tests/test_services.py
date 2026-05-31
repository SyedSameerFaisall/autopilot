from backend.app.automation import map_verified_facts, select_form_adapter
from backend.app.browser_worker import InspectedField, fill_page
from backend.app.services import classify_email


def test_email_classification() -> None:
    assert classify_email("Congratulations", "You have been selected")[0] == "accepted"
    assert classify_email("Update", "Unfortunately, we cannot proceed")[0] == "rejected"
    assert classify_email("Hello", "Coffee next week?")[0] == "unrelated"


def test_form_adapter_selection() -> None:
    assert select_form_adapter("https://lu.ma/demo") == "Luma"
    assert select_form_adapter("https://docs.google.com/forms/d/demo") == "Google Forms"
    assert select_form_adapter("https://example.com/apply") == "Generic HTML"


def test_map_verified_facts_pauses_for_unknown_and_sensitive_fields() -> None:
    fields = [
        InspectedField("Email address", "email", "email", True),
        InspectedField("Why do you want to join?", "motivation", "textarea", True),
        InspectedField("I agree to the declaration", "consent", "checkbox", True),
    ]
    facts = [{"id": 1, "label": "Email", "value": "sameer@example.com"}]
    mapped = map_verified_facts(fields, facts)
    assert mapped[0].value == "sameer@example.com"
    assert mapped[1].value is None
    assert mapped[2].value is None


def test_fill_page_skips_declarations_and_never_clicks() -> None:
    values: dict[str, str] = {}

    class FakeLocator:
        def __init__(self, selector: str) -> None:
            self.selector = selector

        def count(self) -> int:
            return 1

        def fill(self, value: str) -> None:
            values[self.selector] = value

        def select_option(self, value: str) -> None:
            values[self.selector] = value

    class FakePage:
        def locator(self, selector: str) -> FakeLocator:
            return FakeLocator(selector)

    result = fill_page(FakePage(), [
        {"label": "Email", "field_name": "email", "field_type": "email", "mapped_value": "sameer@example.com"},
        {"label": "Declaration", "field_name": "consent", "field_type": "checkbox", "mapped_value": "yes"},
    ])
    assert values == {'[name="email"]': "sameer@example.com"}
    assert result == {"filled": ["Email"], "skipped": ["Declaration"]}

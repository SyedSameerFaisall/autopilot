from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol
from urllib.parse import urlparse

from .browser_worker import InspectedField


@dataclass(frozen=True)
class FormField:
    label: str
    name: str
    field_type: str
    required: bool
    value: str | None = None
    confidence: float = 0.0
    source_kind: str | None = None
    source_reference: str | None = None
    reason: str = ""


@dataclass(frozen=True)
class PreparationResult:
    adapter: str
    fields: list[FormField]
    requires_review: bool = True


class FormAdapter(Protocol):
    name: str

    def supports(self, url: str) -> bool: ...


class DomainAdapter:
    def __init__(self, name: str, domains: tuple[str, ...]) -> None:
        self.name = name
        self.domains = domains

    def supports(self, url: str) -> bool:
        hostname = urlparse(url).hostname or ""
        return any(hostname == domain or hostname.endswith(f".{domain}") for domain in self.domains)


FORM_ADAPTERS: tuple[FormAdapter, ...] = (
    DomainAdapter("Luma", ("lu.ma",)),
    DomainAdapter("Google Forms", ("docs.google.com",)),
    DomainAdapter("Microsoft Forms", ("forms.office.com", "forms.microsoft.com")),
    DomainAdapter("Generic HTML", ()),
)


def select_form_adapter(url: str) -> str:
    for adapter in FORM_ADAPTERS[:-1]:
        if adapter.supports(url):
            return adapter.name
    return FORM_ADAPTERS[-1].name


SENSITIVE_TERMS = ("gender", "ethnicity", "disability", "salary", "consent", "agree", "declaration", "visa", "sponsorship", "authorization")
FACT_ALIASES = {
    "full name": ("full name", "name", "your name"),
    "email": ("email", "email address"),
    "phone": ("phone", "telephone", "mobile", "contact number"),
    "linkedin": ("linkedin",),
    "github": ("github",),
    "portfolio": ("portfolio", "website", "personal site"),
    "current course": ("course", "degree", "programme", "program"),
}


def normalize(value: str) -> str:
    return " ".join(value.lower().replace("_", " ").replace("-", " ").split())


def map_verified_facts(
    fields: list[InspectedField],
    facts: list[dict],
    retrieve: Callable[[str, str], object | None] | None = None,
) -> list[FormField]:
    mapped: list[FormField] = []
    for field in fields:
        label = normalize(f"{field.label} {field.name}")
        if any(term in label for term in SENSITIVE_TERMS):
            mapped.append(FormField(field.label, field.name, field.field_type, field.required, reason="Sensitive or declarative field left for your review."))
            continue
        match = next(
            (
                fact for fact in facts
                if any(alias in label for alias in FACT_ALIASES.get(normalize(fact["label"]), (normalize(fact["label"]),)))
            ),
            None,
        )
        if match:
            mapped.append(FormField(
                field.label, field.name, field.field_type, field.required, match["value"], 0.96,
                "verified_fact", match["label"], "Mapped from a verified profile fact.",
            ))
            continue
        retrieved = retrieve(field.label, field.field_type) if retrieve else None
        if retrieved:
            mapped.append(FormField(
                field.label, field.name, field.field_type, field.required,
                retrieved.value, retrieved.confidence, retrieved.source_kind, retrieved.source_reference, retrieved.reason,
            ))
            continue
        mapped.append(FormField(field.label, field.name, field.field_type, field.required, reason="No grounded local answer matched this field."))
    return mapped

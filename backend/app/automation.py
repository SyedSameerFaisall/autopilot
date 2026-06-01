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


def normalize(value: str) -> str:
    return " ".join(value.lower().replace("_", " ").replace("-", " ").split())


def map_memory_answers(
    fields: list[InspectedField],
    answer: Callable[[list[InspectedField]], dict[int, object]],
) -> list[FormField]:
    safe_fields = [field for field in fields if not any(term in normalize(f"{field.label} {field.name}") for term in SENSITIVE_TERMS)]
    generated = answer(safe_fields)
    generated_index = 0
    mapped: list[FormField] = []
    for field in fields:
        label = normalize(f"{field.label} {field.name}")
        if any(term in label for term in SENSITIVE_TERMS):
            mapped.append(FormField(field.label, field.name, field.field_type, field.required, reason="Sensitive or declarative field left for your review."))
            continue
        retrieved = generated.get(generated_index)
        generated_index += 1
        if retrieved:
            mapped.append(FormField(
                field.label, field.name, field.field_type, field.required,
                retrieved.value, retrieved.confidence, "llm_memory", retrieved.source_reference,
                f"AI-generated from your stored memory. Evidence: {retrieved.evidence}",
            ))
            continue
        mapped.append(FormField(field.label, field.name, field.field_type, field.required, reason="AI could not find a supported answer in your stored memory."))
    return mapped

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlparse


@dataclass(frozen=True)
class FormField:
    label: str
    field_type: str
    required: bool
    value: str | None = None
    confidence: float = 0.0


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

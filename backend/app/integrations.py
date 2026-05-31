from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class OpportunityRecord:
    title: str
    organization: str
    category: str
    source: str
    source_url: str
    summary: str


class OpportunityAdapter(Protocol):
    name: str

    def fetch(self) -> list[OpportunityRecord]: ...


class CuratedOpportunityAdapter:
    """Live scraping is intentionally opt-in; adapters expose one stable boundary."""

    def __init__(self, name: str) -> None:
        self.name = name

    def fetch(self) -> list[OpportunityRecord]:
        return []


OPPORTUNITY_ADAPTERS: tuple[OpportunityAdapter, ...] = (
    CuratedOpportunityAdapter("Devpost"),
    CuratedOpportunityAdapter("Luma"),
    CuratedOpportunityAdapter("MLH"),
)


@dataclass(frozen=True)
class OAuthProvider:
    name: str
    client_id_env: str
    client_secret_env: str | None
    scopes: tuple[str, ...]

    @property
    def configured(self) -> bool:
        has_id = bool(os.getenv(self.client_id_env))
        has_secret = not self.client_secret_env or bool(os.getenv(self.client_secret_env))
        return has_id and has_secret


EMAIL_PROVIDERS = {
    "gmail": OAuthProvider(
        name="gmail",
        client_id_env="APPLYPILOT_GMAIL_CLIENT_ID",
        client_secret_env="APPLYPILOT_GMAIL_CLIENT_SECRET",
        scopes=("https://www.googleapis.com/auth/gmail.readonly",),
    ),
    "microsoft": OAuthProvider(
        name="microsoft",
        client_id_env="APPLYPILOT_MICROSOFT_CLIENT_ID",
        client_secret_env=None,
        scopes=("Mail.Read", "offline_access"),
    ),
}

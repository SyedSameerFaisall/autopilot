from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from playwright.sync_api import BrowserContext, Page, sync_playwright

from .database import DATA_DIR

PROFILE_DIR = DATA_DIR / "browser-profile"


@dataclass(frozen=True)
class InspectedField:
    label: str
    name: str
    field_type: str
    required: bool


def inspect_page(page: Page) -> list[InspectedField]:
    raw_fields: list[dict[str, Any]] = page.locator("input, textarea, select").evaluate_all(
        """elements => elements.map(element => ({
          label: element.labels?.[0]?.innerText || element.getAttribute('aria-label') || element.name || element.id || 'Unlabelled field',
          name: element.name || element.id || '',
          field_type: element.tagName.toLowerCase() === 'textarea' ? 'textarea' : (element.type || element.tagName.toLowerCase()),
          required: Boolean(element.required || element.getAttribute('aria-required') === 'true')
        }))"""
    )
    return [InspectedField(**field) for field in raw_fields]


class PersistentBrowserWorker:
    """Visible, user-controlled Playwright browser context for preparation sessions."""

    def __init__(self, profile_dir: Path = PROFILE_DIR, headless: bool = False) -> None:
        self.profile_dir = profile_dir
        self.headless = headless
        self._playwright: Any | None = None
        self.context: BrowserContext | None = None

    def start(self) -> BrowserContext:
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self._playwright = sync_playwright().start()
        self.context = self._playwright.chromium.launch_persistent_context(
            str(self.profile_dir),
            headless=self.headless,
        )
        return self.context

    def inspect(self, url: str) -> list[InspectedField]:
        context = self.context or self.start()
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(url, wait_until="domcontentloaded")
        return inspect_page(page)

    def close(self) -> None:
        if self.context:
            self.context.close()
            self.context = None
        if self._playwright:
            self._playwright.stop()
            self._playwright = None

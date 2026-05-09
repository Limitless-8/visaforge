"""
ingestion/playwright_provider.py
--------------------------------
PLACEHOLDER provider. Not active in the MVP.

Use Playwright when a target site requires JS rendering, cookie handling,
or multi-step navigation that simpler providers cannot do.

To activate:
1. Uncomment `playwright` in requirements.txt, then `playwright install`.
2. Replace this scaffold's body with the real implementation.
3. Set INGESTION_PROVIDER=playwright.
"""

from __future__ import annotations

from ingestion.base import IngestionProvider
from ingestion.parser import extract_scholarships
from models.schemas import IngestionResult


class PlaywrightProvider(IngestionProvider):
    name = "playwright"

    def is_available(self) -> bool:
        # Return False until activated.
        try:
            import playwright  # noqa: F401
            return True
        except ImportError:
            return False

    def fetch(self, url: str, *, country: str = "UK") -> IngestionResult:
        # --- Scaffolded implementation ---
        # from playwright.sync_api import sync_playwright
        # with sync_playwright() as p:
        #     browser = p.chromium.launch(headless=True)
        #     page = browser.new_page(user_agent="VisaForgeBot/0.1 (...)")
        #     page.goto(url, wait_until="networkidle", timeout=30000)
        #     html = page.content()
        #     browser.close()
        # from bs4 import BeautifulSoup
        # text = BeautifulSoup(html, "lxml").get_text("\n", strip=True)
        # entries = extract_scholarships(url=url, country=country, text=text)
        # return IngestionResult(source_url=url, success=True,
        #                        raw_text=text[:20000], entries=entries,
        #                        provider=self.name)
        return IngestionResult(
            source_url=url,
            success=False,
            error="PlaywrightProvider is a placeholder — not yet implemented.",
            provider=self.name,
        )

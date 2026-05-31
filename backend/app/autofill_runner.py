from __future__ import annotations

import json
import sys
from pathlib import Path

from .browser_worker import PersistentBrowserWorker, fill_page


def write_state(path: Path, **values: object) -> None:
    path.write_text(json.dumps(values), encoding="utf-8")


def main(payload_path: str) -> None:
    payload = json.loads(Path(payload_path).read_text(encoding="utf-8"))
    state_path = Path(payload["state_path"])
    screenshot_path = Path(payload["screenshot_path"])
    worker = PersistentBrowserWorker(profile_dir=Path(payload["profile_dir"]))
    try:
        context = worker.start()
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(payload["source_url"], wait_until="domcontentloaded")
        result = fill_page(page, payload["fields"])
        screenshot_path.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(screenshot_path), full_page=True)
        write_state(state_path, status="filled", screenshot_path=str(screenshot_path), **result)
        page.bring_to_front()
        while context.pages:
            page.wait_for_timeout(1000)
    except Exception as exc:  # Runner reports startup failures, but a user closing Chromium is normal.
        if not state_path.exists():
            write_state(state_path, status="failed", error=str(exc))
    finally:
        worker.close()


if __name__ == "__main__":
    main(sys.argv[1])

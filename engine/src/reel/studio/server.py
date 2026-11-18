"""`reel studio`: serve the API and the built web app on 127.0.0.1 only (NFR-4)."""

from __future__ import annotations

import webbrowser
from pathlib import Path

HOST = "127.0.0.1"


def serve(port: int = 8765, open_browser: bool = False, dev: bool = False, projects: str | None = None) -> int:
    import uvicorn

    from reel.studio.app import create_app
    from reel.studio.settings import Settings

    settings = Settings(dev=dev)
    if projects:
        settings.projects_root = Path(projects).expanduser().resolve()
    app = create_app(settings)
    url = f"http://{HOST}:{port}/?token={app.state.token}"
    print(f"Reel Studio: {url}")
    print(f"projects: {settings.projects_root}")
    if open_browser:
        webbrowser.open(url)
    uvicorn.run(app, host=HOST, port=port, log_level="warning")
    return 0

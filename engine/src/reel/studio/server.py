"""`reel studio`: serve the API and the built web app on 127.0.0.1 only (NFR-4)."""

from __future__ import annotations

import webbrowser
from pathlib import Path

HOST = "127.0.0.1"
LAUNCHER_LABEL = "com.reel.studio"


LAUNCHER_ENV = ("PATH", "SSL_CERT_FILE", "REEL_PROJECTS_ROOT", "REEL_CONFIG_DIR", "REEL_MODEL_DIR", "HOME", "LANG")


def launcher_plist(python: str, port: int, projects: str | None, log: Path, *, env: dict[str, str] | None = None,
                   cwd: Path | None = None) -> str:
    """A macOS LaunchAgent that keeps `reel studio` running at login (UI plan E1). It still binds 127.0.0.1 only;
    sharing outside this Mac (E3) stays a separate owner decision. launchd starts with a bare PATH and no
    SSL_CERT_FILE, so the install-time values are written in: jobs need `claude`, `node`/`npx` and the CA bundle."""
    import plistlib

    data = {"Label": LAUNCHER_LABEL,
            "ProgramArguments": [python, "-m", "reel.cli", "studio", "--port", str(port), *(["--projects", projects] if projects else [])],
            "RunAtLoad": True, "KeepAlive": True, "StandardOutPath": str(log), "StandardErrorPath": str(log)}
    if env:
        data["EnvironmentVariables"] = dict(env)
    if cwd:
        data["WorkingDirectory"] = str(cwd)
    return plistlib.dumps(data).decode()


def install_launcher(port: int = 8765, projects: str | None = None, *, home: Path | None = None, load: bool = True) -> Path:
    import subprocess
    import sys

    home = home or Path.home()
    plist = home / "Library" / "LaunchAgents" / f"{LAUNCHER_LABEL}.plist"
    log = home / "Library" / "Logs" / "reel-studio.log"
    plist.parent.mkdir(parents=True, exist_ok=True)
    log.parent.mkdir(parents=True, exist_ok=True)
    import os

    from reel import config

    env = {k: os.environ[k] for k in LAUNCHER_ENV if os.environ.get(k)}
    plist.write_text(launcher_plist(sys.executable, port, str(Path(projects).expanduser().resolve()) if projects else None, log,
                                    env=env, cwd=config.REPO_ROOT))
    if load:
        subprocess.run(["launchctl", "unload", str(plist)], capture_output=True)
        subprocess.run(["launchctl", "load", "-w", str(plist)], check=True, capture_output=True)
    return plist


def uninstall_launcher(*, home: Path | None = None, unload: bool = True) -> bool:
    import subprocess

    plist = (home or Path.home()) / "Library" / "LaunchAgents" / f"{LAUNCHER_LABEL}.plist"
    if not plist.exists():
        return False
    if unload:
        subprocess.run(["launchctl", "unload", "-w", str(plist)], capture_output=True)
    plist.unlink()
    return True


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

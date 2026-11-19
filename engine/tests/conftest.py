import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


@pytest.fixture(autouse=True)
def _private_config_dir(tmp_path_factory):
    """Tests never read or append to the owner's ~/.config/reel (licence ledger, subscriptions).
    Plain os.environ, not monkeypatch: an autouse monkeypatch would be torn down last and change other
    fixtures' teardown order (test_voice_enhance clears a cache on a function the test patched)."""
    old = os.environ.get("REEL_CONFIG_DIR")
    os.environ["REEL_CONFIG_DIR"] = str(tmp_path_factory.mktemp("reel_config"))
    yield
    if old is None:
        os.environ.pop("REEL_CONFIG_DIR", None)
    else:
        os.environ["REEL_CONFIG_DIR"] = old

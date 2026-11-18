import yaml

from reel import capability_status, config, knowledge


def test_library_lists_every_node_and_capability(tmp_path):
    files = knowledge.library_files()
    idx = files["index.md"]
    for nid in knowledge.node_ids():
        assert f"`{nid}`" in idx
    caps = yaml.safe_load((config.KNOWLEDGE_DIR / "capabilities.yaml").read_text())["capabilities"]
    for c in caps:
        assert f"`{c['id']}`" in files["capabilities.md"]
    # every status entry names a real capability (no stale ids)
    assert set(capability_status.STATUS) <= {c["id"] for c in caps}


def test_unknown_capability_is_no():
    assert capability_status.status("cap.nope")[0] == "no"

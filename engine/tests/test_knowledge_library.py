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


def test_index_line_numbers_point_at_each_node():
    import re

    files = knowledge.library_files()
    refs = re.findall(r"- `([^`]+)` L(\d+)", files["index.md"])
    assert len(refs) == len(knowledge.node_ids())
    for nid, line in refs:
        assert any(body.split("\n")[int(line) - 1:int(line)] == [f"### `{nid}`"] for name, body in files.items() if name not in ("index.md", "capabilities.md")), nid

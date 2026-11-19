"""Licence registry, gate and manifest (reel.licences, docs/product/asset-library-plan.md)."""

from __future__ import annotations

import datetime as dt
import json

import pytest

from reel import assets, licences, package, validate
from reel.brief import Brief
from reel.decide import _allowed
from reel.schemas.timeline import Asset, AssetKind, AudioClip, GraphicEvent, PipEvent, Provenance, Timeline, VideoClip

PIXABAY_SNAPSHOT = "Pixabay Content License — free commercial use, no attribution required; no redistribution of unmodified clips"
CC_BY_CREDIT = '"Carefree" Kevin MacLeod (incompetech.com)'


@pytest.fixture(scope="module")
def reg():
    return licences.load_registry()


def _use(**kw) -> licences.UseContext:
    return licences.UseContext(**{"client": "Acme", "project": "p1", **kw})


def _r(reg, meta, use=None, **kw):
    return [c for c, _m in licences.refusals("a1", meta, reg, use or _use(), subs=kw.get("subs", {}), ledger=kw.get("ledger", {}))]


def test_registry_loads_and_every_committed_asset_has_a_licence(reg):
    assert {"owned", "cc0-1.0", "cc-by-4.0", "pexels", "pixabay-content", "client-supplied"} <= set(reg.licences)
    c = licences.census()
    assert c["unresolved"] == [] and c["stamped"] == 0  # the committed indexes are backfilled
    assert c["by_licence"]["cc-by-4.0"]["music"] == 33 and sum(c["by_licence"]["cc0-1.0"].values()) == 205


def test_resolution_order_id_then_licence_text_then_pack(reg):
    assert reg.resolve({"licence_id": "cc0-1.0", "license": "whatever"}).id == "cc0-1.0"
    assert reg.resolve({"licence_id": "nope"}) is None  # a wrong explicit id never falls through
    assert reg.resolve({"license": PIXABAY_SNAPSHOT}).id == "pixabay-content"  # old timeline snapshots still resolve
    assert reg.resolve({"license": "Pexels License — free commercial use"}).id == "pexels"
    assert reg.resolve({"license": "client-supplied"}).id == "client-supplied"
    assert reg.resolve({"source": "Kenney UI Audio"}).id == "cc0-1.0" and reg.notice({"source": "Kenney UI Audio"}) == "kenney-ui-audio.txt"
    assert reg.resolve({"license": "mystery licence"}) is None


def test_clean_assets_pass(reg):
    assert _r(reg, {"license": "CC0-1.0"}) == []
    assert _r(reg, {"license": "CC-BY-4.0", "attribution": CC_BY_CREDIT}) == []
    assert _r(reg, {"license": PIXABAY_SNAPSHOT}) == []


def test_blocked_and_unknown(reg):
    assert _r(reg, {"license": "CC-BY-NC-4.0"}) == ["blocked_licence"]
    assert _r(reg, {"license": "Sonniss GDC 2024 — royalty free"}) == ["blocked_licence"]  # on hold until Sonniss answers
    assert _r(reg, {}) == ["no_licence"]


def test_political_brief_refuses_pixabay_but_not_cc0(reg):
    use = _use(categories=frozenset({"political"}))
    assert _r(reg, {"license": PIXABAY_SNAPSHOT}, use) == ["sensitive_use"]
    assert _r(reg, {"licence_id": "pixabay-content"}, use) == ["sensitive_use"]
    assert _r(reg, {"license": "CC0-1.0"}, use) == []
    assert _r(reg, {"license": "CC0-1.0", "sensitive_use": ["political"]}, use) == ["sensitive_use"]  # a per-asset flag


def test_editorial_platform_and_registration(reg):
    assert _r(reg, {"license": "CC0-1.0", "editorial_only": True}) == ["editorial_only"]
    assert _r(reg, {"license": "CC0-1.0", "editorial_only": True}, _use(purpose="editorial")) == []
    assert _r(reg, {"license": "CC0-1.0", "allowed_platforms": ["platform.youtube_shorts"]}) == ["platform_not_allowed"]
    reg2 = licences.Registry({**reg.licences, "envato": licences.Licence(id="envato", title="Envato", family="subscription",
                                                                           per_project_registration=True, aliases=["^Envato"])},
                             reg.sources, reg.root)
    assert _r(reg2, {"license": "Envato Elements"}) == ["registration_missing"]
    assert _r(reg2, {"license": "Envato Elements", "registrations": [{"project": "p1", "id": "ENV-1"}]}) == []


def test_subscription_must_be_active(reg):
    meta = {"licence_id": "epidemic-pro"}
    today = dt.date(2026, 11, 19)
    use = _use(today=today)
    assert _r(reg, meta, use) == ["subscription_inactive"]
    assert _r(reg, meta, use, subs={"epidemic": {"active_until": "2026-12-31"}}) == []
    assert _r(reg, meta, use, subs={"epidemic": {"active_until": "2026-11-18"}}) == ["subscription_inactive"]


def test_cc_by_needs_a_credit_and_a_client_who_accepts_it(reg):
    assert _r(reg, {"license": "CC-BY-4.0"}) == ["attribution_missing"]
    assert _r(reg, {"license": "CC-BY-4.0", "attribution": CC_BY_CREDIT}, _use(accept_credits=False)) == ["credit_refused"]


def test_single_client_ledger(reg, tmp_path):
    meta = {"license": "client-supplied", "sha256": "abc"}
    assert _r(reg, meta) == []
    licences.record_use([{"key": "abc", "id": "b_1", "licence_id": "client-supplied"}], _use(client="Acme"))
    licences.record_use([{"key": "abc", "id": "b_1", "licence_id": "client-supplied"}], _use(client="Acme"))  # repackaging: no new entry
    assert len(licences.ledger_file().read_text().splitlines()) == 1
    ledger = licences.load_ledger()
    assert _r(reg, meta, _use(client="Acme"), ledger=ledger) == []  # the same client again
    assert _r(reg, meta, _use(client="Globex"), ledger=ledger) == ["single_client"]
    assert _r(reg, meta, _use(client=None), ledger=ledger) == ["single_client"]  # an unnamed client is not Acme
    assert _r(reg, {"license": "CC0-1.0", "sha256": "abc"}, _use(client="Globex"), ledger=ledger) == []  # CC0 is reusable


def test_ledger_and_subscriptions_live_in_the_test_config_dir(tmp_path):
    assert "reel_config" in str(licences.ledger_file()) and ".config/reel" not in str(licences.ledger_file())


def test_brief_fields_default_to_permissive_and_validate():
    b = Brief(project="x")
    assert b.use_categories == [] and b.purpose == "promo" and b.accept_credits is True
    with pytest.raises(ValueError):
        Brief(project="x", use_categories=["politics"])
    with pytest.raises(ValueError):
        Brief(project="x", purpose="ads")
    use = licences.UseContext.from_brief(Brief(project="x", client="Acme", use_categories=["political"], accept_credits=False), "p9")
    assert use.categories == {"political"} and not use.accept_credits and use.client == "Acme" and use.project == "p9"


def _idx() -> assets.Indexes:
    return assets.Indexes(
        sfx={"s_cc0": {"id": "s_cc0", "license": "CC0-1.0", "source": "Kenney UI Audio", "file": "/x/s.wav"}},
        music={"m_by": {"id": "m_by", "license": "CC-BY-4.0", "attribution": CC_BY_CREDIT, "source": "Incompetech (Kevin MacLeod)"}},
        broll={"b_px": {"id": "b_px", "license": PIXABAY_SNAPSHOT, "source": "Pixabay", "file": "broll/mezz/b_px.mov",
                        "credit": "U7 (https://pixabay.com/videos/7/)"},
               "b_own": {"id": "b_own", "license": "client-supplied", "source": "client", "file": "broll/mezz/b_own.mov"}},
        lottie={"lt_1": {"id": "lt_1", "license": "owned", "source": "reel procedural"}})


PROV = Provenance(item="k1", words=[0, 3])


def _timeline(pip: bool = True) -> Timeline:
    return Timeline(fps="25/1", width=1080, height=1920, duration_f=100,
                    assets={"c01": Asset(id="c01", kind=AssetKind.video, uri="mezz/c01.mov"),
                            "s_cc0": Asset(id="s_cc0", kind=AssetKind.sfx, uri="/x/s.wav", license="CC0-1.0"),
                            "m_by": Asset(id="m_by", kind=AssetKind.music, uri="/x/m.wav", license="CC-BY-4.0", attribution=CC_BY_CREDIT),
                            "b_own": Asset(id="b_own", kind=AssetKind.video, uri="broll/mezz/b_own.mov", license="client-supplied")},
                    video=[VideoClip(id="v0", asset="c01", at_f=0, dur_f=100, src_in_us=0, src_out_us=4_000_000, src=PROV),
                           VideoClip(id="br_k1", asset="b_own", at_f=10, dur_f=20, src_in_us=0, src_out_us=800_000, src=PROV)],
                    audio=[AudioClip(id="music", asset="m_by", at_f=0, dur_f=100, role="music"),
                           AudioClip(id="sfx1", asset="s_cc0", at_f=5, dur_f=5, role="sfx")],
                    pips=[PipEvent(id="p1", uri="broll/mezz/b_px.mov", start_f=40, end_f=60)] if pip else [],
                    graphics=[GraphicEvent(id="g1", kind="lottie", start_f=70, end_f=90, uri="lt_1")])


def test_gate_sees_every_library_asset_including_pips_and_lottie(reg):
    res = licences.gate(_timeline(), _idx(), _use(), reg)
    assert res.ok
    kinds = {i["id"]: (i["kind"], i["licence_id"], i["where"]) for i in res.items}
    assert kinds == {"m_by": ("music", "cc-by-4.0", ["music"]), "s_cc0": ("sfx", "cc0-1.0", ["sfx1"]),
                     "b_own": ("broll", "client-supplied", ["br_k1"]), "b_px": ("broll", "pixabay-content", ["p1"]),
                     "lt_1": ("lottie", "owned", ["g1"])}
    assert "c01" not in kinds  # the client's own footage is not a library asset


def test_gate_refuses_a_pixabay_pip_for_a_political_client(reg):
    res = licences.gate(_timeline(), _idx(), _use(categories=frozenset({"political"})), reg)
    assert not res.ok and [p.split(" ")[0] for p in res.problems()] == ["b_px"]
    with pytest.raises(licences.LicenceRefused, match="b_px"):
        raise licences.LicenceRefused(res)
    assert licences.gate(_timeline(pip=False), _idx(), _use(categories=frozenset({"political"})), reg).ok


def test_gate_uses_the_snapshot_when_the_library_moved(reg):
    idx = _idx()
    idx.music.clear()  # the music library is not on this machine: the compile-time snapshot still names the licence
    res = licences.gate(_timeline(pip=False), idx, _use(), reg)
    assert res.ok and next(i for i in res.items if i["id"] == "m_by")["licence_id"] == "cc-by-4.0"


def test_menus_leave_refused_assets_out_and_validation_names_the_reason(reg):
    idx = _idx()
    idx.refused = licences.refused(idx, _use(categories=frozenset({"political"}), accept_credits=False), reg)
    assert set(idx.refused) == {"b_px", "m_by"}
    assert set(_allowed(idx, idx.broll)) == {"b_own"} and _allowed(idx, idx.music) == {}
    issues = validate._refused(idx, "b_px", "broll[0].asset", "B-roll")
    assert issues[0].code == "licence_refused" and "political" in issues[0].message
    assert validate._refused(idx, "b_own", "broll[1].asset", "B-roll") == []


def test_credits_now_include_pip_broll(reg):
    from reel import library

    lines = library.credit_lines(_timeline(), _idx())
    assert lines == [CC_BY_CREDIT, "U7 (https://pixabay.com/videos/7/)"]


def test_manifest_records_assets_licences_and_text_hashes(reg, tmp_path):
    reel = tmp_path / "final.mp4"
    reel.write_bytes(b"REEL")
    (tmp_path / "broll" / "mezz").mkdir(parents=True)
    (tmp_path / "broll" / "mezz" / "b_px.mov").write_bytes(b"PX")
    res = licences.gate(_timeline(), _idx(), _use(), reg)
    path = licences.write_manifest(tmp_path / "pkg", res, tmp_path, reg=reg, reel=reel, credits=[CC_BY_CREDIT])
    m = json.loads(path.read_text())
    assert m["client"] == "Acme" and m["purpose"] == "promo" and m["credits_required"] == [CC_BY_CREDIT]
    import hashlib

    assert m["reel"]["sha256"] == hashlib.sha256(b"REEL").hexdigest()
    assert set(m["licences"]) == {"cc-by-4.0", "cc0-1.0", "client-supplied", "pixabay-content", "owned"}
    by = {a["id"]: a for a in m["assets"]}
    assert by["b_px"]["file_sha256"] and by["b_px"]["used_in"] == ["p1"] and by["s_cc0"]["pack_notice"] == "kenney-ui-audio.txt"
    files = {p.name for p in path.parent.iterdir()}
    assert {"cc-by-4.0-legalcode.txt", "cc0-1.0-legalcode.txt", "kenney-ui-audio.txt", "manifest.json"} <= files
    assert m["licences"]["pixabay-content"]["text"] is None and m["licences"]["pixabay-content"]["text_kind"] == "missing"
    assert m["licences"]["cc0-1.0"]["text_sha256"] and m["registry_sha256"] == reg.sha256


def test_package_refuses_and_clears_stale_proof(reg, tmp_path):
    from reel.workspace import Workspace

    ws = Workspace.create(tmp_path / "proj")
    stale = ws.path("export", "package", "licences")
    stale.mkdir(parents=True)
    (stale / "manifest.json").write_text("{}")
    res = licences.gate(_timeline(), _idx(), _use(categories=frozenset({"political"})), reg)
    with pytest.raises(licences.LicenceRefused):
        package.build(ws, _timeline(), None, None, None, _idx(), gate=res)
    assert not stale.exists()


def test_package_hash_follows_brief_and_subscriptions(tmp_path):
    brief = tmp_path / "brief.json"
    brief.write_text(json.dumps({"project": "x"}))
    a = licences.fingerprint(brief)
    brief.write_text(json.dumps({"project": "x", "use_categories": ["political"]}))
    b = licences.fingerprint(brief)
    licences.subscriptions_file().parent.mkdir(parents=True, exist_ok=True)
    licences.subscriptions_file().write_text(json.dumps({"epidemic": {"active_until": "2027-01-01"}}))
    assert len({a, b, licences.fingerprint(brief)}) == 3

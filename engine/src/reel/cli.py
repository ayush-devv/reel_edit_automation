"""`reel` command line."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path


def _cmd_doctor(args: argparse.Namespace) -> int:
    from reel import doctor

    report = doctor.check()
    for item in report["items"]:
        mark = "ok " if item["ok"] else ("MISSING" if item["required"] else "warn")
        print(f"[{mark:7}] {item['name']}: {item['detail']}")
    print("\nresult:", "PASS" if report["ok"] else "FAIL")
    return 0 if report["ok"] else 1


def _cmd_probe(args: argparse.Namespace) -> int:
    from reel.probe import probe

    print(probe(Path(args.file)).model_dump_json(indent=2))
    return 0


def _print_state(state: dict, ws) -> None:
    for name, entry in state["stages"].items():
        print(f"{name:10} {entry['status']:7} {json.dumps(entry.get('meta', {}), ensure_ascii=False)}")
    print(f"\nworkspace: {ws.root}")
    if ws.path("export", "reel.mp4").exists():
        print(f"reel: {ws.path('export', 'reel.mp4')}")


CARRIED_OPTIONS = ("deliverables",)


def _print_checkin(ws) -> None:
    from reel import checkin

    c = checkin.load(ws)
    if not c or c.get("status") != "open":
        return
    print(f"\nStory check-in — {c['summary']} ({c['total_s']} s)\nHook: “{c['hook']['text']}”")
    for line in c["lines"]:
        print(f"  {line['id']:6} {line['seconds']:5.1f} s  {line['beat']:8} {line['text']}")
    for w in c["warnings"]:
        print(f"warning: {w}")
    for q in c["questions"]:
        print(f"  [{q['id']}] {q['text']}")
    print(f"\nanswer with `reel checkin --project {ws.root} [--yes q1,q2] [--note \"…\"] --continue`")


def _cmd_checkin(args: argparse.Namespace) -> int:
    """3a.1: answer the story check-in (accepted question ids, an optional note), then optionally finish the edit."""
    from reel import autofix, checkin, decide
    from reel.stages import CLIP_PIPELINE, EDIT_PIPELINE
    from reel.workspace import Workspace

    ws = Workspace(Path(args.project).resolve())
    options = json.loads(ws.path("run_options.json").read_text()) if ws.path("run_options.json").exists() else {}
    if not args.yes and not args.note and not args.approve and not args.cont:
        _print_checkin(ws)
        return 0
    try:
        res = checkin.answer(ws, decide.load_inputs(ws, options.get("brief"), options.get("brand")),
                             [x.strip() for x in (args.yes or "").split(",") if x.strip()], args.note)
    except checkin.CheckinError as exc:
        print(f"not applied: {exc}")
        return 1
    print(f"story approved ({', '.join(res['applied']) or 'as it was'})")
    if args.cont:
        stages = CLIP_PIPELINE if ws.path("window.json").exists() else EDIT_PIPELINE
        out = autofix.run(ws, stages, options)
        _print_state(out["state"], ws)
        _print_verdict(ws, out["loops"])
    return 0


def _run_child(args: argparse.Namespace) -> int:
    """A Clip Factory reel project: edit stages only, on the source's shared analysis (reel.clipfactory)."""
    from reel import autofix
    from reel.runner import run_pipeline
    from reel.stages import CLIP_PIPELINE, edit
    from reel.workspace import Workspace

    ws = Workspace(Path(args.project).resolve())
    options = json.loads(ws.path("run_options.json").read_text())
    options["skip_review"] = bool(getattr(args, "skip_review", False)) or bool(options.get("skip_review"))
    if getattr(args, "story_checkin", False):
        state = run_pipeline(ws, edit.checkin_pipeline(CLIP_PIPELINE), options=options)
        _print_state(state, ws)
        _print_checkin(ws)
        return 0
    res = autofix.run(ws, CLIP_PIPELINE, options, force=set(getattr(args, "force", None) or []))
    _print_state(res["state"], ws)
    _print_verdict(ws, res["loops"])
    return 0


def _cmd_gold(args: argparse.Namespace) -> int:
    """3b.5: add one gold pair (raw + the pro's final), checked to belong together."""
    from reel.evalh import gold_add

    try:
        r = gold_add.add_pair(Path(args.raw).expanduser().resolve(), Path(args.final).expanduser().resolve(), language=args.language,
                              split=args.split, genre=args.genre, channel=args.channel, pair_id=args.id, check=not args.no_check)
    except gold_add.GoldError as exc:
        print(f"not added: {exc}")
        return 1
    print(f"added {r['id']} ({r['duration_s']} s, match {r['match'] if r['match'] is not None else 'not checked'}) · "
          f"{r['pairs']} gold pairs, {r['hindi_hinglish']} Hindi/Hinglish")
    if r.get("warning"):
        print(f"warning: {r['warning']}")
    return 0


def _cmd_listen(args: argparse.Namespace) -> int:
    """G2.5: render the blind listening set, or print its result."""
    from reel import listen

    try:
        if args.listen_cmd == "prepare":
            m = listen.prepare(args.set)
            for gid, g in m["generators"].items():
                print(f"{gid:32} {g['status']}" + (f": {g['why']}" if g.get("why") else "") + (f" ({len(g['failures'])} failed)" if g.get("failures") else ""))
            print(f"{len(m['outputs'])} file(s); listen in Reel Studio → Quality lab → Listening test")
            return 0
        print(json.dumps(listen.summary(args.set), indent=2, ensure_ascii=False))
        return 0
    except (listen.ListenError, FileNotFoundError) as exc:
        print(f"not done: {exc}")
        return 1


def _cmd_factory(args: argparse.Namespace) -> int:
    from reel import clipfactory, mine
    from reel.workspace import Workspace

    ws = Workspace(Path(args.project).resolve())
    data = mine.load(ws)
    if not data:
        print(f"{ws.root} has no candidates: run `reel run <recording> --project {ws.root} --mine` first")
        return 2
    if not args.make:
        print(ws.path("mine", "board.md").read_text())
        return 0
    try:
        made = clipfactory.spawn(ws, [x.strip() for x in args.make.split(",") if x.strip()])
    except ValueError as exc:
        print(f"not made: {exc}")
        return 1
    for root in made:
        print(f"reel project: {root}")
    if args.run:
        for root in made:
            _run_child(argparse.Namespace(project=str(root), skip_review=args.skip_review, force=None))
    else:
        print("edit each with `reel run --project <reel project>`")
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    from reel.runner import run_pipeline
    from reel.stages import EDIT_PIPELINE, PIPELINE
    from reel.workspace import Workspace, atomic_write_json

    if not args.input:
        if args.project and (Path(args.project) / "window.json").exists():
            return _run_child(args)
        print("give an input clip or folder (only a Clip Factory reel project runs without one)")
        return 2
    src = Path(args.input).resolve()
    project = Path(args.project).resolve() if args.project else Path.cwd() / "projects" / src.stem
    ws = Workspace.create(project)
    absolute = lambda p: str(Path(p).resolve()) if p else None  # noqa: E731
    options = {"input": str(src), "fps": args.fps, "encoder": args.encoder, "language": args.language,
               "brief": absolute(args.brief), "brand": absolute(args.brand), "asr_repo": args.asr_repo, "skip_visual": args.skip_visual,
               "broll": absolute(args.broll), "reference": absolute(args.reference), "stock": bool(args.stock)}
    options["skip_review"] = args.skip_review
    options["voice_enhance"] = not args.no_voice_enhance
    if getattr(args, "clip_length", None):
        lo, _, hi = args.clip_length.partition("-")
        options["clip_target_s"] = [float(lo), float(hi)]
    prev = ws.path("run_options.json")
    if prev.exists():  # options set outside `reel run` (Reel Studio's extra deliverables) survive a re-run
        carried = {k: v for k, v in json.loads(prev.read_text()).items() if k in CARRIED_OPTIONS}
        options = {**carried, **options}
    atomic_write_json(ws.path("run_options.json"), options)  # `reel revise` / `reel proof` reuse them
    if getattr(args, "story_checkin", False):  # 3a.1: stop after the story pass; `reel checkin` answers and continues
        from reel.stages import edit

        state = run_pipeline(ws, edit.checkin_pipeline(EDIT_PIPELINE), options=options, force=set(args.force or []))
        _print_state(state, ws)
        _print_checkin(ws)
        return 0
    if getattr(args, "mine", False):  # Clip Factory: analyse the long recording once, then find the reels in it
        from reel.stages import MINE_PIPELINE

        state = run_pipeline(ws, MINE_PIPELINE, options=options, force=set(args.force or []))
        _print_state(state, ws)
        board = ws.path("mine", "board.md")
        if board.exists():
            print("\n" + board.read_text())
            print(f"make reels with `reel factory --project {ws.root} --make c01,c02 [--run]`")
        return 0
    if args.analyse_only:
        state = run_pipeline(ws, PIPELINE, options=options, force=set(args.force or []))
        _print_state(state, ws)
        return 0
    if getattr(args, "preview_first", False):  # stop after the two hook previews; `reel preview-choose` continues
        from reel.stages import edit

        state = run_pipeline(ws, [*PIPELINE, *edit.preview_pipeline()], options=options, force=set(args.force or []))
        _print_state(state, ws)
        pv = ws.path("export", "preview", "preview.json")
        if pv.exists():
            print(f"\nhook previews: {', '.join(json.loads(pv.read_text())['options'])} in {pv.parent} — pick with "
                  f"`reel preview-choose --project {ws.root} --option A|B`")
        return 0
    from reel import autofix

    res = autofix.run(ws, EDIT_PIPELINE, options, force=set(args.force or []))
    _print_state(res["state"], ws)
    _print_verdict(ws, res["loops"])
    return 0


def _print_verdict(ws, loops: list | None = None) -> None:
    v = ws.path("qa", "verdict.md")
    if loops and len(loops) > 1:
        print("\nfix loops: " + " → ".join(f"{h['status']}" + (f" (revised: {h['revision']})" if h.get("revision") else "") for h in loops))
    if v.exists():
        print("\n" + v.read_text().split("## Gates")[0].strip())
        print(f"\nfull report: {v}")


def _cmd_licences(args: argparse.Namespace) -> int:
    """Licence census of the libraries; --backfill stamps licence ids; --brief shows what that brief refuses."""
    from reel import assets, licences
    from reel.brief import load_brief

    c = licences.census(write=args.backfill)
    for lid, kinds in sorted(c["by_licence"].items()):
        print(f"{lid:18} " + ", ".join(f"{k} {n}" for k, n in sorted(kinds.items())))
    for line in c["unresolved"]:
        print(f"no licence on record: {line}")
    for line in c["blocked"]:
        print(f"blocked: {line}")
    if args.backfill:
        print(f"stamped {c['stamped']} field(s) into the indexes")
    elif c["stamped"]:
        print(f"{c['stamped']} field(s) missing — run with --backfill to write them")
    if args.brief:
        brief = load_brief(args.brief)
        refused = licences.refused(assets.load(), licences.UseContext.from_brief(brief))
        print(f"\nthis brief refuses {len(refused)} asset(s)")
        for aid, rs in sorted(refused.items()):
            print(f"  {aid}: {licences.reason(rs)}")
    return 1 if c["unresolved"] else 0


def _cmd_preview_choose(args: argparse.Namespace) -> int:
    from reel import preview
    from reel.workspace import Workspace

    try:
        data = preview.choose(Workspace(Path(args.project).resolve()), args.option)
    except ValueError as exc:
        print(f"not applied: {exc}")
        return 1
    o = data["options"][args.option]
    print(f"chose {args.option}: caption style {o['caption_family']}, look {o['look']} — now `reel run` renders the full reel")
    return 0


def _cmd_add_asset(args: argparse.Namespace) -> int:
    from reel import library

    try:
        e = library.add_file(Path(args.file).expanduser(), kind=args.kind, licence_id=args.licence, source=args.source,
                             source_url=args.source_url, attribution=args.attribution, credit=args.credit, category=args.category, mood=args.mood)
    except ValueError as exc:
        print(f"not added: {exc}")
        return 1
    print(f"added {e['id']} ({args.kind}, {e.get('licence_id')}) → {e['file']}")
    return 0


def _cmd_remeasure_music(args: argparse.Namespace) -> int:
    from reel import library

    r = library.remeasure_music()
    print(f"re-measured {r['remeasured']} track(s) with {r['tracker']}; {r['with_drop']} have a drop")
    if r["missing"]:
        print(f"not on this machine (run `reel assets fetch`): {', '.join(r['missing'])}")
    return 0


def _cmd_library(args: argparse.Namespace) -> int:
    from reel import library

    folder = Path(args.folder).resolve()
    if args.kind == "lottie":
        from reel import lottie

        entries = lottie.index_folder(folder, source=args.source, license_=args.license)
        path = lottie.write_index(entries, replace=args.replace)
        print(f"indexed {len(entries)} Lottie animation(s) → {path}")
        for f, why in lottie.SKIPPED:
            print(f"refused: {f} ({why})")
        return 0
    if args.kind == "sfx":
        entries = library.index_sfx(folder, source=args.source, license_=args.license)
    else:
        entries = library.index_music(folder, source=args.source, license_=args.license)
    path = library.write_index(args.kind, entries, replace=args.replace)
    cats: dict[str, int] = {}
    for e in entries:
        k = e.get("category") or e.get("mood") or "?"
        cats[k] = cats.get(k, 0) + 1
    print(f"indexed {len(entries)} {args.kind} file(s) → {path}")
    for k, n in sorted(cats.items()):
        print(f"  {k:12} {n}")
    for f, why in library.SKIPPED:
        print(f"couldn't read: {f} ({why})")
    return 0


def _cmd_assets_fetch(args: argparse.Namespace) -> int:
    from reel import fetch_assets

    if args.sonniss_url and not args.include_sonniss:
        print("--sonniss-url needs --include-sonniss (Sonniss licence v2.0 has a 'NO AI TRAINING OR USAGE' clause; legal review first)")
        return 2
    if args.include_sonniss and not args.sonniss_url:
        print("--include-sonniss needs at least one --sonniss-url https://downloads.sonniss.com/<bundle>.zip")
        return 2
    res = fetch_assets.fetch(procedural=not args.no_procedural, kenney=not args.no_kenney, music=not args.no_music,
                             sonniss_urls=args.sonniss_url if args.include_sonniss else None, sonniss_pattern=args.sonniss_pattern,
                             sonniss_per_category=args.sonniss_per_category, refresh=args.refresh)
    print(f"fetched {res['sfx_new']} SFX and {res['music_new']} music track(s) this run\n")
    print("SFX library by category:")
    for k, n in res["sfx_by_category"].items():
        print(f"  {k:10} {n}")
    print("SFX library by source:")
    for k, n in res["sfx_by_source"].items():
        print(f"  {k:32} {n}")
    print("Music library by mood:")
    for k, n in res["music_by_mood"].items():
        print(f"  {k:10} {n}")
    mb = {k: v / 1e6 for k, v in res["disk_bytes"].items()}
    print(f"\ndisk: sfx {mb['sfx']:.1f} MB · music {mb['music']:.1f} MB")
    for p in res["problems"]:
        print(f"note: {p}")
    return 0


def _cmd_bakeoff(args: argparse.Namespace) -> int:
    import time

    from reel import bakeoff

    clips = bakeoff.load_dataset(Path(args.samples).resolve())
    if not clips:
        print(f"no clips in {args.samples}: add <name>/{{clip.mp4, transcript.txt[, words.tsv]}}")
        return 2
    out = Path(args.out).resolve() / time.strftime("%Y%m%d-%H%M%S")
    summary = bakeoff.run(bakeoff.engines(args.engines), clips, out, language=args.language)
    print((out / "results.md").read_text())
    print(f"details: {out}")
    return 0


def _load_ws(project: str):
    from reel.workspace import Workspace

    ws = Workspace(Path(project).resolve())
    opts_file = ws.path("run_options.json")
    return ws, (json.loads(opts_file.read_text()) if opts_file.exists() else {})


def _rerun_after_plan_change(ws, options) -> None:
    from reel.runner import run_pipeline
    from reel.stages import edit

    state = run_pipeline(ws, [edit.COMPILE, edit.RENDER, edit.OVERLAY, edit.COMPOSITE, edit.QA, edit.COVER, edit.PACKAGE, edit.VARIANTS], options=options)
    _print_state(state, ws)
    _print_verdict(ws)


def _cmd_rerun(args: argparse.Namespace) -> int:
    """Re-run the pipeline from one edit stage onward (that stage forced), without Editor calls or the fix loop.

    Used after a plan was changed by hand (Reel Studio adjustments, version restore, delivery variants), so the
    owner's change is rendered as-is and never revised by the fix loop."""
    from reel.runner import StageContext, load_state, run_pipeline, save_state
    from reel.stages import edit

    stages = edit.STAGES[[s.name for s in edit.STAGES].index(args.from_stage):]
    ws, options = _load_ws(args.project)
    with ws.lock():  # the plans on disk are now the accepted ones: a later `reel run` must not re-ask the Editor
        state = load_state(ws)  # (as autofix.apply_revision does after a revision)
        fin = state.get("stages", {}).get("finish")
        if fin and fin.get("status") == "done" and ws.path("plan", "finish.json").exists():
            fin["input_hash"] = edit.FINISH.input_hash(StageContext(ws=ws, options=options))
            save_state(ws, state)
    state = run_pipeline(ws, stages, options=options, force={args.from_stage})
    _print_state(state, ws)
    _print_verdict(ws)
    return 0


RERUN_FROM = ("compile", "render", "overlay", "composite", "qa", "package", "variants")


def _cmd_studio(args: argparse.Namespace) -> int:
    from reel.studio import server

    if args.install_launcher:
        plist = server.install_launcher(args.port, args.projects)
        print(f"Reel Studio now starts at login: {plist}\nlogs: ~/Library/Logs/reel-studio.log · remove with `reel studio --uninstall-launcher`")
        return 0
    if args.uninstall_launcher:
        print("launcher removed" if server.uninstall_launcher() else "no launcher was installed")
        return 0
    return server.serve(port=args.port, open_browser=args.open, dev=args.dev, projects=args.projects)


def _cmd_revise(args: argparse.Namespace) -> int:
    """Chat revision: resume the Editor's finish session, apply story ops + new finish plan, re-render, re-check."""
    from reel import autofix

    ws, options = _load_ws(args.project)
    res = autofix.apply_revision(ws, options, args.request)
    print(f"Editor: {res['reply']}  ({res['calls']} call(s), ~${res['cost_usd']})")
    for w in res.get("warnings", []):
        print(f"warning: {w}")
    _rerun_after_plan_change(ws, options)
    return 0


def _cmd_notes(args: argparse.Namespace) -> int:
    """Client notes on the review copy → one Editor revision → re-render + re-check."""
    from reel import autofix, notes, project
    from reel.schemas.plan import StoryPlan
    from reel.schemas.timeline import Timeline

    ws, options = _load_ws(args.project)
    parsed = notes.parse(Path(args.file).read_text())
    if not parsed:
        print("no notes found")
        return 2
    tl = Timeline.model_validate_json(ws.path("timeline", "timeline.json").read_text())
    story = project.load_json_model(StoryPlan, ws.path("plan", "story.json"))
    request = notes.revision_request(parsed, tl, story, project.word_table(ws))
    print(request + "\n")
    if args.dry_run:
        return 0
    res = autofix.apply_revision(ws, options, request)
    print(f"Editor: {res['reply']}  ({res['calls']} call(s), ~${res['cost_usd']})")
    for w in res.get("warnings", []):
        print(f"warning: {w}")
    _rerun_after_plan_change(ws, options)
    return 0


def _cmd_stock(args: argparse.Namespace) -> int:
    """Search Pexels and download clips into a folder to pass as `reel run … --broll <folder>`."""
    from reel import stock

    folder = Path(args.out).resolve()
    results = stock.search(args.query, n=args.n)
    paths = stock.download(results, folder, args.query)
    for r, pth in zip(results, paths):
        print(f"{pth.name}: {r['w']}x{r['h']} {r['duration']} s — {r['author']} {r['page']}")
    print(f"\n{len(paths)} clip(s) in {folder}. Add them to the edit with: reel run <clip> --broll {folder}")
    return 0


def _cmd_improve(args: argparse.Namespace) -> int:
    """Gated self-improvement over the tuning set (knowledge deltas only; holdout never used)."""
    from reel import improve

    evaluate, rows_of = improve.harness_evaluator()
    res = improve.run_night(evaluate, improve.claude_proposer(), runs=args.runs, rounds=args.rounds, budget=args.budget,
                            rows_of=rows_of, commit=not args.no_commit, dry_run=args.dry_run)
    for r in res["rounds"]:
        print(f"round {r['round']}: {r.get('outcome')} — {r.get('diagnosis', '')[:200]}")
        for c in r["changes"]:
            print(f"   {c['kind']} {c['node_id']}: {c['expected_effect'][:120]}")
        if r.get("decision"):
            d = r["decision"]
            print(f"   gain {d.get('mean_gain')} (δ_min {d.get('delta_min')}), p={d.get('p')} {'; '.join(d.get('reasons', []))}")
    print(f"\naccepted {len(res['accepted'])} change(s) · {res['reel_runs']} reel-runs · log {improve.LOG}")
    return 0


def _cmd_proof(args: argparse.Namespace) -> int:
    """Owner confirms or corrects unsure caption words (ADR-0021); captions re-render, the base does not."""
    from reel.workspace import atomic_write_json

    ws, options = _load_ws(args.project)
    path = ws.path("qa", "proof_confirmed.json")
    conf = json.loads(path.read_text()) if path.exists() else {}
    for i in args.ok or []:
        conf[str(i)] = {"ok": True}
    for item in args.fix or []:
        i, _, text = item.partition("=")
        conf[str(int(i))] = {"ok": True, "text": text}
    atomic_write_json(path, conf)
    print(f"confirmed {len(conf)} word(s)")
    _rerun_after_plan_change(ws, options)
    return 0


def _cmd_label(args: argparse.Namespace) -> int:
    from reel.workspace import atomic_write_json

    ws, _ = _load_ws(args.project)
    atomic_write_json(ws.path("qa", "owner_label.json"), {"sendable": args.sendable == "yes", "note": args.note or ""})
    print(f"labelled {ws.root.name}: sendable={args.sendable}")
    return 0


def _cmd_calibrate(args: argparse.Namespace) -> int:
    from reel import calibrate

    if args.auto:
        from reel import calibrate_auto

        rep = calibrate_auto.run(Path(args.projects).resolve(), Path(args.gold).resolve(), args.project, args.trials,
                                 Path(args.out).resolve() if args.out else calibrate_auto.DEFAULT_OUT)
        print(json.dumps({k: rep[k] for k in ("rule", "known_good_reels", "gates", "seconds")}, indent=2))
        return 0
    print(json.dumps(calibrate.report(calibrate.collect(Path(args.projects).resolve())), indent=2))
    return 0


def _cmd_eval(args: argparse.Namespace) -> int:
    from reel.evalh import harness

    if args.init:
        m = harness.init_manifest(auto_holdout=args.auto_holdout)
        from collections import Counter

        print(Counter((r["split"], r.get("language")) for r in m["reels"]))
        print(f"manifest: {harness.MANIFEST} ({len(m['reels'])} reels)")
        return 0
    if args.revisions:  # 3b.3: one Claude call per case in eval/revisions/
        from reel.evalh import revisions

        out = revisions.run_all()
        for c in out["cases"]:
            print(f"{c['id']:22} did_it {c['did_it']!s:5} collateral {c.get('collateral_s', '—')!s:>6} s  dont_break {c['dont_break']!s:5} "
                  + (c.get("error") or f"“{c.get('reply', '')}”"))
        print(f"\n{out['did_it']}/{out['n']} did what was asked · {out['dont_break']}/{out['n']} broke nothing · "
              f"mean collateral {out['mean_collateral_s']} s")
        return 0
    row = harness.run_eval(args.set, allow_holdout=args.holdout, pairwise=args.pairwise)
    keys = ("run_id", "split", "commit", "dirty", "knowledge", "mean_primary", "vetoed", "pairwise")
    print(json.dumps({k: row[k] for k in keys if k in row}, indent=2))
    return 0


def _cmd_conformance(args: argparse.Namespace) -> int:
    from fractions import Fraction

    from reel.conformance import checks, corpus
    from reel.mezzanine import make_mezzanine
    from reel.probe import probe
    from reel.stages.ingest import choose_project_fps

    out_dir = Path(args.out).resolve()
    clips = corpus.build(out_dir / "src", args.only)
    real = sorted((Path.cwd() / "samples" / "conformance").glob("*")) if args.real else []
    failures = 0
    for clip in [*clips, *[p for p in real if p.is_file()]]:
        p = probe(clip)
        fps = choose_project_fps([Fraction(p.video.nominal_fps).limit_denominator(1001)], [p.duration_s])
        mezz = out_dir / "mezz" / f"{clip.stem}.mov"
        mezz.parent.mkdir(parents=True, exist_ok=True)
        make_mezzanine(p, mezz, fps, encoder=args.encoder)
        synthetic = clip.parent == out_dir / "src"
        res = checks.check_mezzanine(p, mezz, fps, expect_probe=synthetic and clip.stem != "no_audio")
        failures += not res["ok"]
        status = "PASS" if res["ok"] else "FAIL"
        c = res["checks"]
        print(f"{status} {clip.name:28} fps={c.get('fps')} frames={c.get('frames')}/{c.get('frames_expected')} "
              f"size={c.get('size')} av={c.get('av_offset_ms')}ms colour={c.get('color')}")
        for f in res["failures"]:
            print(f"       - {f}")
    print(f"\n{len(clips) + len(real) - failures} passed, {failures} failed")
    return 0 if failures == 0 else 1


SCHEMAS = {
    "story": ("reel.schemas.plan", "StoryPlan"),
    "finish": ("reel.schemas.plan", "FinishPlan"),
    "patch": ("reel.schemas.plan", "StoryPatch"),
    "revision": ("reel.schemas.plan", "Revision"),
    "timeline": ("reel.schemas.timeline", "Timeline"),
    "words": ("reel.schemas.perception", "WordTable"),
}


def _cmd_schema(args: argparse.Namespace) -> int:
    import importlib

    mod, name = SCHEMAS[args.name]
    model = getattr(importlib.import_module(mod), name)
    print(json.dumps(model.model_json_schema(), indent=2))
    return 0


def _plan_inputs(args: argparse.Namespace):
    from reel import assets, knowledge, project
    from reel.schemas.plan import FinishPlan, StoryPlan
    from reel.workspace import Workspace

    ws = Workspace(Path(args.project).resolve())
    story_path = Path(args.story) if args.story else ws.path("plan", "story.json")
    story = project.load_json_model(StoryPlan, story_path)
    finish = None
    finish_path = Path(args.finish) if args.finish else ws.path("plan", "finish.json")
    if finish_path.exists():
        finish = project.load_json_model(FinishPlan, finish_path)
    return ws, story, finish, project.word_table(ws), project.clip_infos(ws), project.project_fps(ws), assets.load(), knowledge.node_ids()


def _cmd_validate(args: argparse.Namespace) -> int:
    from reel.validate import errors, validate_finish, validate_story

    from reel.clipfactory import load_window

    ws, story, finish, words, clips, fps, idx, kids = _plan_inputs(args)
    issues = validate_story(story, words, set(clips), kids, window=load_window(ws))
    if finish is not None and not errors(issues):
        issues += validate_finish(finish, story, words, idx, kids)
    print(json.dumps({"ok": not errors(issues), "issues": [i.as_dict() for i in issues]}, indent=2, ensure_ascii=False))
    return 0 if not errors(issues) else 2


def _cmd_compile(args: argparse.Namespace) -> int:
    from reel import project
    from reel.compile import compile_timeline
    from reel.validate import errors, validate_finish, validate_story
    from reel.workspace import atomic_write_json

    from reel.clipfactory import load_window

    ws, story, finish, words, clips, fps, idx, kids = _plan_inputs(args)
    issues = validate_story(story, words, set(clips), kids, window=load_window(ws)) + (validate_finish(finish, story, words, idx, kids) if finish else [])
    if errors(issues):
        print(json.dumps({"ok": False, "issues": [i.as_dict() for i in errors(issues)]}, indent=2, ensure_ascii=False))
        return 2
    tl = compile_timeline(story, finish, words, clips, fps, idx, edges=project.edges(ws), vad=project.vad_speech(ws), scene_cuts=project.scene_cuts(ws))
    out = ws.path("timeline", "timeline.json")
    atomic_write_json(out, tl.model_dump(mode="json"))
    print(f"timeline: {out} · {tl.duration_f} frames @ {tl.fps} · {len(tl.video)} video clips · {len(tl.captions.pages if tl.captions else [])} caption pages")
    return 0


def _cmd_dry_run(args: argparse.Namespace) -> int:
    from reel import project
    from reel.compile import dry_run
    from reel.validate import errors, validate_story

    from reel.clipfactory import load_window

    ws, story, _finish, words, clips, fps, idx, kids = _plan_inputs(args)
    issues = validate_story(story, words, set(clips), kids, window=load_window(ws))
    if errors(issues):
        print(json.dumps({"ok": False, "issues": [i.as_dict() for i in errors(issues)]}, indent=2, ensure_ascii=False))
        return 2
    print(dry_run(story, words, clips, fps, idx, edges=project.edges(ws), vad=project.vad_speech(ws), scene_cuts=project.scene_cuts(ws)))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="reel", description="Claude-driven reel editor engine")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("doctor", help="check the pinned toolchain").set_defaults(func=_cmd_doctor)

    p = sub.add_parser("probe", help="describe a media file")
    p.add_argument("file")
    p.set_defaults(func=_cmd_probe)

    p = sub.add_parser("run", help="run the pipeline on a clip or folder of clips")
    p.add_argument("input", nargs="?", help="clip or folder (omit for a Clip Factory reel project: --project only)")
    p.add_argument("--project", help="workspace folder (default: ./projects/<input name>)")
    p.add_argument("--fps", help="override project fps, e.g. 30 or 30000/1001")
    p.add_argument("--encoder", default="prores_ks", choices=["prores_ks", "prores_videotoolbox"])
    p.add_argument("--force", action="append", help="re-run a stage even if up to date (repeatable)")
    p.add_argument("--language", help="speech language: en | hi (default: brief, else auto-detect)")
    p.add_argument("--brief", help="client brief JSON (briefs/<project>.json)")
    p.add_argument("--brand", help="brand kit JSON (brands/<client>.json)")
    p.add_argument("--asr-repo", help="override the ASR model repo (default mlx-community/whisper-large-v3-turbo)")
    p.add_argument("--skip-visual", action="store_true", help="skip OCR, scenes, faces, palette, motion (faster)")
    p.add_argument("--no-voice-enhance", action="store_true", help="keep the original voice (no DeepFilterNet; the ffmpeg chain still applies)")
    p.add_argument("--analyse-only", action="store_true", help="stop after the footage tables (no Claude calls)")
    p.add_argument("--preview-first", action="store_true", help="stop after rendering the hook in two looks (A/B) for the client to pick")
    p.add_argument("--skip-review", action="store_true", help="QA gates only, no Reviewer call")
    p.add_argument("--reference", help="a finished reel the client likes: its pacing, captions and colour become the style to match")
    p.add_argument("--broll", help="folder of client b-roll clips (conformed, described by Claude, offered to the Editor)")
    p.add_argument("--stock", action="store_true", help="find stock b-roll on Pexels for this talk at edit time (needs PEXELS_API_KEY)")
    p.add_argument("--story-checkin", action="store_true", help="stop after the story pass for the owner's check-in (`reel checkin`)")
    p.add_argument("--mine", action="store_true", help="Clip Factory: a long recording → analysis + a ranked board of candidate reels")
    p.add_argument("--clip-length", help="(--mine) speech length per reel in seconds, e.g. 20-75 (default 20-75 or the brief's)")
    p.set_defaults(func=_cmd_run)

    p = sub.add_parser("gold", help="gold set: `gold add <raw> <final.mp4> --language hi` (3b.5)")
    gsub = p.add_subparsers(dest="gold_cmd", required=True)
    q = gsub.add_parser("add", help="add one pair: raw footage (file or folder) + the pro's finished reel")
    q.add_argument("raw")
    q.add_argument("final")
    q.add_argument("--language", required=True, choices=["en", "hi", "hinglish"])
    q.add_argument("--split", default="tuning", choices=["tuning", "holdout"])
    q.add_argument("--genre", help="e.g. genre.podcast_clip")
    q.add_argument("--channel", help="the creator, e.g. @handle (spreads the holdout across creators)")
    q.add_argument("--id", help="pair id (default: from the final's file name)")
    q.add_argument("--no-check", action="store_true", help="skip the 'final was cut from this raw' audio check")
    p.set_defaults(func=_cmd_gold)

    p = sub.add_parser("checkin", help="answer the story check-in (3a.1); without answers, print it")
    p.add_argument("--project", required=True)
    p.add_argument("--yes", help="accepted question ids, comma-separated (e.g. q1,q3)")
    p.add_argument("--note", help="a change in your words (one Editor call)")
    p.add_argument("--approve", action="store_true", help="approve the story as it is")
    p.add_argument("--continue", dest="cont", action="store_true", help="then run the rest of the edit")
    p.set_defaults(func=_cmd_checkin)

    p = sub.add_parser("listen", help="free-model listening test (G2.5): blind A/B of generated SFX, music, voice")
    lsub = p.add_subparsers(dest="listen_cmd", required=True)
    for name, help_text in (("prepare", "render every prompt with the declared generators (~/.config/reel/generators.json) + the fallback"),
                            ("summary", "win rate, usable rate and the adopt decision per model")):
        q = lsub.add_parser(name, help=help_text)
        q.add_argument("--set", required=True, choices=["sfx", "music", "voice"])
    p.set_defaults(func=_cmd_listen)

    p = sub.add_parser("factory", help="Clip Factory: turn picked candidates of a mined recording into reel projects")
    p.add_argument("--project", required=True, help="the mined source project (`reel run <long recording> --mine`)")
    p.add_argument("--make", help="candidate ids, comma-separated (see mine/board.md); omit to print the board")
    p.add_argument("--run", action="store_true", help="also edit each new reel now, one after another")
    p.add_argument("--skip-review", action="store_true")
    p.set_defaults(func=_cmd_factory)

    p = sub.add_parser("notes", help="apply a client's timestamped notes (e.g. '0:12 make this faster') as one revision")
    p.add_argument("--project", required=True)
    p.add_argument("file", help="text file with one note per line")
    p.add_argument("--dry-run", action="store_true", help="show the anchored request without calling the Editor")
    p.set_defaults(func=_cmd_notes)

    p = sub.add_parser("stock", help="search Pexels stock b-roll (needs PEXELS_API_KEY) into a b-roll folder")
    p.add_argument("query")
    p.add_argument("--out", required=True, help="b-roll folder (e.g. projects/<p>/broll_src)")
    p.add_argument("--n", type=int, default=3)
    p.set_defaults(func=_cmd_stock)

    p = sub.add_parser("improve", help="gated self-improvement on the tuning set (knowledge deltas; ADR-0029/0030)")
    p.add_argument("--runs", type=int, default=3, help="runs per arm per reel")
    p.add_argument("--rounds", type=int, default=5)
    p.add_argument("--budget", type=int, default=100, help="max reel-runs for the night")
    p.add_argument("--dry-run", action="store_true", help="baseline + proposal only, nothing tested or kept")
    p.add_argument("--no-commit", action="store_true", help="keep accepted overrides uncommitted")
    p.set_defaults(func=_cmd_improve)

    p = sub.add_parser("proof", help="confirm/correct unsure caption words, then re-render captions")
    p.add_argument("--project", required=True)
    p.add_argument("--ok", nargs="*", type=int, help="word indices that are correct as transcribed")
    p.add_argument("--fix", nargs="*", help="corrections as <index>=<text>, e.g. 7=DearMa")
    p.set_defaults(func=_cmd_proof)

    p = sub.add_parser("label", help="owner judgement of a rendered reel (for calibration)")
    p.add_argument("--project", required=True)
    p.add_argument("--sendable", required=True, choices=["yes", "no"])
    p.add_argument("--note")
    p.set_defaults(func=_cmd_label)

    p = sub.add_parser("calibrate", help="Reviewer agreement + gate false-positive rates vs owner labels; --auto: pro finals + injected defects")
    p.add_argument("--projects", default="projects")
    p.add_argument("--auto", action="store_true", help="ADR-0033: false alarms on gold-set pro finals, catches of injected defects")
    p.add_argument("--project", default="_real_doac", help="(--auto) one of our rendered projects to inject defects into")
    p.add_argument("--gold", default="samples/gold", help="(--auto) folder of pro finals (<reel>/final.mp4)")
    p.add_argument("--trials", type=int, default=10)
    p.add_argument("--out", default=None, help="(--auto) report folder (default eval/calibration)")
    p.set_defaults(func=_cmd_calibrate)

    p = sub.add_parser("library", help="index a local SFX, music or Lottie folder into assets/")
    p.add_argument("kind", choices=["sfx", "music", "lottie"])
    p.add_argument("folder")
    p.add_argument("--source", required=True, help='e.g. "Sonniss GDC 2024"')
    p.add_argument("--license", required=True, help="licence summary stored with every file")
    p.add_argument("--replace", action="store_true", help="drop previously indexed files from the same source first")
    p.set_defaults(func=_cmd_library)

    p = sub.add_parser("preview-choose", help="apply the client's hook-preview pick (A or B) to the plan; then `reel run` renders it")
    p.add_argument("--project", required=True)
    p.add_argument("--option", required=True, choices=["A", "B"])
    p.set_defaults(func=_cmd_preview_choose)

    p = sub.add_parser("add-asset", help="add ONE hand-picked SFX / music / Lottie file with its licence and source (never bulk)")
    p.add_argument("file")
    p.add_argument("--kind", required=True, choices=["sfx", "music", "lottie"])
    p.add_argument("--licence", required=True, help="a licence id from assets/licenses/registry.yaml, e.g. cc0-1.0, pixabay-content")
    p.add_argument("--source", required=True, help='where it came from, e.g. "Pixabay", "Freesound"')
    p.add_argument("--source-url", default="", help="the page you downloaded it from")
    p.add_argument("--attribution", default="", help="exact credit text, when the licence requires one")
    p.add_argument("--credit", default="", help="an optional credit the author asked for")
    p.add_argument("--category", help="SFX category when the file name doesn't say it")
    p.add_argument("--mood", help="music mood")
    p.set_defaults(func=_cmd_add_asset)

    p = sub.add_parser("licences", help="licence of every library asset (assets/licenses/registry.yaml); exit 1 if any has none")
    p.add_argument("--backfill", action="store_true", help="write licence ids (and missing sha256) into the committed indexes")
    p.add_argument("--brief", help="also list the assets this brief's licence gate refuses")
    p.set_defaults(func=_cmd_licences)

    p = sub.add_parser("assets", help="asset libraries (SFX, music)")
    asub = p.add_subparsers(dest="assets_cmd", required=True)
    p = asub.add_parser("fetch", help="fill assets/ with procedural + Kenney CC0 SFX and Incompetech CC BY music, with licence provenance")
    p.add_argument("--no-procedural", action="store_true", help="skip the synthesised SFX")
    p.add_argument("--no-kenney", action="store_true", help="skip the Kenney CC0 packs")
    p.add_argument("--no-music", action="store_true", help="skip the Incompetech music")
    p.add_argument("--refresh", action="store_true", help="re-download music already on disk")
    p.add_argument("--include-sonniss", action="store_true",
                   help="also fetch Sonniss GDC SFX — OFF by default: licence v2.0 says 'NO AI TRAINING OR USAGE'; get a legal read first")
    p.add_argument("--sonniss-url", action="append", help="Sonniss bundle zip on downloads.sonniss.com (repeatable)")
    p.add_argument("--sonniss-pattern", help="regex on member paths to take (default: every categorised sound)")
    p.add_argument("--sonniss-per-category", type=int, default=12)
    p.set_defaults(func=_cmd_assets_fetch)

    p = asub.add_parser("remeasure-music", help="re-measure beats, downbeats and the drop of the music library (Beat This! if installed)")
    p.set_defaults(func=_cmd_remeasure_music)

    p = sub.add_parser("bakeoff", help="Hinglish ASR bake-off on samples/hinglish (ADR-0007)")
    p.add_argument("--samples", default="samples/hinglish")
    p.add_argument("--out", default="analysis/bakeoff")
    p.add_argument("--engines", nargs="*", help="subset of engines (default: all registered)")
    p.add_argument("--language", default="hi", help="language hint passed to engines that take one")
    p.set_defaults(func=_cmd_bakeoff)

    p = sub.add_parser("revise", help="chat revision of an edited project, then re-render")
    p.add_argument("--project", required=True)
    p.add_argument("request", help='what to change, e.g. "start with the 10%% line and make it punchier"')
    p.set_defaults(func=_cmd_revise)

    p = sub.add_parser("rerun", help="re-render from an edit stage onward after a plan change (no Editor calls)")
    p.add_argument("--project", required=True)
    p.add_argument("--from", dest="from_stage", default="compile", choices=RERUN_FROM)
    p.set_defaults(func=_cmd_rerun)

    p = sub.add_parser("studio", help="Reel Studio: the local dashboard and its API on 127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--open", action="store_true", help="open the dashboard in the browser")
    p.add_argument("--dev", action="store_true", help="allow the Vite dev origin http://127.0.0.1:5173 (CORS)")
    p.add_argument("--projects", help="projects folder (default: <repo>/projects, or $REEL_PROJECTS_ROOT)")
    p.add_argument("--install-launcher", action="store_true", help="start Reel Studio at login (macOS LaunchAgent; still 127.0.0.1 only)")
    p.add_argument("--uninstall-launcher", action="store_true", help="remove that LaunchAgent")
    p.set_defaults(func=_cmd_studio)

    p = sub.add_parser("eval", help="eval harness")
    p.add_argument("--init", action="store_true", help="create/refresh eval/manifest.yaml from samples/gold/")
    p.add_argument("--set", default="tuning", choices=["tuning", "holdout"])
    p.add_argument("--holdout", action="store_true", help="confirm running the holdout set (release candidates only)")
    p.add_argument("--auto-holdout", action="store_true", help="with --init: pick a seeded, stratified holdout (≥ 2 Hinglish) once")
    p.add_argument("--pairwise", action="store_true", help="also judge ours vs the pro's reel, both orders (2 Claude calls per reel; 3b.2)")
    p.add_argument("--revisions", action="store_true", help="run the revision evals in eval/revisions/ (1 Claude call per case; 3b.3)")
    p.set_defaults(func=_cmd_eval)

    p = sub.add_parser("conformance", help="build the synthetic corpus and check S0 on it")
    p.add_argument("--out", default="projects/_conformance")
    p.add_argument("--only", nargs="*", help="clip names to build")
    p.add_argument("--real", action="store_true", help="also check samples/conformance/* (real phone clips)")
    p.add_argument("--encoder", default="prores_ks", choices=["prores_ks", "prores_videotoolbox"])
    p.set_defaults(func=_cmd_conformance)

    p = sub.add_parser("schema", help="print a JSON Schema (for claude -p --json-schema)")
    p.add_argument("name", choices=sorted(SCHEMAS))
    p.set_defaults(func=_cmd_schema)

    for name, func, help_text in (
        ("validate", _cmd_validate, "check plans against the word table and libraries (exit 2 on errors)"),
        ("compile", _cmd_compile, "validate + compile plans into timeline/timeline.json"),
        ("dry-run", _cmd_dry_run, "read-back script of the story plan"),
    ):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("--project", required=True)
        p.add_argument("--story", help="story plan JSON (default: <project>/plan/story.json)")
        p.add_argument("--finish", help="finish plan JSON (default: <project>/plan/finish.json if present)")
        p.set_defaults(func=func)

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

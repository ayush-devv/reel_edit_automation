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


def _cmd_run(args: argparse.Namespace) -> int:
    from reel.runner import run_pipeline
    from reel.stages import EDIT_PIPELINE, PIPELINE
    from reel.workspace import Workspace, atomic_write_json

    src = Path(args.input).resolve()
    project = Path(args.project).resolve() if args.project else Path.cwd() / "projects" / src.stem
    ws = Workspace.create(project)
    absolute = lambda p: str(Path(p).resolve()) if p else None  # noqa: E731
    options = {"input": str(src), "fps": args.fps, "encoder": args.encoder, "language": args.language,
               "brief": absolute(args.brief), "brand": absolute(args.brand), "asr_repo": args.asr_repo, "skip_visual": args.skip_visual,
               "broll": absolute(args.broll), "reference": absolute(args.reference)}
    options["skip_review"] = args.skip_review
    atomic_write_json(ws.path("run_options.json"), options)  # `reel revise` / `reel proof` reuse them
    if args.analyse_only:
        state = run_pipeline(ws, PIPELINE, options=options, force=set(args.force or []))
        _print_state(state, ws)
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


def _cmd_library(args: argparse.Namespace) -> int:
    from reel import library

    folder = Path(args.folder).resolve()
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

    state = run_pipeline(ws, [edit.COMPILE, edit.RENDER, edit.OVERLAY, edit.COMPOSITE, edit.QA, edit.PACKAGE, edit.VARIANTS], options=options)
    _print_state(state, ws)
    _print_verdict(ws)


def _cmd_revise(args: argparse.Namespace) -> int:
    """Chat revision: resume the Editor's finish session, apply story ops + new finish plan, re-render, re-check."""
    from reel import autofix

    ws, options = _load_ws(args.project)
    res = autofix.apply_revision(ws, options, args.request)
    print(f"Editor: {res['reply']}  ({res['calls']} call(s), ~${res['cost_usd']})")
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
    row = harness.run_eval(args.set, allow_holdout=args.holdout)
    print(json.dumps({k: row[k] for k in ("run_id", "split", "commit", "dirty", "knowledge", "mean_primary", "vetoed")}, indent=2))
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

    ws, story, finish, words, clips, fps, idx, kids = _plan_inputs(args)
    issues = validate_story(story, words, set(clips), kids)
    if finish is not None and not errors(issues):
        issues += validate_finish(finish, story, words, idx, kids)
    print(json.dumps({"ok": not errors(issues), "issues": [i.as_dict() for i in issues]}, indent=2, ensure_ascii=False))
    return 0 if not errors(issues) else 2


def _cmd_compile(args: argparse.Namespace) -> int:
    from reel import project
    from reel.compile import compile_timeline
    from reel.validate import errors, validate_finish, validate_story
    from reel.workspace import atomic_write_json

    ws, story, finish, words, clips, fps, idx, kids = _plan_inputs(args)
    issues = validate_story(story, words, set(clips), kids) + (validate_finish(finish, story, words, idx, kids) if finish else [])
    if errors(issues):
        print(json.dumps({"ok": False, "issues": [i.as_dict() for i in errors(issues)]}, indent=2, ensure_ascii=False))
        return 2
    tl = compile_timeline(story, finish, words, clips, fps, idx, edges=project.edges(ws))
    out = ws.path("timeline", "timeline.json")
    atomic_write_json(out, tl.model_dump(mode="json"))
    print(f"timeline: {out} · {tl.duration_f} frames @ {tl.fps} · {len(tl.video)} video clips · {len(tl.captions.pages if tl.captions else [])} caption pages")
    return 0


def _cmd_dry_run(args: argparse.Namespace) -> int:
    from reel import project
    from reel.compile import dry_run
    from reel.validate import errors, validate_story

    ws, story, _finish, words, clips, fps, idx, kids = _plan_inputs(args)
    issues = validate_story(story, words, set(clips), kids)
    if errors(issues):
        print(json.dumps({"ok": False, "issues": [i.as_dict() for i in errors(issues)]}, indent=2, ensure_ascii=False))
        return 2
    print(dry_run(story, words, clips, fps, idx, edges=project.edges(ws)))
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
    p.add_argument("input")
    p.add_argument("--project", help="workspace folder (default: ./projects/<input name>)")
    p.add_argument("--fps", help="override project fps, e.g. 30 or 30000/1001")
    p.add_argument("--encoder", default="prores_ks", choices=["prores_ks", "prores_videotoolbox"])
    p.add_argument("--force", action="append", help="re-run a stage even if up to date (repeatable)")
    p.add_argument("--language", help="speech language: en | hi (default: brief, else auto-detect)")
    p.add_argument("--brief", help="client brief JSON (briefs/<project>.json)")
    p.add_argument("--brand", help="brand kit JSON (brands/<client>.json)")
    p.add_argument("--asr-repo", help="override the ASR model repo (default mlx-community/whisper-large-v3-turbo)")
    p.add_argument("--skip-visual", action="store_true", help="skip OCR, scenes, faces, palette, motion (faster)")
    p.add_argument("--analyse-only", action="store_true", help="stop after the footage tables (no Claude calls)")
    p.add_argument("--skip-review", action="store_true", help="QA gates only, no Reviewer call")
    p.add_argument("--reference", help="a finished reel the client likes: its pacing, captions and colour become the style to match")
    p.add_argument("--broll", help="folder of client b-roll clips (conformed, described by Claude, offered to the Editor)")
    p.set_defaults(func=_cmd_run)

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

    p = sub.add_parser("library", help="index a local SFX or music folder into assets/")
    p.add_argument("kind", choices=["sfx", "music"])
    p.add_argument("folder")
    p.add_argument("--source", required=True, help='e.g. "Sonniss GDC 2024"')
    p.add_argument("--license", required=True, help="licence summary stored with every file")
    p.add_argument("--replace", action="store_true", help="drop previously indexed files from the same source first")
    p.set_defaults(func=_cmd_library)

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

    p = sub.add_parser("eval", help="eval harness")
    p.add_argument("--init", action="store_true", help="create/refresh eval/manifest.yaml from samples/gold/")
    p.add_argument("--set", default="tuning", choices=["tuning", "holdout"])
    p.add_argument("--holdout", action="store_true", help="confirm running the holdout set (release candidates only)")
    p.add_argument("--auto-holdout", action="store_true", help="with --init: pick a seeded, stratified holdout (≥ 2 Hinglish) once")
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

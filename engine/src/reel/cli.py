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
               "brief": absolute(args.brief), "brand": absolute(args.brand), "asr_repo": args.asr_repo, "skip_visual": args.skip_visual}
    atomic_write_json(ws.path("run_options.json"), options)  # `reel revise` reuses them
    state = run_pipeline(ws, PIPELINE if args.analyse_only else EDIT_PIPELINE, options=options, force=set(args.force or []))
    _print_state(state, ws)
    return 0


def _cmd_revise(args: argparse.Namespace) -> int:
    """Chat revision: resume the Editor's finish session, apply story ops + new finish plan, re-render."""
    from reel import decide
    from reel.runner import StageContext, load_state, run_pipeline, save_state
    from reel.stages import edit
    from reel.workspace import Workspace

    ws = Workspace(Path(args.project).resolve())
    opts_file = ws.path("run_options.json")
    options = json.loads(opts_file.read_text()) if opts_file.exists() else {}
    with ws.lock():
        res = decide.revise(decide.load_inputs(ws, options.get("brief"), options.get("brand")), args.request)
        # the revised plans are the finish stage's output now: mark it done for its current inputs
        state = load_state(ws)
        ctx = StageContext(ws=ws, options=options)
        state["stages"]["finish"] = {**state["stages"].get("finish", {}), "status": "done", "input_hash": edit.FINISH.input_hash(ctx),
                                     "meta": {"revision": res}}
        save_state(ws, state)
    state = run_pipeline(ws, [edit.COMPILE, edit.RENDER], options=options)
    print(f"Editor: {res['reply']}  ({res['calls']} call(s), ~${res['cost_usd']})")
    _print_state(state, ws)
    return 0


def _cmd_eval(args: argparse.Namespace) -> int:
    from reel.evalh import harness

    if args.init:
        m = harness.init_manifest()
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
    p.set_defaults(func=_cmd_run)

    p = sub.add_parser("revise", help="chat revision of an edited project, then re-render")
    p.add_argument("--project", required=True)
    p.add_argument("request", help='what to change, e.g. "start with the 10%% line and make it punchier"')
    p.set_defaults(func=_cmd_revise)

    p = sub.add_parser("eval", help="eval harness")
    p.add_argument("--init", action="store_true", help="create/refresh eval/manifest.yaml from samples/gold/")
    p.add_argument("--set", default="tuning", choices=["tuning", "holdout"])
    p.add_argument("--holdout", action="store_true", help="confirm running the holdout set (release candidates only)")
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

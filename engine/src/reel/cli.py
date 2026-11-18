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


def _cmd_run(args: argparse.Namespace) -> int:
    from reel.runner import run_pipeline
    from reel.stages import PIPELINE
    from reel.workspace import Workspace

    src = Path(args.input).resolve()
    project = Path(args.project).resolve() if args.project else Path.cwd() / "projects" / src.stem
    ws = Workspace.create(project)
    options = {"input": str(src), "fps": args.fps, "encoder": args.encoder}
    state = run_pipeline(ws, PIPELINE, options=options, force=set(args.force or []))
    for name, entry in state["stages"].items():
        print(f"{name:10} {entry['status']:7} {json.dumps(entry.get('meta', {}))}")
    print(f"\nworkspace: {ws.root}")
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
    p.set_defaults(func=_cmd_run)

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

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

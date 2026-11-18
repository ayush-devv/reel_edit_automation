# ADR-0020: `reel run` CLI is the orchestrator; Claude Code is called at decision points

- **Status:** Accepted (2026-11-18, council re-review issue #4) · Amended by ADR-0030 (`--tools Read`, fresh session per decision, failure detection)
- **Date:** 2026-11-18
- **Deciders:** project owner
- **Amends:** ADR-0019 (Claude Code runtime). Claude Code remains the runtime; sequencing moves into code.

## Context
A skill-driven procedure depends on the model following every step (a skipped `reel validate` is silent); after compaction, skill bodies are re-injected only up to 5k tokens each and earlier images/tables are gone; under `claude -p`, a Bash command that hits its timeout moves to background and the run can exit 0 before work finishes. ADR-0016 §7 already says the orchestrator owns compile, render and QA. (Claude Code docs: skills, sub-agents, headless, hooks, settings, context-window — code.claude.com/docs.)

## Decision
1. **`reel run <folder>`** is a state machine over `projects/<name>/state.json`: idempotent stages keyed by input hash, write-to-temp-then-rename, a lockfile, artifact gates (a stage is done only when its artifacts exist and validate), timeouts per stage, resume from the first incomplete stage.
2. **Claude is called only at decision points**, each as a short headless Claude Code call:
   - story pass, finish pass, review, fix decisions, chat revisions.
   - `claude -p --output-format json --json-schema <schema> --append-system-prompt-file <persona.md> --allowedTools Read` (Read for tables and contact sheets only); `--resume <session_id>` to continue a reel's conversation for revisions.
   - The JSON result is validated by `reel validate` (schema + quote check + ranges); on failure the errors are sent back in the same session, up to N retries.
3. **Reviewer** is a separate headless call with its own persona file and `--allowedTools Read` (fresh context; equivalent to the `reel-reviewer` subagent, which stays available for interactive use).
4. **Interactive entry point:** one skill `.claude/skills/edit-reel/SKILL.md` (`/edit-reel <folder>`), which simply runs `reel run` and relays status / handles chat revisions. No separate slash-command file. This is **project configuration** (`.claude/`), not a plugin; hooks use `$CLAUDE_PROJECT_DIR` (not `${CLAUDE_PLUGIN_ROOT}`). SessionStart hook (matchers `startup|resume|compact`) prints in-progress projects from `state.json`.
5. **Permissions for unattended runs:** explicit flags on every `claude -p` call (do not rely on project settings, which wait for folder trust); `reel` itself runs outside Claude, so ffmpeg/Remotion need no Claude permissions. On this machine also `lean-ctx allow` the binaries `reel` calls if run through lean-ctx.
6. **Reproducibility:** pin the Claude Code version; log Claude Code version, model ID and session ID per decision call in `log/runs.jsonl`.
7. **Smoke test before the build:** a stub `reel run` that exercises every binary and every Claude call headless; acceptance requires **0 permission prompts / denials** and no background-timeout exits.

## Consequences
- **Good:** deterministic, testable, resumable; survives compaction; each Claude call has a small, focused context.
- **Bad:** more Python; session plumbing for revisions.

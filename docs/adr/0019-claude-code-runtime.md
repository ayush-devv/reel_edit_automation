# ADR-0019: Claude Code is the runtime (not the Claude API)

- **Status:** Accepted (owner decision, 2026-11-18) · Amended by ADR-0020 (orchestration in `reel run`)
- **Date:** 2026-11-18
- **Deciders:** project owner
- **Supersedes:** ADR-0010 (Claude API integration) — its model/effort reasoning and Experiment 1 evidence still inform this ADR.

## Context
The owner will run the editor inside **Claude Code** (the CLI agent), not build an app on the Claude API. This is the same pattern as social-video-agent: a Claude Code skill drives a local command-line engine; state lives in files.

## Decision
- **Shape:** a Python CLI engine (`reel` — perception, selects, compile, render, QA, package) + **project Claude Code configuration** (`.claude/`, not a packaged plugin):
  - **Skill** `edit-reel` (`.claude/skills/edit-reel/SKILL.md`): the Editor persona, judgment principles, annotated examples, and the stage-by-stage procedure (call CLI → read tables/sheets → write plan JSON → validate → render → QA → fix).
  - **Subagent** `reel-reviewer` (`.claude/agents/reel-reviewer.md`, fresh context, model set in frontmatter): judges contact sheets of the render against the plan's stated intents — the same setup as Experiment 1.
  - The skill itself provides `/edit-reel <folder>` (no separate command file); a **SessionStart hook** (via `$CLAUDE_PROJECT_DIR`) reports in-progress projects (resume).
  - **Permissions:** `.claude/settings.json` allowlists the `reel` CLI, ffmpeg, ffprobe, npx remotion so autonomous runs are not interrupted by prompts (plus `lean-ctx allow` for the same binaries on this machine).
- **How Claude sees media:** the Read tool on contact-sheet PNGs and on the text tables the CLI writes. Claude never reads video.
- **How Claude writes the plan:** writes `plan/*.json` to disk; `reel validate` checks it against the pydantic schema (incl. quote check, ranges) and prints errors for Claude to fix. (No API structured-output guarantee — validation is ours.)
- **Models:** main session on Opus (owner's Claude Code model setting); reviewer subagent on Opus (Experiment 1: Opus 6/6). Effort/model are Claude Code settings, not API parameters.
- **Batch tagging of the asset library:** done inside Claude Code sessions (or a subagent) — no Batch API.
- **State:** `projects/<name>/state.json` is the source of truth for resume; chat history is not state.
- **Headless option:** `claude -p "/edit-reel <folder>"` for unattended runs, with the same allowlist.

## Consequences
- **Good:** no API key or SDK code; Claude Code already provides the agent loop, image reading, subagents, context management and caching; matches social-video-agent's design (strengthens the fork option, ADR-0013); cost is the owner's Claude Code plan instead of per-token billing.
- **Bad / accept:**
  - No API structured-output or strict-tool guarantees → validator + correction loop is mandatory.
  - Usage limits of the Claude Code plan cap reels per day; cost per reel is not directly metered (log session counts).
  - Less control over caching and effort than the API; long sessions rely on Claude Code's context management.
  - Permission prompts or allowlist gaps can stall an autonomous run → allowlist must be complete and tested.
- **Revisit when:** the tool must run without a human-owned Claude Code session (e.g. a server or SaaS) → return to the Messages API (ADR-0010 design).

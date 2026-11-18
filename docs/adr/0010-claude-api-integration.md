# ADR-0010: Claude API integration (models, surface, caching, structured output)

- **Status:** Superseded by ADR-0019 (2026-11-18)
- **Date:** 2026-11-18
- **Deciders:** project owner
- **Basis:** claude-api skill review (model table cached 2026-11-03) + Experiment 1 (`analysis/exp1/results.md`)

## Context
ADR-0005 chose one orchestrator with Editor and Reviewer personas. This ADR fixes how those talk to Claude. Constraints: local-first (ADR-0009); tools (ffmpeg, perception, renderer) run on the Mac; edit plan must be schema-valid; revisions happen in a chat loop that can span many minutes.

## Decisions

### 1. Surface: Messages API + SDK Tool Runner (Python), not Managed Agents
- The pipeline is a code-driven workflow with a short agentic step (Editor inspects frames/assets). All tools need local files and local binaries.
- Managed Agents would host the loop in Anthropic's sandbox (beta, session-hour billing, media upload) — conflicts with local-first. Revisit if the tool moves to a server.
- Python `anthropic` SDK; `client.beta.messages.tool_runner` with `@beta_tool` for Editor tools, or a manual loop where per-turn control is needed. Validate every tool input against its schema.

### 2. Models and effort
| Role | Model | Effort | Why |
|---|---|---|---|
| Editor (plan + revisions) | `claude-opus-5-5` | `high` for first draft, `medium` for small revisions (set per conversation, not mid-conversation) | Creative reasoning is intelligence-sensitive; Opus 5.5 default effort is `medium`, so set it explicitly |
| Reviewer (visual QA on contact sheets) | `claude-opus-5-5` | `medium` | Exp 1: Opus 6/6, Sonnet 5/6, Haiku 4/6 |
| Bulk tagging (SFX/b-roll library, frame captions) | `claude-opus-5-5` via Message Batches by default; `claude-haiku-5-5` **only if the user chooses it** (cost-driven downgrade is the user's call) | default | Offline, 50% batch discount; Haiku prompts < 100k tokens (price tier) |
- Thinking is always on for Opus 5.5 (adaptive); `budget_tokens` and `disabled` return 400. Effort is the only control.
- Enable server-side refusal fallbacks (`server-side-fallback-2026-07-01`, `fallbacks: "default"`) and always check `stop_reason` before reading content.

### 3. Structured output for the edit plan
- Final plan returned via `output_config.format` (JSON schema generated from the pydantic plan model), parsed with `client.messages.parse()`.
- Inspection tools use `strict: true`, `additionalProperties: false`.
- **Forced `tool_choice` (`any`/`tool`) is a 400 on Opus 5.5** — use `auto` + instructions.
- Schema limits: no recursion, no numeric bounds → ranges (frame ≥ 0, zoom 1.0–2.0, durations) enforced by pydantic validators after parsing; failures go back to Claude as a tool error / correction message.
- No assistant prefill (400 on current models).

### 4. Prompt caching layout (prefix order: tools → system → messages)
1. `tools` — fixed list, sorted, no per-request changes.
2. `system` — persona + playbook rules + plan schema notes (frozen text; no timestamps).
3. First user message — footage tables + contact sheets + SFX index for this project → **cache breakpoint here, 1-hour TTL** (revision gaps exceed 5 min while the user watches previews).
4. Conversation turns and tool results appended after it (append-only; never edit earlier turns — Opus 5.5 preserved-thinking check).
- Frames requested via `inspect_frames` are appended as tool results, so they do not invalidate the cached prefix.
- Operator nudges mid-session go in a mid-conversation `{"role":"system"}` message, not by editing `system`.
- Don't change top-level effort mid-conversation (invalidates cache).
- Verify `usage.cache_read_input_tokens > 0` on every revision call; log it.

### 5. Images
- Send **contact sheets** (many small frames per image), not single frames: ~1.6–1.7k tokens per 12-frame sheet (`ceil(w/28)·ceil(h/28)`).
- Upload sheets once per project via the Files API (`client.files.upload`, no beta) and reference by `file_id`; delete or set expiry when the project closes. Never accept `file_id`s from outside.
- Faces are described, never identified (Anthropic usage policy).

### 6. Requests
- Stream every Editor/Reviewer call (`.stream()` + `.get_final_message()`), `max_tokens` ~64k; `eager_input_streaming: true` on client tools with input validation.
- Optional: task budget (beta `task-budgets-2026-03-13`) to cap tokens per draft loop.
- Credentials: SDK resolves `ANTHROPIC_API_KEY` or an `ant auth login` profile (`ant` currently blocked by the lean-ctx allowlist).

## Consequences
- **Good:** cheap revisions (cached prefix at $0.20/MTok on Opus 5.5), schema-valid plans, no infra to host.
- **Bad:** thinking tokens are billed output and dominate cost at `high`; must be measured.
- **Revisit when:** cost per finished reel > $3, or Editor quality at `medium` matches `high` on the eval set (then drop effort).

## Challenges raised
- "Use Sonnet for the Editor to save money?" → measure first; Opus at lower effort is the recommended first lever before switching models (one cache namespace).
- "Managed Agents is the default for agents" → overridden by local-first and local binaries.
- "Use Google ADK?" → rejected (2026-11-18): multi-agent/model-agnostic layer not needed for one Claude orchestrator; an adapter would hide Claude features we rely on (1-h caching, structured output, effort, fallbacks, Files API). Revisit only for a Gemini second-opinion tool or a multi-agent SaaS on Google Cloud.

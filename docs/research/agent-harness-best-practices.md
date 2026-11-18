# Agent harness best practices for `reel run` decision calls

_Research by a Claude Code docs specialist, 2026-11-18. Official Anthropic sources only; UNDOCUMENTED marks anything not found in them._

## Top 8 harness rules
1. Restrict tools with **`--tools Read`** (`--allowedTools` only pre-approves; unlisted tools that need no approval still run). Add `--permission-mode dontAsk` or `--permission-prompts none`.
2. Decide **`--bare`** explicitly: recommended for scripts, but it requires `ANTHROPIC_API_KEY` (no keychain/OAuth) — conflicts with the Claude Code subscription choice (ADR-0019). Without it, every call loads the user's global CLAUDE.md, hooks, MCP and auto memory.
3. **One fresh session per decision**, state in files; `--resume <id>` only for bounded revision loops, under a per-reel lock.
4. Long tables and contact sheets **first**, the question **last**; tag each block; contact sheets ≤ 2,576 px long edge.
5. Treat missing `structured_output`, `is_error: true`, `refusal` or `max_tokens` as failure; enforce ranges, quotes and enums in `reel validate` (the API does not).
6. Retry by resuming with **actionable** validator messages; cap retries; then fail the stage.
7. Stop with **SIGINT**, not SIGTERM; set `BASH_DEFAULT_TIMEOUT_MS` or drop Bash; `CLAUDE_CODE_RETRY_WATCHDOG=1` for unattended runs; pin version and full model IDs; log `session_id` and `total_cost_usd`.
8. Reviewer = separate fresh call with a bounded rubric; criteria file writable only in status fields. No documented pattern covers cross-run self-improvement.

## 0. Corrections to ADR-0020
- `--allowedTools` only pre-approves → use `--tools Read`. [cli-reference, headless]
- `--bare` skips CLAUDE.md, hooks (incl. the planned SessionStart hook), skills, MCP, auto memory; needs `ANTHROPIC_API_KEY`. **Open decision** vs ADR-0019. [headless]
- A resumed session keeps the system prompt of its first request; a changed `--append-system-prompt-file` applies only after compaction or in a new conversation. [cli-reference]
- `--mcp-config`, `--plugin-dir`, `--add-dir`, `--settings`, `--fallback-model` are not restored on resume — pass every call. [sessions]
- Two `-p` runs resuming one session can lose messages → lock or `--fork-session`. [sessions]
- Transcripts deleted after 30 days (`cleanupPeriodDays`) → keep every stage's inputs/outputs in files. [sessions]
- **Oldest images are silently dropped** once request limits are hit in long resumed sessions. [prompt-caching]
- CLI structured-output retry count is UNDOCUMENTED (SDK documents `error_max_structured_output_retries`). [cli-reference; agent-sdk/structured-outputs]

## 1. Context per decision call
- "Smallest set of high-signal tokens"; context has diminishing returns. [effective-context-engineering]
- Order: persona → schema → long tables/sheets → question (queries at the end can improve quality up to ~30% on long multi-document inputs). [prompting best practices]
- Tag each table/sheet with source metadata; examples in `<examples>`, diverse. [prompting best practices]
- Hybrid retrieval: small index (shot IDs, timecodes, schema) in the prompt; Claude Reads full tables/sheets by path on demand. [effective-context-engineering]
- Image cost ⌈w/28⌉×⌈h/28⌉ visual tokens; high-res tier caps 2,576 px / 4,784 tokens; 600 images per request on 1M-context models, stricter per-image size above 20 images. [vision]
- Few-shot count/placement relative to instructions: UNDOCUMENTED.

## 2. Persona, tools, schema, retries
- `--append-system-prompt-file` keeps Claude Code's default prompt; `--system-prompt-file` replaces it. Skill bodies re-injected after compaction only up to 5,000 tokens. For `-p` calls a version-controlled persona file is simpler. [headless, context-window]
- Start the persona minimal; add rules only after observed failures. [effective-context-engineering]
- Ask the model to self-check against criteria. [prompting best practices]
- Keep the tool set minimal. [writing-tools-for-agents]
- Structured outputs guarantee structure, not semantics: `minimum/maximum/minLength/maxLength` not enforced, enum casing not guaranteed, `format` annotation only; limits 24 optional params, 16 union-type params per request, 180 s compile timeout. [structured-outputs]
- Validator errors must name field, rule and a concrete fix. [writing-tools-for-agents]

## 3. Session strategy
- Default: fresh session per decision; state in `state.json` and plan files (structured note-taking). [effective-context-engineering]
- `--resume <id>` (not `--continue`, which skips `-p` sessions) for bounded revision loops; resumed-turn cap is our own rule. [sessions]
- Don't rely on compaction in headless chains; start a new session with the validated plan. [context-window]
- Cache TTL 5 min on API/usage-credit billing; set `promptCacheTtl: "1h"` or `CLAUDE_CODE_PROMPT_CACHE_TTL=1h`; avoid model/effort changes mid-chain. [prompt-caching]

## 4. Reliability
- Parse `is_error` as well as the exit code (in-run failures print as the result). [headless]
- SIGTERM exits 143 with no result; send SIGINT first. [headless]
- Background tasks awaited up to 10 min; a timed-out Bash command moves to background → early exit 0. Set `BASH_DEFAULT_TIMEOUT_MS` or remove Bash. [headless]
- `CLAUDE_CODE_MAX_RETRIES` default 10; `CLAUDE_CODE_RETRY_WATCHDOG=1` retries 429/529 indefinitely; spend-limit 429s fail at once; usage-limit wait capped by `CLAUDE_CODE_RETRY_WATCHDOG_MAX_USAGE_LIMIT_WAIT_MS`. [errors]
- `--max-turns`, `--max-budget-usd` (client-side estimate). [cli-reference]
- Log `session_id`, `total_cost_usd`, model ID, version; cache creation per TTL bucket. Pin with `claude install <version>` + `DISABLE_AUTOUPDATER=1`; use full model IDs. [headless, prompt-caching, cli-reference]
- No temperature control documented; output determinism UNDOCUMENTED.
- Without `--bare`, `-p` runs project hooks and MCP servers without a trust prompt. [headless]

## 5. Evaluator–optimizer and reflection
- Generator + evaluator loop is best when clear criteria exist; add complexity only when it demonstrably helps. [building-effective-agents]
- A fresh-context reviewer isn't swayed by the generator's reasoning. [best-practices]
- Scope the rubric; a reviewer asked for problems "will always find something". [best-practices]
- Long-running harness pattern: criteria in JSON, agent may only change the pass/fail status; editing or removing tests is unacceptable. [effective-harnesses-for-long-running-agents]
- Cross-run learning / prompt tuning from past runs: no official pattern; eval-gated changes are our own design.

## Sources
code.claude.com/docs/en/{headless, cli-reference, sessions, context-window, prompt-caching, errors, sub-agents, best-practices, agent-sdk/structured-outputs}.md · platform.claude.com/docs/en/build-with-claude/{structured-outputs, vision, prompt-engineering/claude-prompting-best-practices} · anthropic.com/engineering/{building-effective-agents, effective-context-engineering-for-ai-agents, writing-tools-for-agents, effective-harnesses-for-long-running-agents}

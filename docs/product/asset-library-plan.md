# Premium asset library: implementation plan (2026-11-19)

Source: `reports/Premium asset library for AI editor.md` (the research). Its main conclusion: **the licence gate and the per-render manifest matter more than catalogue size.** They come first, because they also protect the 291 assets the engine already uses.

## What exists today

| Piece | Where | Gap |
|---|---|---|
| Licence string per asset (`license`, `attribution`, `credit`, `restrictions`) | the JSON indexes, `stock.py` sidecars, `broll.conform` | Free text. There is no licence registry, no stored licence text hash, and no rules beyond "not NC/SA/ND". |
| NC/SA/ND blocklist | `library.check_licence` (only when indexing) | It does not run at render time. It has no political/sensitive-use, editorial, platform, subscription or single-client rules. |
| Licence snapshot in the timeline | `compile._licence` → `Asset.license/attribution/credit/restrictions` | No licence id. Pips and Lottie graphics are not snapshotted. |
| Package check | `package.build`: unknown licence → refuse; CC BY → `CREDITS.txt` | Covers music and SFX only. It writes no manifest, no licence texts and no receipt. |

Census of what's indexed today:
- SFX (252): 47 owned procedural sounds and 205 Kenney sounds (CC0).
- Music (33): Incompetech tracks (CC BY 4.0, attribution set).
- Lottie (6): owned procedural animations.
- Owned b-roll library: 0.
- Per project: stock b-roll from Pexels/Pixabay and the client's own b-roll.

## Design decisions

1. **The source of truth stays in git-diffable files.**
   - `assets/licenses/registry.yaml`, beside the licence texts, holds the `licences` table: one row per licence version. The manifest records each text's sha256.
   - Texts that the vendor sites block from download (Pexels, Pixabay, Epidemic, Sonniss) are marked `text_kind: missing` with their URL. A paraphrase is never stored as the licence.
   - The existing JSON indexes are the `assets` table: each entry gains `licence_id` and per-asset overrides.
   - The SQLite catalogue in Phase D is a **derived, rebuildable, gitignored** search index, not a second source of truth.
2. **Licence rules live on the licence row; facts about one file live on the asset.**
   - On the licence row: `commercial_ok`, `client_transfer`, `attribution_required`, `sensitive_use` categories, `allowed_platforms`, `subscription`, `per_project_registration`, `deliver_source_files`, `ml_indexing_ok`, `blocked` plus its reason.
   - On the asset: `licence_id`, `editorial_only`, `content_id_registered`, `registrations[]`, `source_url`, `sha256`, `downloaded_at`.
   - Resolution order: an explicit `licence_id`, then an alias match on the old `license` string (old projects keep working), then nothing, which fails the gate.
3. **The gate runs in code, at three points:**
   - **Before ranking:**
     - The indexes stay complete. `idx.refused` holds every asset this brief refuses, with the reasons. It is set in `decide.load_inputs` and in Studio Adjust.
     - The Editor's menus (`decide._allowed`) leave those assets out.
     - `validate_finish` reports `licence_refused` with the reason. The finish stage's validate hook then re-runs the Editor when a cached plan uses an asset that is now refused.
   - **Before render:**
     - `_render` gates the compiled timeline: music, SFX, full-frame b-roll, **pips** (mapped by file) and **Lottie** graphics.
     - No render is spent on a reel that can't be delivered.
   - **At package:**
     - The gate runs again, as the stage's run and its validate hook. The hook means even a cached package is re-checked on every run, for example after a subscription lapses.
     - The package hash includes the brief, the registry and the subscriptions file.
     - A failed gate deletes the old `licences/` folder and raises.
   - **The timeline schema is unchanged.** Licences resolve from the compile-time snapshot, so old timelines don't re-render.
   - `assets/licenses/` is left out of the finish-stage asset hash. A registry edit therefore never buys every project a new finish pass; the validate hooks handle it.
4. **Use context comes from the brief.** The brief gains three fields:
   - `use_categories`: political, dating, drugs, alcohol, gambling, religious, adult.
   - `purpose`: organic, promo or paid_ad. The default, promo, is the strict choice for client work.
   - `accept_credits`: **defaults to true.** False means the client refuses on-screen or caption credits, so CC BY assets are excluded. All 33 current music tracks are CC BY.

   The brief's existing `client` and `platform` fields are reused.
5. **Account state that must not go into git** lives in `~/.config/reel/` (or `$REEL_CONFIG_DIR`; tests point it at a temp folder):
   - `subscriptions.json`: which subscriptions are active and until when, e.g. `{"epidemic": {"active_until": "2027-11-30"}}`.
   - `licence_ledger.jsonl`: which asset went to which client in which project. It is used by the single-client rule.
     - Entries are keyed on asset, client and project, so repackaging the same project adds nothing.
     - An unnamed client counts as different from a named one.
6. **The per-render manifest** is written to `export/package/licences/`:
   - `manifest.json`: per asset, the id, kind, source, URL, file sha256, licence id, licence title and URL, licence-text sha256, attribution, receipts and where it is used. Plus the client, platform, purpose, categories, render time and `reel.mp4` sha256.
   - Copies of each licence text the reel uses.
   - `README.md` points at it. This folder is the client's proof of licence and the dispute packet.

## Phases

| Phase | What | Report action | Status |
|---|---|---|---|
| **A** | Licence registry, resolver, gate (3 points), manifest + licence texts in the package, CC BY credit rule (`accept_credits`), sensitive-use rule, ledger, subscriptions file, backfill (`reel library licences`), stock sidecars carry `licence_id`/`source_url`/`downloaded_at`, Studio Libraries shows the licence id and blocked reasons | 1 | **Building now** |
| B | MIT motion: vendor useAnimations (300 Lottie, MIT) through the existing Lottie safety checks; evaluate remotion-bits / remotion-animated as renderer components; more procedural overlays | 4 | Next |
| C | Curation tooling: `reel library add <file> --licence <id> --source-url …`, which records provenance per file, so hand-picked Pixabay music, Freesound CC0 and 99Sounds files enter with their licence (no bulk downloading) | 5 | After B |
| D | Search index: SQLite + FTS5 (+ sqlite-vec), DSP features (BPM/key/onset already exist for music and SFX), LAION-CLAP `laion/clap-htsat-unfused` for audio and SigLIP 2 for video, **embeddings only where `ml_indexing_ok`**, and a `search_assets` tool with the gate inside plus a live Pixabay branch | 6 | After C |
| E | ElevenLabs SFX generation (needs the owner's paid key), saved as owned assets | 8 | When a key exists |

These are not code tasks; they are left for the owner:
- client contract clauses, reviewed by a lawyer (action 2);
- vendor emails to Sonniss, Epidemic, LottieFiles, Pixabay and Hoopr (action 3);
- a Zapsplat sprint (7);
- Epidemic at the first client (9);
- Hoopr (10).

## Phase A as built (2026-11-19)

**Commands:**
- `reel licences` lists the licence of every library asset. It exits 1 if any asset has none.
- `--backfill` stamps the licence ids.
- `--brief <file>` lists what that brief refuses.

**Backfill result:** all 291 assets resolve.

| Licence | Assets |
|---|---|
| cc0-1.0 | 205 SFX |
| owned | 47 SFX + 6 Lottie |
| cc-by-4.0 | 33 music tracks |

**Where things land:**
- **Package:** each package gets `licences/manifest.json` plus the licence texts and the pack notices.
- **Stock clips:** their sidecars now carry `licence_id`, `source_url`, `sha256` and `downloaded_at`.
- **Studio Libraries:** shows the registry licence and any blocked reason.
- **Tests:** `engine/tests/test_licences.py`.

## Phase A in detail (the original plan)

**New:**
- `reel/licences.py`:
  - `Licence` model;
  - `load_registry()`, `resolve(meta)`;
  - `UseContext.from_brief()`;
  - `refusals(meta, ctx)` → list of `(code, message)`;
  - `gate(tl, idx, ctx)`;
  - `manifest(...)`;
  - ledger and subscriptions helpers.
- `assets/licences/registry.yaml`, with these rows:

| Licence id | Rules |
|---|---|
| `owned` | |
| `cc0-1.0` | |
| `cc-by-4.0` | attribution required |
| `mit` | |
| `pexels` | no resale |
| `pixabay-content` | sensitive use: political |
| `client-supplied` | single client |
| `sonniss-gdc-2.0` | blocked: on hold until written OK |
| `epidemic-pro` | subscription; inactive until the owner adds it |

**Gate refusal codes:**

| Code | Fails when |
|---|---|
| `no_licence` | the asset has no licence row |
| `blocked_licence` | the licence is blocked |
| `editorial_only` | an editorial-only asset sits in a promo or paid-ad reel |
| `sensitive_use` | the client's category hits the licence's sensitive-use list |
| `platform_not_allowed` | the target platform is not allowed |
| `subscription_inactive` | the asset's subscription is not active |
| `registration_missing` | a required per-project registration is missing |
| `single_client` | a single-client asset was already used for another client |
| `credit_refused` | the asset needs attribution but the client refuses credits |
| `attribution_missing` | the licence needs attribution but the asset has no attribution text |

**Changed files:**

| File | Change |
|---|---|
| `Brief` | three new fields |
| `timeline.Asset` | `licence_id` (default `""`, so old timelines still load) |
| `compile._licence` | adds the licence id |
| `project.indexes` | filters by the brief and keeps the refusal reasons |
| `validate_finish` | names the reason when a plan asks for a refused asset |
| `render` stage | runs the gate before rendering |
| `package.build` | runs the gate, writes the manifest and licence texts, records ledger entries |
| `stock.download` | writes `licence_id`, `source_url` and `downloaded_at` into the sidecar |
| `broll.conform` | copies those fields over |
| `lottie.index_folder` | records `licence_id` and sha256 |
| `library.index_*` | record `licence_id` |
| CLI | `reel library licences [--backfill]` |
| Studio | `catalog.libraries` shows the licence id and any blocked reason |

**Tests:**
- every refusal code;
- old timelines with no `licence_id` still pass through the alias match;
- the menu leaves out refused assets;
- the render stage stops on a refused asset;
- the package writes the manifest and licence texts, and refuses on a failed gate;
- the backfill makes every current index entry resolve.

**Not in Phase A:**
- UI for editing the new brief fields. The API accepts them; New edit gets the controls in Phase A2 if wanted.
- Any change to which assets exist.

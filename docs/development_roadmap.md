# Gal Translator Development Roadmap

This roadmap defines the complete path from the current CLI prototype to a usable local Galgame translation product.

The product remains local-only. It does not bypass DRM, does not promise encrypted package cracking, and does not make OCR or real-time LLM translation the default experience. For unsupported packaged games, the supported fallback is Textractor/clipboard capture.

## Final Product Target

A Windows local tool that can:

1. Scan a Galgame exe or folder and produce a useful diagnostic report.
2. Create an isolated translation project outside the game directory.
3. Import source Japanese lines from one of these supported sources:
   - directly readable scripts;
   - verified non-DRM extraction adapters;
   - Textractor/clipboard logs as fallback.
4. Prepare and run offline batch translation through Codex CLI with strict JSON results.
5. Track translation progress and resume safely.
6. Match runtime Japanese text from clipboard/Textractor against translated records.
7. Show translated Simplified Chinese only in an external subtitle surface.

## Phase 1: Scan And Diagnose

Goal: Given an exe or folder, identify the game root, file layout, likely engine/container, and next actionable path.

Deliverables:

- `scan` command outputs UTF-8 JSON.
- Extension counts, directories, file list, and engine candidates are reported.
- `PFS/pf8` archive diagnostics list visible file-table entries without extraction.
- Unsupported packaged games return clear diagnostics rather than pretending import is possible.

Verification:

- Unit tests cover exe root detection, extension grouping, engine ranking, and archive diagnostics.
- Real sample `D:\private\otaku\game\galgame\selectoblige.exe` reports `pf8_pfs_ast` as the top candidate.
- `archive-list --scripts-only` lists `.ast` entries for the real sample.

Status: Implemented.

## Phase 2: Project Workspace

Goal: Create a local project workspace that keeps all tool state outside the game directory.

Deliverables:

- `init` creates project folders under the configured workspace.
- `project.json` records game root, language pair, status, and scan report path.
- `scan-report.json` stores the diagnostic report.
- All generated files go under the project workspace.

Verification:

- Unit tests prove no files are written into the game directory.
- Real sample `init` creates a stable project id and writes project metadata.

Status: Implemented.

## Phase 3: Source Import

Goal: Populate `story-entries.json` and `translation-state.json` from safe source inputs.

Deliverables:

- `import` handles directly readable scripts.
- Direct import is conservative and ignores root readme/patch notes.
- `record-clipboard` can write changed clipboard text to a UTF-8 log; `capture-log` imports Textractor/clipboard logs, removes empty and repeated lines, and tolerates UTF-8 BOM.
- Unsupported packaged games initialize an empty state instead of leaving half-created projects.

Verification:

- Unit tests cover direct script import, story filtering, capture-log import, duplicate suppression, and empty-state fallback.
- Real sample fallback smoke: `capture-log` creates pending entries from a sample clipboard log.

Status: Implemented.

## Phase 4: Batch Translation

Goal: Make translation batches reproducible, reviewable, resumable, and compatible with Codex CLI.

Deliverables:

- `batch` prints the next pending prompt.
- `prepare-codex` writes `prompt.txt`, `schema.json`, `command.json`, and the expected `result.json` path.
- `apply-result` applies strict result JSON and accepts UTF-8 BOM.
- `run-codex` can execute the prepared command when explicitly invoked by the user.

Verification:

- Unit tests cover batch selection, prompt style requirements, schema generation, command shape, and result application.
- Smoke test: capture log -> prepare batch -> apply sample result -> progress becomes ready.

Status: Implemented.

## Phase 5: Runtime Matching

Goal: Match runtime Japanese text to translated Simplified Chinese locally and quickly.

Deliverables:

- `lookup` returns Chinese-only display text for exact and normalized matches.
- `watch-clipboard` watches Windows clipboard and emits JSON subtitle events.
- Matching handles whitespace and repeated clipboard text.
- Unmatched text emits empty translation without source text by default.

Verification:

- Unit tests cover exact, normalized, unmatched, and untranslated records.
- Smoke test: apply a sample translation and `lookup` returns Chinese only.

Status: Implemented for CLI/JSON output.

## Phase 6: External Subtitle Surface

Goal: Provide a practical external subtitle surface over or beside the game.

Deliverables:

- Minimal local window that subscribes to clipboard changes and displays matched Chinese text.
- Always-on-top option.
- Font size and opacity configuration.
- No source Japanese in default display.
- Non-matching state is visually quiet.

Verification:

- Unit tests cover view-model/state formatting where possible.
- Manual Windows smoke test confirms the window starts, remains responsive, and updates from clipboard text.

Status: Minimal Tkinter surface implemented with a testable view-model layer. Window position, font family, colors, opacity clamping, dry-run config validation, and optional stale-text clearing are implemented. Manual interactive smoke still required.

## Phase 7: Real Workflow Hardening

Goal: Make the tool robust enough for repeated game sessions.

Deliverables:

- Better CLI errors with actionable next steps.
- Project status transitions are explicit.
- Batch logs and runtime event logs are written under project `logs/`.
- Import/capture can append new lines without duplicating existing entries.
- Existing projects can append new logs without rescanning large game archives.
- Configurable source names for multiple hooks/logs.
- Failed translation items can be moved back to pending for retry.
- `workflow-fallback` runs the packaged-game fallback path as one command.

Verification:

- Unit tests cover append import, duplicate handling across sessions, error payloads, and progress summaries.
- Real sample smoke: add more captured lines, translate only new pending entries, and keep old translations.

Status: Partially implemented. `project-info`, `clear-lock`, clipboard recording, append capture, `append-log`, `translate-log`, `translate-log --watch`, project translation locking, `workflow-fallback`, Codex logs, runtime event logs, runtime miss logs, runtime state auto-reload, `retry-failed`, `translate-all`, `play-session`, `scripts/live-session.ps1`, and `doctor` exist. Result application is now strict enough to report applied, failed, missing, unknown, duplicate, empty, and invalid items; prepared batches write `batch.json` so missing expected ids can be marked failed. Default Codex logs use per-run directories. Common missing-state, missing-log, invalid-result, invalid-batch, and active-lock failures now return structured JSON errors. `project-info` also reports malformed project metadata and translation lock state through recovery payloads, while `clear-lock` removes stale writer locks only after checking the recorded process id. `translate-all` can run and apply repeated Codex batches until pending entries are exhausted.

## Phase 8: Optional Engine Adapters

Goal: Add engine/container adapters only when safe and verifiable.

Deliverables:

- Adapter profile documents the exact supported engine/version/tool.
- Adapter writes extracted scripts only under the project workspace.
- Adapter never modifies game files.
- Unsupported/encrypted packages return diagnostics and fallback guidance.

Verification:

- Fixture tests use non-protected sample files.
- Real-game validation uses only verified tool output or user-provided decoded files.

Status: `PFS/pf8` listing is implemented; extraction is blocked for the real sample because `.ast` payloads are encrypted/non-plaintext and public PF8 references describe XOR encryption.

## Phase 9: Packaging And Handoff

Goal: Package the CLI and subtitle surface for normal local use.

Deliverables:

- Windows launch scripts.
- Example workflow in README.
- Minimal troubleshooting guide.
- Release checklist.

Verification:

- Fresh workspace smoke test.
- Real sample fallback workflow smoke test.
- No generated state lands in the game directory.

Status: Partially implemented. PowerShell launch scripts and release checklist exist; packaged binary/distribution is not implemented.

## Current Continuous Development Rule

Continue implementing phases in order without waiting for user input unless:

- a step would require DRM bypass or encrypted package cracking;
- a real interactive game/Textractor/manual window test is required;
- a missing external tool or decoded file must be supplied by the user;
- network/cost-incurring Codex execution should be explicitly run rather than only prepared.

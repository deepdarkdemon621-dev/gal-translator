# Gal Translator Project Record

Last updated: 2026-05-24 pause checkpoint

## Project Goal

Build a local Galgame translation workflow that can:

1. Capture or import Japanese game text.
2. Batch translate all pending entries through Codex CLI.
3. Apply translation results into a local project state.
4. Match runtime game text locally.
5. Show Simplified Chinese only in an external subtitle window while the game runs.
6. Recover interrupted or failed sessions without rebuilding commands by hand.

MVP direction:

- Primary path: pre-extracted scripts or Textractor/clipboard capture -> offline batch translation -> local matching -> external bilingual workflow via subtitle window.
- Do not write translated text back into the game UI for MVP.
- Do not make OCR or realtime LLM translation the default runtime experience.
- Do not handle DRM bypass or promise encrypted archive cracking.

## Repository Structure

- `gal_translator/`: Python package and CLI implementation.
- `gal_translator/cli.py`: Main command surface and orchestration.
- `gal_translator/importer.py`: Direct script import plus Artemis `.ast` import/parsing.
- `gal_translator/desktop.py`: Tk desktop product shell and command builders for the two-entry workflow.
- `gal_translator/capture.py`: Textractor/clipboard log import and capture statistics.
- `gal_translator/subtitle_window.py`: Tk subtitle window, view model, and reusable window config.
- `gal_translator/translator.py`: Codex batch prompt/schema/result application logic.
- `gal_translator/progress.py`: Translation state tracker.
- `gal_translator/runtime.py`: Runtime matching and reloadable subtitle service.
- `gal_translator/scanner.py`, `detector.py`, `archives.py`, `profiles.py`: Game scan and diagnostic import support.
- `scripts/`: PowerShell wrappers for Windows play/recovery flows.
- `tests/`: Unit and CLI integration tests.
- `docs/`: Workflow docs, roadmap, and release checklist.
- `README.md`: User-facing command overview.
- `progress.md`: Detailed chronological implementation log.
- `task_plan.md`: Resume notes and longer-term plan.
- `findings.md`: Real-game findings and constraints.
- `PROJECT_RECORD.md`: Compact project status and task board for new conversations.

## Current Verified Baseline

- Environment check: `python -m gal_translator doctor` -> `status=ready`; Codex is on PATH, Tkinter imports, and the default workspace is writable.
- Full test suite: `python -m unittest discover -v` -> 144 tests passed.
- Desktop shell dry-run: `python -m gal_translator desktop --dry-run` -> `status=ready` with Translation Preparation and Play Output entries, including Play Output `source-log-session` and a `sourceLogSession` command template.
- Global skill setup: `any-search` installed from `https://github.com/anysearch-ai/anysearch-skill.git` into `C:\Users\deepd\.codex\skills\any-search`; restart Codex to load it. `skill-creator` is already installed as a system skill.
- Synthetic end-to-end smoke: `python -m gal_translator smoke-test --workspace .tmp-smoke-resume-record-afterfix` -> `status=passed` with every `checks` value true.
- Optional self-closing UI smoke: `python -m gal_translator smoke-test --workspace .tmp-smoke-ui --open-subtitle --subtitle-exit-after 1`.
- Recovery diagnostics include bounded `tailLines` arrays for Codex stdout/stderr and saved watcher stdout/stderr summaries, alongside `lastLine` / `lastEvent`.
- Real-log diagnostics include `inspect-log.status`, `nextActions`, `uniqueImportedEntryCount`, and `repeatedSourceCount`.
- Real sample recheck: `python -m gal_translator scan "D:\private\otaku\game\galgame\selectoblige.exe"` still reports `pf8_pfs_ast` first, with 220 visible `.ast` entries in `selectoblige.pfs`.
- Archive diagnostic recheck: `python -m gal_translator archive-list "D:\private\otaku\game\galgame\selectoblige.exe" --scripts-only --limit 5` lists five `script\*.ast` entries from `selectoblige.pfs`; this remains diagnostic-only, with no extraction/decryption.
- Artemis script export recheck: `pfs-rs` v0.2.5 extracted 220 readable UTF-8 `script\*.ast` files from `selectoblige.pfs` into the LocalAppData experiment workspace; estimated text volume is about 50,924 Japanese story string segments and 866,592 Japanese story characters.
- Artemis importer smoke: `python -m gal_translator import-artemis-ast "C:\Users\deepd\AppData\Local\GalTranslator\real-session-selectoblige\pfs-rs-extract-selectoblige-pfs-v0.2.5" --workspace ".tmp-artemis-import-smoke"` copied 220 `.ast` files and generated 32,978 merged pending story entries; the first entry is `「これが最後の質問だ」` with speaker `？？？`.
- Artemis translation project: `C:\Users\deepd\AppData\Local\GalTranslator\real-session-selectoblige\artemis-script-project\projects\pfs-rs-extract-selectoblige-pfs-v0.2.5-b56875e0b374` has 6,950 translated, 26,028 pending, 0 failed. Latest full-batch continuation summary is `logs\translate-all-summary-20260524T194733.json`; the last full-batch applied id was `script/01_06奏命編_01.ast:4515`. Full archive translation is now paused by default to control token spend. The project keeps the translated entries as a local match base, and runtime miss/source logs should be fed through `translate-log --only-new-log-entries` so only log-referenced entries are translated. This covers both newly appended miss text and existing imported pending script entries. Real scoped proof translated existing pending id `script/01_06奏命編_01.ast:4529` from `本当の殺意とは……心が底冷えしていくものだと、誰かが言っていた。` to `真正的杀意……有人说过，是会让内心寒彻骨髓的东西。` A later live-reload proof appended `script/01_06奏命編_01.ast:4545` to a source log while `subtitle-window` was running: the window first logged it as unmatched and wrote it to miss-log, then a background scoped watcher translated it to `无论内心如何狂乱翻涌，在明确怀抱杀意的那一瞬间，一切都彻底冷却了。`, and the same running window reloaded to exact visible Chinese. Evidence logs: `logs\live-reload-smoke-subtitle-events.jsonl` and `logs\live-reload-smoke-watcher-stdout.jsonl`.
- Source-log session launcher: `scripts/source-log-session.ps1` starts a scoped `translate-log --watch --only-new-log-entries` watcher plus `subtitle-window --source-log` for an already imported project. It intentionally omits `--watch-require-ready`, defaults to `BatchSize=1` / `MaxBatches=1`, writes session logs under the project `logs` directory, and has a real-project dry-run against the persistent `selectoblige` Artemis project with `SourceName=lunahook`. The desktop Play Output tab now exposes the same path as `source-log-session`. Non-dry-run startup creates the source log parent directory and empty file when missing; the prepared real path is `C:\Users\deepd\AppData\Local\GalTranslator\real-session-selectoblige\lunahook-source.txt`. Every run writes `sessionReportPath` with `restartCommand`, watcher/subtitle commands, pids, and log paths; latest bounded real report is `logs\source-log-session-20260524-210145-report.json`. A persistent real source-log session is currently running from `logs\source-log-session-20260524-210406-report.json` with watcher pid 11584 and subtitle-window pid 43600. A verified append of `「これが最後の質問だ」` to the prepared source log was processed by that same running watcher at cycle 349 with `lastProcessedScopedTranslatedCount=1`, `plannedBatchCount=0`, and `lastProcessedLogEntryIds=["script/01_01プロローグ_01.ast:16"]`; the running subtitle window wrote exact visible translated output without logging a miss, and project progress stayed at 6,950 translated / 26,028 pending / 0 failed. `session-info` recognizes these reports as `reportType=source-log-session`, returns `sourceLogSessionCommand` to restore the full scoped watcher + subtitle window, keeps both current idle state and `lastProcessedEvent` diagnostics, and warns not to use `translateAllCommand` unless global pending translation is intentional. If PowerShell launcher stdout is empty after starting the hidden watcher, use the saved `sessionReportPath` plus `session-info`; the report is the reliable recovery channel.
- Codex result-ready recovery: `translate-all` now polls for a complete `result.json` while Codex is running, stops the process tree once all expected ids are present, and reports the batch as `result_ready_process_stopped`. Valid result output written before a timeout is still applied instead of discarded.
- Recovery command hardening: default synthesized `subtitle-window` resume commands now omit unset `--x` / `--y` instead of emitting `None`.
- Failed translation recovery is bounded: failed entries can be reset for retry at most 3 times, then `retry-failed` skips them and surfaces an abandon/ignore reminder through retry payloads and `project-info.failedRetry`.
- Real game menu smoke: manually captured five visible `selectoblige` menu lines, translated them through real Codex, replay matched 5/5, and showed Chinese in a real external subtitle window screenshot.
- Real hooked story closed loop: LunaHook from LunaTranslator x64 identified the sample as Artemis, captured `「これが最後の質問だ」`, Codex translated it as `“这是最后一个问题。”`, replay matched 1/1, and a live `subtitle-window --source-log` showed the Chinese subtitle over the running game while the game displayed the Japanese line.
- Textractor status: Textractor 5.2.0 is installed under `C:\Users\deepd\Desktop\Textractor`, but CLI auto-attach currently only emits the Clipboard thread for this sample. LunaHook is the verified hook path for this sample.
- Pause checkpoint: the latest active source-log session is `logs\source-log-session-20260524-225357-report.json` for project `C:\Users\deepd\AppData\Local\GalTranslator\real-session-selectoblige\artemis-script-project\projects\pfs-rs-extract-selectoblige-pfs-v0.2.5-b56875e0b374`, source log `C:\Users\deepd\AppData\Local\GalTranslator\real-session-selectoblige\lunahook-source.txt`, game pid `26324`, watcher pid `3292`, subtitle-window pid `14860`, LunaHook bridge pid `37836`, clipboard bridge disabled. Latest proof: Hook text `窶補輔≠縺ゅ∝､ｱ謨励＠縺溘Ａ` matched `script/01_01繝励Ο繝ｭ繝ｼ繧ｰ_01.ast:143` and displayed subtitle `窶披泌賦蝠奇ｼ梧裾遐ｸ莠・Ａ` with exact visible output. Full archive translation remains paused at `6950/32978`; resume with scoped source-log translation, not global `translate-all`, unless explicitly requested.

Important: the real `selectoblige.exe` sample has now been validated end-to-end through external Hook capture, real Codex batch translation, replay coverage, and an actual subtitle window while the game is running. Continue hardening reusable tooling around that verified path.

## Main CLI Workflow

Real-log diagnostic and import:

```powershell
python -m gal_translator inspect-log ".\textractor-log.txt" --source-name textractor
python -m gal_translator capture-log "D:\Games\Game\game.exe" ".\textractor-log.txt" --workspace "$env:LOCALAPPDATA\GalTranslator" --source-name textractor
python -m gal_translator append-log "$env:LOCALAPPDATA\GalTranslator\projects\<project-id>" ".\textractor-log.txt" --source-name textractor
```

Pre-extracted Artemis script import:

```powershell
python -m gal_translator import-artemis-ast "C:\Path\To\pfs-rs-extract" --workspace "$env:LOCALAPPDATA\GalTranslator"
python -m gal_translator import "C:\Path\To\pfs-rs-extract" --workspace "$env:LOCALAPPDATA\GalTranslator"
```

Full translation and replay:

```powershell
python -m gal_translator translate-all "$env:LOCALAPPDATA\GalTranslator\projects\<project-id>" --size 40 --dry-run
python -m gal_translator translate-all "$env:LOCALAPPDATA\GalTranslator\projects\<project-id>" --size 40 --timeout 600
python -m gal_translator translate-all "$env:LOCALAPPDATA\GalTranslator\projects\<project-id>" --size 40 --timeout 600 --retry-failed
python -m gal_translator replay-log "$env:LOCALAPPDATA\GalTranslator\projects\<project-id>" ".\textractor-log.txt" --source-name textractor --event-log ".\replay-events.jsonl"
python -m gal_translator translate-log "$env:LOCALAPPDATA\GalTranslator\projects\<project-id>" ".\misses.txt" --only-new-log-entries --size 40 --max-batches 1 --timeout 600
```

Runtime subtitle:

```powershell
python -m gal_translator subtitle-window "$env:LOCALAPPDATA\GalTranslator\projects\<project-id>" --source-log ".\textractor-log.txt" --source-log-name textractor --miss-log ".\misses.txt"
python -m gal_translator subtitle-window "$env:LOCALAPPDATA\GalTranslator\projects\<project-id>" --dry-run --save-config ".\subtitle-window.json"
python -m gal_translator subtitle-window "$env:LOCALAPPDATA\GalTranslator\projects\<project-id>" --config ".\subtitle-window.json"
```

One-command play/session paths:

```powershell
python -m gal_translator play-session "D:\Games\Game\game.exe" ".\textractor-log.txt" --workspace "$env:LOCALAPPDATA\GalTranslator" --subtitle-source-log --subtitle-preview-first-match --subtitle-miss-log ".\misses.txt" --session-report ".\play-session-report.json"
python -m gal_translator live-session "D:\Games\Game\game.exe" ".\textractor-log.txt" --workspace "$env:LOCALAPPDATA\GalTranslator" --subtitle-detach --subtitle-source-log --subtitle-miss-log ".\misses.txt" --subtitle-preview-first-match
.\scripts\source-log-session.ps1 -ProjectRoot "$env:LOCALAPPDATA\GalTranslator\projects\<project-id>" -SourceLog ".\lunahook-source.txt" -SourceName lunahook
python -m gal_translator session-info ".\play-session-report.json"
python -m gal_translator resume-session ".\play-session-report.json" --open-subtitle --start-miss-watcher --start-session-log-watcher --retry-failed
```

Desktop shell:

```powershell
python -m gal_translator desktop
python -m gal_translator desktop --dry-run
```

## Task Board

### Done

- [x] Basic project scanner and engine detector.
- [x] Direct script import pipeline.
- [x] Textractor/clipboard capture import.
- [x] Capture statistics: raw, candidate, duplicate, non-Japanese, imported, unique imported, and repeated source counts.
- [x] `inspect-log` for log quality checks without creating a project, including status and nextActions diagnostics.
- [x] Translation progress state and strict result application.
- [x] Codex batch preparation, execution, result application, and per-run logs.
- [x] `translate-all` for repeated pending-batch execution.
- [x] `translate-all --retry-failed` for direct failed-entry retry inside the translation lock.
- [x] Project translation lock and stale-lock recovery.
- [x] Runtime local matching and replay checks.
- [x] Runtime events omit source text by default.
- [x] External Tk subtitle window.
- [x] Subtitle preview, source-log input, reload on updated translation state, miss-log feedback.
- [x] Reusable subtitle layout/style config via `--config` / `--save-config`.
- [x] `play-session` one-command capture/translate/replay/subtitle path.
- [x] Python `live-session` supervisor with background miss/session-log watchers.
- [x] PowerShell wrappers under `scripts/`.
- [x] Saved session reports, `session-info`, and `resume-session`.
- [x] Retry-failed recovery through both `resume-session --retry-failed` and `translate-all --retry-failed`.
- [x] Failed-entry retry limit: max 3 retry resets, then warn the user that isolated lines can usually be abandoned.
- [x] Bounded log-tail diagnostics for failed Codex batches and saved miss/session-log watcher reports.
- [x] Synthetic `smoke-test` covering capture, translation, replay, subtitle dry-run, saved-report recovery, live-session dry-run, retry recovery, and source-log feedback.
- [x] Default synthesized subtitle resume commands omit unset position arguments instead of writing `--x None --y None`.
- [x] Windows clipboard provider handles 64-bit clipboard handles without `GlobalLock` overflow.
- [x] Real visible-menu translation smoke for `selectoblige.exe`: import -> Codex translate -> replay -> external subtitle-window preview.
- [x] Real hooked story closed loop for `selectoblige.exe` through LunaHook: live Hook capture -> import -> Codex translate -> replay -> live external subtitle-window screenshot.
- [x] Read-only Artemis/PFS script export experiment with pfs-rs: 220 readable `.ast` scripts extracted from `selectoblige.pfs`.
- [x] Install user-provided `any-search` skill globally; confirm `skill-creator` is already available.
- [x] First Tk desktop product shell: Translation Preparation and Play Output entries over the verified CLI workflow.
- [x] Desktop shell dry-run payload and command-builder tests.
- [x] Artemis `.ast` importer for exported scripts: parse `text.ja`, preserve speaker names, skip control commands, and create translation state.
- [x] Scoped miss/source-log translation: `translate-log --only-new-log-entries` translates only log-referenced entries, including existing imported pending script text, and avoids unrelated global archive pending work.
- [x] Full local test baseline: 136 tests passed.

### In Progress

- [x] Turn the current synthetic and fixture-verified workflow into a real-game validated workflow.
- [x] Build the first desktop product shell around the verified CLI workflow.
- [ ] Keep hardening recovery payloads and next actions when real logs expose gaps.
- [ ] Keep task/progress records updated after each completed slice.

### Next

- [x] Find a working Hook path for `selectoblige.exe`: LunaHook inserted Artemis hooks `ENHVXN-24@195720:selectoblige.exe` and `HVXN-4C@1971E0:selectoblige.exe`.
- [x] Run `inspect-log` on an actual hooked story log.
- [x] If `inspect-log.status` is ready and `captureStats.uniqueImportedEntryCount` is useful, run `capture-log` or `append-log`.
- [x] Run real `translate-all`.
- [x] Run `replay-log --event-log` against the same real captured log.
- [x] Open `subtitle-window` while the game is running.
- [x] Verify runtime display shows translated Simplified Chinese only.
- [ ] Verify `--source-log` tailing, miss-log feedback, and background watcher behavior during real play.
- [x] Design the UI flow with two entries: translation preparation and play output.
- [x] Implement the translation preparation UI: choose game/source directory, inspect/import, translate, progress, failed retry status, and 3-failure abandon reminder.
- [x] Implement the play output UI: source-log/Hook follow mode, local matching status, styled external subtitle display, and miss-log feedback.
- [ ] Run a manual interactive desktop-shell smoke during real play and tune the UI based on actual operator friction.
- [x] Implement an Artemis `.ast` importer for exported scripts: parse `text.ja` blocks, preserve speaker names, skip control commands, and feed the existing batch translation state.
- [x] Run a small real Codex batch from the imported Artemis script project, then replay/lookup against known lines before bulk translation.
- [x] Validate scoped miss-log/source-log feedback against an existing imported pending Artemis line, including real Codex translation and subtitle-window display.
- [x] Confirm source-log live reload after a background scoped watcher translates a newly encountered pending line.
- [x] Add `scripts/source-log-session.ps1` launcher and desktop Play Output command for paused-full-archive play loops: scoped watcher plus source-log subtitle window without readiness guard.
- [ ] Run a longer manual LunaHook play-session/source-log tail and tune window placement/launcher UX.
- [x] Record real-game constraints in `findings.md`.

### Blocked On External State

- [x] A real game folder or executable for scan/archive diagnostics: `D:\private\otaku\game\galgame\selectoblige.exe`.
- [x] A real external Hook capture log containing Japanese story text.
- [x] A manual Windows desktop run showing the visible subtitle window over/near the running game for manually captured visible menu text.
- [x] A live Windows desktop run showing the visible subtitle window over the running game for hooked story text.

## New Conversation Resume Prompt

Use this when starting a fresh chat:

```text
Continue development in D:\Projects\11.gal-translator. Read AGENTS.md and PROJECT_RECORD.md first. The local Galgame translation workflow has been validated against the real `selectoblige.exe` sample through LunaHook, and the Artemis `.ast` route is active. The persistent script project is `C:\Users\deepd\AppData\Local\GalTranslator\real-session-selectoblige\artemis-script-project\projects\pfs-rs-extract-selectoblige-pfs-v0.2.5-b56875e0b374`; it imported 220 `.ast` files and currently has 6,950 translated, 26,028 pending, 0 failed. Full archive translation is paused by default to control token spend. Use the translated entries as the local match base, then feed runtime Hook/source-log/subtitle misses through `translate-log --only-new-log-entries` so only log-referenced entries are translated. The reusable PowerShell path is `scripts/source-log-session.ps1 -ProjectRoot <project> -SourceLog <lunahook-source-log> -SourceName lunahook`, which starts a scoped watcher plus `subtitle-window --source-log` without `--watch-require-ready`; defaults are `BatchSize=1` and `MaxBatches=1`, and non-dry-run startup creates the source log when missing. It also writes a `sessionReportPath` with `restartCommand`, watcher/subtitle commands, pids, and log paths; `session-info` recognizes this as `reportType=source-log-session` and returns `sourceLogSessionCommand` for restoring the full scoped watcher + subtitle window. The prepared real source-log path is `C:\Users\deepd\AppData\Local\GalTranslator\real-session-selectoblige\lunahook-source.txt`; latest bounded real report is `logs\source-log-session-20260524-210145-report.json`; current persistent real session report is `logs\source-log-session-20260524-210406-report.json` with watcher pid 11584 and subtitle-window pid 43600 active. The current session already processed an append of `「これが最後の質問だ」` at watcher cycle 349 with no Codex batch, exact visible subtitle output, and unchanged project progress; `session-info` now preserves `lastProcessedEvent` even after the watcher returns to idle. The desktop Play Output tab exposes the same path as `source-log-session`, and `desktop --dry-run` includes a `sourceLogSession` command template. Real live-reload proof appended `script/01_06奏命編_01.ast:4545` to a source log while `subtitle-window` was running; the window first logged unmatched with `missLogged=true`, then a background scoped watcher translated exactly that entry, and the same window reloaded to exact visible Chinese. Current verified baseline is python -m unittest discover -v -> 136 tests passed, python -m gal_translator doctor -> ready, and python -m gal_translator desktop --dry-run -> status=ready. Keep MVP scope: external subtitle output and local matching only; no in-game text rewrite, no DRM bypass, no archive cracking promises, no OCR-first flow, and no realtime Codex translation as the default gameplay path. Next useful work is configuring LunaHook/Textractor to append actual runtime text to the prepared source-log path during the running source-log session; if launcher stdout is empty, recover with `python -m gal_translator session-info <sessionReportPath>`.
```

Updated resume delta:

- New reusable launcher: `scripts/source-log-session.ps1 -ProjectRoot <project> -SourceLog <lunahook-source-log> -SourceName lunahook`.
- It starts `translate-log --watch --only-new-log-entries` plus `subtitle-window --source-log` without `--watch-require-ready`; defaults are `BatchSize=1` and `MaxBatches=1`.
- Current verified baseline after this launcher slice: `python -m unittest discover -v` -> 136 tests passed.

Updated paused-full-archive source-log delta:

- Added `python -m gal_translator source-log-status <project_root> <source_log>` for the cost-controlled play loop.
- It reports `mode=paused_full_archive_scoped_source_log`, project progress, source-log import stats, saved watcher/subtitle process health, and optional game/Hook process checks.
- Current real project progress remains intentionally partial: `32978` total, `6950` translated, `26028` pending, `0` failed, `21.07%`.
- Real status check reports `selectoblige.exe` pid `4492`, LunaTranslator pid `13540`, source-log watcher pid `11584`, and subtitle-window pid `43600` active.
- The active watcher is idle on unchanged source log, but `session-info`/`source-log-status` still expose the last processed proof from cycle `349`: `lastProcessedSessionStatus=translation_ready`, `lastProcessedScopedTranslatedCount=1`, and `lastProcessedLogEntryIds=["script/01_01プロローグ_01.ast:16"]`.
- The remaining external step is configuring/confirming LunaHook appends fresh runtime story text into `C:\Users\deepd\AppData\Local\GalTranslator\real-session-selectoblige\lunahook-source.txt`.
- Current verified baseline: `python -m unittest discover -v` -> 137 tests passed.

Updated LunaHook bridge delta:

- Added `luna-hook-bridge` as the current preferred capture bridge for `selectoblige.exe` when full archive translation is paused. It uses the local LunaTranslator `files/LunaHook` host/hook DLLs to append runtime Hook text directly into `C:\Users\deepd\AppData\Local\GalTranslator\real-session-selectoblige\lunahook-source.txt`.
- Real clean source-log session is now `logs\source-log-session-20260524-215636-report.json`, with watcher pid `31704`, subtitle-window pid `30304`, clipboard bridge disabled, and background LunaHook bridge pid `6252`.
- Real closed-loop proof after clicking `START` and the in-game next-arrow:
  - Captured `「これが最後の質問だ」`.
  - Captured `「ワン・ズ・ギフトの権利を不正に手に入れたと認めれば、法の下で裁いてやる」`.
  - The scoped watcher matched imported Artemis ids `script/01_01プロローグ_01.ast:16` and `script/01_01プロローグ_01.ast:35`.
  - The subtitle event logged exact Chinese `「只要你承认是非法取得了 One's Gift 的权利，我就会依法审判你」`.
- Project progress remains intentionally partial and restored after cleanup: `32978` total, `6950` translated, `26028` pending, `0` failed.
- Keep clipboard bridge opt-in only for this sample because it can consume unrelated clipboard text.

Unified source-log session update:

- `scripts/source-log-session.ps1 -StartLunaHookBridge` now starts the direct LunaHook bridge alongside the scoped watcher and subtitle window, and the saved report includes `lunaHookBridge`.
- `session-info` and `source-log-status` surface the LunaHook bridge process, command, and JSONL status log.
- Latest real session is `logs\source-log-session-20260524-221940-report.json`, with watcher pid `43408`, subtitle-window pid `24088`, LunaHook bridge pid `18108`, and clipboard bridge disabled.
- Latest integrated proof: runtime capture `「もし認めないのなら……」` -> imported Artemis id `script/01_01プロローグ_01.ast:55` -> exact visible subtitle `「如果你不承认的话……」`.
- Project progress remains intentionally partial: `32978` total, `6950` translated, `26028` pending, `0` failed.

Desktop Play Output LunaHook delta:

- `python -m gal_translator desktop --dry-run --source-name lunahook --start-luna-hook-bridge --luna-hook-game-process selectoblige.exe` now emits a `sourceLogSession` command template with `-StartLunaHookBridge`, `-LunaHookGameProcess selectoblige.exe`, the two verified Artemis hook codes, and scoped cost controls `-BatchSize 1 -MaxBatches 1`.
- Default desktop behavior remains conservative: LunaHook bridge disabled unless requested, clipboard bridge omitted, and Play Output still avoids global `translate-all`.
- Fresh real status check still reports `status=watching_source_log`, watcher pid `43408`, subtitle-window pid `24088`, LunaHook bridge pid `18108`, clipboard bridge disabled, and progress `6950/32978`.
- Focused verification: `python -m unittest tests.test_desktop -v` -> 9 tests passed; focused source-log/LunaHook CLI tests -> 3 tests passed.
- Full regression verification: `python -m unittest discover -v` -> 140 tests passed.

Live game-window closed-loop delta:

- Advanced the real `selectoblige.exe` story window once after the integrated session was already running.
- LunaHook captured `「選べ。認めるか、認めないか」`; the scoped source-log watcher matched imported Artemis id `script/01_01プロローグ_01.ast:73`; the subtitle event log displayed exact Chinese `「选吧。承认，还是不承认」` with `matchType=exact`, `visible=true`, and `missLogged=false`.
- `source-log-status` now includes `subtitleWindow.eventLog` parsed from the saved source-log session `eventLog`, so closed-loop status no longer requires manual tailing of subtitle JSONL files.
- Current live session remains partial and scoped: source log 4 unique importable lines, progress `6950/32978`, watcher pid `43408`, subtitle-window pid `24088`, LunaHook bridge pid `18108`, clipboard bridge disabled.
- Verification after this diagnostic update: `python -m unittest discover -v` -> 140 tests passed.

Closed-loop cleanup and current session delta:

- `source-log-status` now includes `closedLoopProof`, combining latest source-log text, LunaHook capture text, watcher matched ids, subtitle event text/match/visibility, and process activity.
- Added UI/control help filtering for source logs. The live `タッチパネル用ＵＩ...` help string was removed from the real source log and from project state; project progress returned to `32978` total / `6950` translated / `26028` pending / `0` failed.
- `LunaHookBridge` now seeds duplicate detection from the existing source log in append mode so a restarted bridge skips already-present text.
- Current fresh integrated session:
  - Report: `logs\source-log-session-20260524-224421-report.json`
  - Game pid `26324`
  - Watcher pid `34316`
  - Subtitle-window pid `46516`
  - LunaHook bridge pid `41028`
  - Clipboard bridge disabled
- Latest closed-loop proof: re-entered START, Hook captured `「これが最後の質問だ」`, subtitle displayed `「这是最后一个问题」`, and `closedLoopProof.status=closed_loop_displayed`.
- Current verified baseline: `python -m unittest discover -v` -> 142 tests passed.

Stronger UI-filter and latest active session:

- UI/control filtering now catches short menu/help strings and the LunaHook bridge applies it before writing source-log lines.
- Removed old pre-patch UI/control noise from the real source log and project state; progress is back to `32978` total / `6950` translated / `26028` pending / `0` failed.
- Current active session:
  - Report: `logs\source-log-session-20260524-225357-report.json`
  - Game pid `26324`
  - Watcher pid `3292`
  - Subtitle-window pid `14860`
  - LunaHook bridge pid `37836`
  - Clipboard bridge disabled
- Latest live proof: Hook captured `――ああ、失敗した。`, watcher matched imported Artemis id `script/01_01プロローグ_01.ast:143`, subtitle displayed `——啊啊，搞砸了。`, and `closedLoopProof.status=closed_loop_displayed`.
- Current verified baseline: `python -m unittest discover -v` -> 144 tests passed.

Updated clipboard-bridge delta:

- `scripts/source-log-session.ps1` now accepts `-StartClipboardBridge` to cover LunaHook/Textractor configurations that copy captured text to the clipboard instead of appending a source-log file.
- The bridge starts `record-clipboard` against the same source log used by the scoped watcher and subtitle window.
- The saved source-log session report now includes a `clipboardBridge` payload with command, pid, stdout path, and stderr path; `session-info` and `source-log-status` expose it when present.
- Temporary smoke verified clipboard text `これは橋接テストです。` was appended into a temp source log with `capturedCount=1`, then the previous clipboard was restored.
- The current real resumed source-log session is `logs\source-log-session-20260524-214004-report.json`; it has game pid `31832`, LunaTranslator pid `23440`, watcher pid `33176`, subtitle-window pid `36956`, and clipboard bridge pid `20228` active. `source-log-status` reports `status=watching_source_log`.

## Maintenance Rule

After each completed development slice:

1. Update the relevant task checkbox in this file.
2. Add detailed notes to `progress.md`.
3. Update `task_plan.md` with the current resume point.
4. Run focused tests, then full tests when the slice touches CLI workflow behavior.

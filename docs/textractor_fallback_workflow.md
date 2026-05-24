# Textractor / Clipboard Fallback Workflow

Use this workflow when `scan` shows a packaged game whose scripts cannot be safely imported directly.

This is the expected path for the current real sample:

```text
D:\private\otaku\game\galgame\selectoblige.exe
```

The sample uses Artemis `PFS/pf8` archives. The tool can list `.ast` entries, but payloads are not plaintext and are not imported.

## 1. Scan The Game

```powershell
python -m gal_translator scan "D:\private\otaku\game\galgame\selectoblige.exe"
```

Expected result:

- `engineCandidates[0].engineId` is `pf8_pfs_ast`.
- `archiveDiagnostics` includes `selectoblige.pfs`.
- `.ast` entries are reported under `visibleScriptPaths`.

## 2. Inspect Script Candidates

```powershell
python -m gal_translator archive-list "D:\private\otaku\game\galgame\selectoblige.exe" --scripts-only --limit 50
```

Expected result:

- `selectoblige.pfs` reports structured entries.
- Script paths look like `script\01_01プロローグ_01.ast`.

This is diagnostic only. Do not treat listed offsets as directly importable text.

## 3. Capture Japanese Runtime Text

Use Textractor or another local clipboard hook to collect Japanese lines into a text log.

Example log:

```text
おはよう、先輩。
……また会えた。
```

Before using a real game/log, run the synthetic local smoke:

```powershell
python -m gal_translator smoke-test --workspace "$env:LOCALAPPDATA\GalTranslatorSmoke"
python -m gal_translator smoke-test --workspace "$env:LOCALAPPDATA\GalTranslatorSmoke" --open-subtitle --subtitle-exit-after 8
```

This creates a disposable fake game, fake Textractor log, and fake Codex launcher, then verifies capture import, full batch translation, replay matching, subtitle dry-run, session report recovery, resume-session planning, source-log feedback translation, Python `live-session` report recovery, and retry-failed saved-report recovery. A passing result means the local Gal Translator pipeline is wired before any Textractor hook quality issues are involved. Add `--open-subtitle` for a local UI smoke that starts the translated subtitle window in a detached process and reports detached pid/stdout/stderr status. Add `--subtitle-exit-after <seconds>` when that UI smoke should close itself.

Import the log:

```powershell
python -m gal_translator record-clipboard ".\textractor-log.txt" --duration 60 --overwrite
python -m gal_translator inspect-log ".\textractor-log.txt" --source-name textractor --include-source
python -m gal_translator capture-log "D:\private\otaku\game\galgame\selectoblige.exe" ".\textractor-log.txt" --workspace "$env:LOCALAPPDATA\GalTranslator" --source-name textractor
```

`record-clipboard` records changed clipboard text into a UTF-8 log. Use it when Textractor is configured to copy hooked text to the clipboard but does not already write a file.
Read the `inspect-log.status` and `nextActions` before importing. `ready_to_import` means the log has Japanese lines; `ready_with_repeated_sources` means the log is usable but repeated source text will be stored as one translation entry; `no_japanese_text` usually means the hook or encoding needs repair. For repeated logs, `captureStats.uniqueImportedEntryCount` is the useful pending-translation estimate.

Or run the combined fallback workflow:

```powershell
python -m gal_translator workflow-fallback "D:\private\otaku\game\galgame\selectoblige.exe" ".\textractor-log.txt" --workspace "$env:LOCALAPPDATA\GalTranslator" --prepare-size 40
python -m gal_translator workflow-fallback "D:\private\otaku\game\galgame\selectoblige.exe" ".\textractor-log.txt" --workspace "$env:LOCALAPPDATA\GalTranslator" --prepare-size 40 --translate-all --translate-timeout 600 --replay-event-log ".\replay-events.jsonl"
python -m gal_translator play-session "D:\private\otaku\game\galgame\selectoblige.exe" ".\textractor-log.txt" --workspace "$env:LOCALAPPDATA\GalTranslator" --launch-game --record-clipboard --record-duration 60 --overwrite-log --replay-event-log ".\replay-events.jsonl" --subtitle-miss-log ".\misses.txt" --subtitle-preview-first-match --subtitle-source-log
python -m gal_translator live-session "D:\private\otaku\game\galgame\selectoblige.exe" ".\textractor-log.txt" --workspace "$env:LOCALAPPDATA\GalTranslator" --subtitle-detach --subtitle-miss-log ".\misses.txt" --subtitle-preview-first-match --subtitle-source-log
```

This runs environment checks, scan, capture import, and Codex batch preparation in one command.
With `--translate-all`, it also runs all pending Codex batches, applies successful results, and can write replay events from the same captured log.
Use `play-session` when you want the full local play path, ending in the subtitle window unless `--no-subtitle` or `--subtitle-dry-run` is passed. The capture log path is optional; if omitted, `play-session` uses `workspace/captures/<game>-live-capture.txt` and reports it as `sessionLogPath`. Clipboard recording in `play-session` defaults to a finite 60 seconds so the command can continue into translation and subtitle startup; use `--record-duration`, `--record-max-events`, or explicit `--record-until-interrupted` to change that. Add `--subtitle-preview-first-match` to initially show the first translated captured line in the subtitle window, or `--subtitle-preview-source "<source line>"` to choose the line explicitly. Add `--subtitle-source-log` when the active Textractor/log capture file should drive the subtitle window directly instead of the clipboard. Add `--session-report <path>` to persist the final session JSON for later recovery. Add `--subtitle-detach` when the subtitle window should open in a separate process and the command should return JSON immediately with `subtitleWindow.detachedPid`, quick `detachedRunning` / `detachedReturnCode` status, plus detached stdout/stderr log paths.
Read the top-level `sessionSummary.status` and `nextActions` first after a run; they collapse capture, no-source capture diagnostics, translation, replay, subtitle, detached subtitle early-exit, and miss-log state into the next command to run. When a subtitle window is configured, `subtitleWindow.command` reopens the same window settings. `sessionSummary.translateSessionLogCommand` and `sessionSummary.watchSessionLogCommand` can translate newly appended Textractor/session-log lines while `subtitle-window --source-log` follows that same file. When a miss log is configured, `sessionSummary.translateMissLogCommand` runs a one-shot miss translation and `sessionSummary.watchMissLogCommand` keeps translating new misses in the background with the same readiness guard used by `live-session.ps1`.
For repeated play sessions, add `--append` when the new log should extend the project. Without it, the captured state is replaced; `sessionSummary.replacedExistingState` and the top-level `nextActions` call this out when a prior state existed.
Use `live-session` when you want the same supervised workflow directly from Python instead of the PowerShell wrapper. It starts readiness-guarded background `translate-log --watch` processes for the miss log and, with `--subtitle-source-log`, the active Textractor/session log, then runs `play-session`, writes a live-session report, and returns a `resumeCommand` for recovery. Its watcher payloads include stdout/stderr tails and `statusSummary`, and top-level `nextActions` call out common wait states such as `log_missing`, `translation_not_ready`, or `translation_locked`.
Run `python -m gal_translator session-info <session-report.json>` when you need to recover from a saved play/live session report. It accepts reports from `play-session --session-report`, Python `live-session`, and `live-session.ps1`, then rechecks current project progress and returns concrete resume command arrays for pending translation, subtitle startup, miss-log translation, and stale-lock recovery.
Run `python -m gal_translator session-info <session-report.json>` first when diagnosing a saved run; it rechecks project progress, inspects the saved session log as `sessionLogInspection`, saved watcher processes when pids were reported, watcher stdout/stderr log tails, and compact `statusSummary` fields with the last watch status/reason/cycle counts. It also returns `resumeSessionCommand`, plus `appendSessionLogCommand` when a saved log can be appended to the reported project. When a subtitle window can be opened from a saved or default command, `resumeSessionCommand` includes `--open-subtitle`. Run the returned resume command, or run `python -m gal_translator resume-session <session-report.json>`, to execute the next recoverable step from that report. It can append the saved session log when the project is empty but the saved log has importable Japanese lines, continues pending `translate-all` work automatically, resets failed entries with `--retry-failed` before translating again, and `--open-subtitle` starts the saved subtitle window command once the project is ready. If an older report lacks a saved subtitle command, recovery builds a default subtitle-window command and follows the saved session log when available. Add `--start-miss-watcher` to restart the saved background miss-log translator at the same time; add `--start-session-log-watcher` to restart the saved background translator for appended Textractor/session-log lines used by `subtitle-window --source-log`; add `--dry-run` to preview the action. Saved `play-session` and `live-session.ps1` outputs include `resumeCommand` so you do not need to reconstruct this command by hand.
When `translate-all` fails, run `project-info <project-root>` before retrying. The `latestCodexBatch` section includes stdout/stderr tails and compact command/result JSON summaries for the last Codex batch, so command failures, timeouts, invalid JSON, and missing result files can be diagnosed without manually opening the batch directory first.
The PowerShell wrapper is `.\scripts\resume-session.ps1 -SessionReport <session-report.json> -OpenSubtitle -StartMissWatcher -StartSessionLogWatcher -RetryFailed`.

Use `subtitle-window --dry-run --preview-source "<captured source line>"` to check the exact display text for one line before opening the real window. Without `--dry-run`, the same option opens the subtitle window with that translated line already visible, then continues normal polling. Add `--source-log <path>` to poll appended Textractor/clipboard log lines instead of the OS clipboard; it uses the same cleaning and Japanese filtering as `inspect-log` / `capture-log`. Add `--save-config <json>` after tuning layout/style, then reuse it with `--config <json>`; `play-session` and `live-session` use the same file through `--subtitle-config` / `--subtitle-save-config`. Explicit window options override the config file. Add `--exit-after <seconds>` for a self-closing UI smoke.

For the closest one-command live setup, use the PowerShell supervisor:

```powershell
.\scripts\live-session.ps1 -GamePath "D:\private\otaku\game\galgame\selectoblige.exe" -LogPath ".\textractor-log.txt" -LaunchGame -RecordClipboard -RecordDuration 60 -OverwriteLog -ReplayEventLog ".\replay-events.jsonl" -SubtitleMissLog ".\misses.txt" -SubtitlePreviewFirstMatch -SubtitleSourceLog
.\scripts\live-session.ps1 -GamePath "D:\private\otaku\game\galgame\selectoblige.exe" -LogPath ".\textractor-log.txt" -SubtitleMissLog ".\misses.txt" -SubtitleDetach
```

It resolves the project root, starts `translate-miss-log.ps1 -Watch` in a hidden background process, then runs `translated-session.ps1`. With `-SubtitleSourceLog`, it also starts a hidden session-log watcher against the same capture log using the configured `-SourceName`, so appended Textractor lines can be translated while `subtitle-window --source-log` follows that file. When `-LogPath` is omitted, the resolved capture log is `Workspace\captures\<game>-live-capture.txt` and is returned as `sessionLogPath`. The final JSON is also saved to `sessionReportPath` under project `logs` by default; pass `-SessionReport` to choose the file. The output includes `resumeCommand` for continuing from that report later. The watchers wait for the primary project translation to become ready before processing log changes, so old miss/session logs do not race the main `translate-all` run. The final JSON includes watcher commands, stdout/stderr paths, and top-level `nextActions` derived from the nested `sessionSummary.status`, including direct detached subtitle stdout/stderr paths when a detached subtitle process exits immediately. `missWatcher.running` / `sessionLogWatcher.running` mean that watcher will remain alive after the launcher exits; `-SubtitleDetach` keeps them alive automatically only when the detached subtitle session starts successfully, and `-KeepMissWatcher` is available for other detached watcher cases.

For an already imported Artemis script project where full archive translation is paused, use the scoped source-log launcher instead:

```powershell
.\scripts\source-log-session.ps1 -ProjectRoot "$env:LOCALAPPDATA\GalTranslator\projects\<project-id>" -SourceLog ".\lunahook-source.txt" -SourceName lunahook -DryRun
.\scripts\source-log-session.ps1 -ProjectRoot "$env:LOCALAPPDATA\GalTranslator\projects\<project-id>" -SourceLog ".\lunahook-source.txt" -SourceName lunahook
.\scripts\source-log-session.ps1 -ProjectRoot "$env:LOCALAPPDATA\GalTranslator\projects\<project-id>" -SourceLog ".\lunahook-source.txt" -SourceName lunahook -StartClipboardBridge
```

This starts `translate-log --watch --only-new-log-entries` and `subtitle-window --source-log` against the same source log. It intentionally omits `--watch-require-ready`, because a partially translated imported project is expected to have many unrelated pending entries. The watcher therefore translates only source-log-referenced entries, including imported pending script lines that already exist in `translation-state.json`.

Use `-StartClipboardBridge` when LunaHook/Textractor copies captured text to the clipboard instead of appending a file. The launcher starts `record-clipboard` as a background bridge so changed clipboard text lands in the same source log that the watcher and subtitle window are already following.

When more lines are captured later, append without losing existing translations:

```powershell
python -m gal_translator capture-log "D:\private\otaku\game\galgame\selectoblige.exe" ".\textractor-log.txt" --workspace "$env:LOCALAPPDATA\GalTranslator" --source-name textractor --append
```

For repeated imports after the project already exists, avoid rescanning large archives:

```powershell
python -m gal_translator append-log "$env:LOCALAPPDATA\GalTranslator\projects\<project-id>" ".\textractor-log.txt" --source-name textractor
```

Expected result:

- `storyEntryCount` increases only for new captured source text; repeated Textractor lines are not added as duplicate pending translations even when the line id changes in a growing log.
- Already translated entries remain translated.
- `captureStats` reports raw lines, candidate lines, skipped duplicate lines, skipped non-Japanese lines, and imported entries. Use this to diagnose noisy Textractor hooks.

## 4. Prepare Or Run Codex Batch Translation

Reviewable preparation:

```powershell
python -m gal_translator prepare-codex "$env:LOCALAPPDATA\GalTranslator\projects\<project-id>" --size 40
```

Dry-run execution preparation:

```powershell
python -m gal_translator run-codex "$env:LOCALAPPDATA\GalTranslator\projects\<project-id>" --size 40 --dry-run
```

Actual execution:

```powershell
python -m gal_translator run-codex "$env:LOCALAPPDATA\GalTranslator\projects\<project-id>" --size 40 --apply --timeout 600
```

Full pending translation:

```powershell
python -m gal_translator translate-all "$env:LOCALAPPDATA\GalTranslator\projects\<project-id>" --size 40 --dry-run
python -m gal_translator translate-all "$env:LOCALAPPDATA\GalTranslator\projects\<project-id>" --size 40 --timeout 600
python -m gal_translator translate-all "$env:LOCALAPPDATA\GalTranslator\projects\<project-id>" --size 40 --timeout 600 --retry-failed
```

Expected result:

- Prompt, schema, command, stdout, and stderr files are written under project `logs/`.
- With `--apply`, successful Codex output updates `translation-state.json`.
- `translate-all` repeats this until all pending entries are translated or a batch fails; every batch keeps its own log directory.
- `translate-all --retry-failed` resets failed entries to pending inside the same translation lock before running batches.
- Translation-state writers use `logs/translation.lock`, so `translate-all`, `translate-log`, and `apply-result` do not run against the same project concurrently. `translate-log --watch` waits when the lock is active. If a run is interrupted, inspect `project-info.translationLock`; then run `clear-lock` only after confirming no Gal Translator translation process is still active.

## 5. Check Progress

```powershell
python -m gal_translator progress "$env:LOCALAPPDATA\GalTranslator\projects\<project-id>"
```

Expected result:

- `pending` decreases as result JSON is applied.
- `status` becomes `ready` when all entries are translated.

## 6. Runtime Lookup

One-off lookup:

```powershell
python -m gal_translator lookup "$env:LOCALAPPDATA\GalTranslator\projects\<project-id>" "おはよう、先輩。"
```

Replay a captured log without using the OS clipboard:

```powershell
python -m gal_translator replay-log "$env:LOCALAPPDATA\GalTranslator\projects\<project-id>" ".\textractor-log.txt" --source-name textractor
python -m gal_translator replay-log "$env:LOCALAPPDATA\GalTranslator\projects\<project-id>" ".\textractor-log.txt" --source-name textractor --event-log ".\replay-events.jsonl"
python -m gal_translator translate-log "$env:LOCALAPPDATA\GalTranslator\projects\<project-id>" ".\misses.txt" --source-name misses --only-new-log-entries --replay-event-log ".\miss-replay.jsonl"
python -m gal_translator translate-log "$env:LOCALAPPDATA\GalTranslator\projects\<project-id>" ".\misses.txt" --source-name misses --only-new-log-entries --watch
python -m gal_translator project-info "$env:LOCALAPPDATA\GalTranslator\projects\<project-id>"
python -m gal_translator clear-lock "$env:LOCALAPPDATA\GalTranslator\projects\<project-id>"
.\scripts\translate-miss-log.ps1 -ProjectRoot "$env:LOCALAPPDATA\GalTranslator\projects\<project-id>" -LogPath ".\misses.txt" -ReplayEventLog ".\miss-replay.jsonl"
.\scripts\translate-miss-log.ps1 -ProjectRoot "$env:LOCALAPPDATA\GalTranslator\projects\<project-id>" -LogPath ".\misses.txt" -Watch
```

Expected result:

- `matched` shows how many captured lines already have translations.
- Runtime event `text` fields contain translated Chinese only.
- Source text is omitted unless `--include-source` is passed for diagnostics.
- `--event-log` writes replayed runtime events as JSONL for release notes or debugging.
- `translate-log --only-new-log-entries` appends or inspects a captured or miss log on an existing project, translates only log-referenced entries, and can replay that same log. For pre-extracted script projects, this includes existing pending entries whose source text appears in the log.
- `translate-log.sessionSummary` and `translate-log.nextActions` report whether the new misses are translated and whether the session can return to `play-session` / `subtitle-window`.
- `translate-log --watch` keeps the miss-log feedback loop running in a background terminal and emits one JSONL event per poll cycle; use `--watch-max-cycles` for bounded smoke tests. It waits while the project translation state is still being created, which lets `live-session.ps1` start the watcher before capture import finishes. Add `--watch-require-ready` when the watcher must not process miss logs until the existing project has no pending or failed entries.

Clipboard JSON events:

```powershell
python -m gal_translator watch-clipboard "$env:LOCALAPPDATA\GalTranslator\projects\<project-id>"
```

External subtitle window:

```powershell
python -m gal_translator subtitle-window "$env:LOCALAPPDATA\GalTranslator\projects\<project-id>"
python -m gal_translator subtitle-window "$env:LOCALAPPDATA\GalTranslator\projects\<project-id>" --dry-run --x 120 --y 760 --clear-after 4
python -m gal_translator subtitle-window "$env:LOCALAPPDATA\GalTranslator\projects\<project-id>" --dry-run --save-config ".\subtitle-window.json"
python -m gal_translator subtitle-window "$env:LOCALAPPDATA\GalTranslator\projects\<project-id>" --dry-run --config ".\subtitle-window.json"
python -m gal_translator subtitle-window "$env:LOCALAPPDATA\GalTranslator\projects\<project-id>" --source-log ".\textractor-log.txt" --source-log-name textractor
python -m gal_translator subtitle-window "$env:LOCALAPPDATA\GalTranslator\projects\<project-id>" --x 120 --y 760 --width 1200 --height 120 --font-size 30 --opacity 0.82 --clear-after 4 --event-log ".\runtime-events.jsonl" --miss-log ".\misses.txt"
```

Expected result:

- Matched lines display Simplified Chinese only.
- Unmatched lines do not show Japanese by default.
- Runtime events are logged to `logs/runtime-events.jsonl` unless disabled.
- Runtime event logs omit raw source text unless `--include-source` is passed.
- `--miss-log` writes only unmatched runtime source text to a plain text log for later `append-log` / `translate-all`.
- Runtime event payloads include `missLogged`, which tells you whether an unmatched line was newly written to the configured miss log without exposing raw source text.
- `watch-clipboard` and `subtitle-window` reload `translation-state.json` by default, so a `translate-log` miss round can become visible without restarting the runtime display. `subtitle-window` rechecks the last unmatched source during idle polls, so a newly translated miss can appear even if that exact line is not emitted again. Their runtime event output omits source text unless `--include-source` is passed. Use `--no-reload` only when diagnosing a fixed snapshot.
- `subtitle-window --source-log` tails only newly imported Japanese lines by default; add `--source-log-from-start` for bounded replay/dry-run checks.
- `subtitle-window --save-config` writes the resolved window config JSON, and `--config` reloads it for later play sessions.
- `--clear-after` is optional. Use it when you want old matched subtitles to disappear after a few seconds without new clipboard text.

## Current Limitation

`PFS/pf8` extraction is intentionally not implemented for encrypted/non-plaintext payloads. If decoded `.ast` files or an acceptable verified extraction workflow are provided later, add an adapter under the engine-adapter phase.

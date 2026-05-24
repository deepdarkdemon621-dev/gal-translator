# Release Checklist

Use this checklist before handing the tool to a normal local user.

## Environment

- Run `python -m gal_translator doctor`.
- Confirm `codexOnPath` is true if Codex batch execution will be used.
- Confirm `tkinterImportable` is true if the subtitle window will be used.
- Confirm the workspace path is writable.

## Tests

```powershell
python -m unittest discover -v
```

Expected result: all tests pass.

## Real Sample Smoke

Scan:

```powershell
python -m gal_translator scan "D:\private\otaku\game\galgame\selectoblige.exe"
```

Expected:

- top candidate is `pf8_pfs_ast`;
- `nextActions` recommends `archive-list` and `capture-log`.

Archive list:

```powershell
python -m gal_translator archive-list "D:\private\otaku\game\galgame\selectoblige.exe" --scripts-only --limit 5
```

Expected:

- entries include `script\... .ast` paths.

Local synthetic smoke:

```powershell
python -m gal_translator smoke-test --workspace "$env:LOCALAPPDATA\GalTranslatorSmoke"
python -m gal_translator smoke-test --workspace "$env:LOCALAPPDATA\GalTranslatorSmoke" --open-subtitle --subtitle-exit-after 8
```

Expected:

- status is `passed`;
- every `checks` value is true;
- `inspectLog.captureStats.importedEntryCount` is greater than zero;
- `playSession.translateAll.status` is `ready`;
- `playSession.replay.matched` is greater than zero;
- `sessionInfo.reportType` is `play-session`;
- `resumeSession.status` is `subtitle_planned`.
- with `--open-subtitle`, `checks.subtitleWindowStarted` is true and `playSession.subtitleWindow.detachedRunning` is true.
- with `--subtitle-exit-after`, the subtitle command includes `--exit-after` and the window closes itself.

Fallback import:

```powershell
python -m gal_translator record-clipboard ".\textractor-log.txt" --duration 30 --overwrite
python -m gal_translator inspect-log ".\textractor-log.txt" --source-name textractor
python -m gal_translator capture-log "D:\private\otaku\game\galgame\selectoblige.exe" ".\textractor-log.txt" --workspace "$env:LOCALAPPDATA\GalTranslator" --source-name textractor
```

Expected:

- inspect-log reports useful `captureStats`, a `ready_to_import` or `ready_with_repeated_sources` status, and actionable `nextActions`;
- `translation-state.json` is created;
- `project-info` recommends translation when entries are pending.
- `project-info.diagnostics` is empty for a healthy project.
- `captureStats.importedEntryCount` is greater than zero for a useful Textractor log.
- `captureStats.uniqueImportedEntryCount` is greater than zero and is treated as the expected pending translation count when the log repeats source text.
- repeated captured source text creates only one project translation entry, even if the later occurrence has a different log line id.

Batch translation:

```powershell
python -m gal_translator translate-all "$env:LOCALAPPDATA\GalTranslator\projects\<project-id>" --size 40 --dry-run
python -m gal_translator translate-all "$env:LOCALAPPDATA\GalTranslator\projects\<project-id>" --size 40 --timeout 600
python -m gal_translator translate-all "$env:LOCALAPPDATA\GalTranslator\projects\<project-id>" --size 40 --timeout 600 --retry-failed
python -m gal_translator play-session "D:\private\otaku\game\galgame\selectoblige.exe" ".\textractor-log.txt" --workspace "$env:LOCALAPPDATA\GalTranslator" --subtitle-dry-run --replay-event-log ".\replay-events.jsonl" --subtitle-miss-log ".\misses.txt" --subtitle-preview-first-match --subtitle-source-log
python -m gal_translator play-session "D:\private\otaku\game\galgame\selectoblige.exe" ".\textractor-log.txt" --workspace "$env:LOCALAPPDATA\GalTranslator" --subtitle-detach --subtitle-miss-log ".\misses.txt"
python -m gal_translator live-session "D:\private\otaku\game\galgame\selectoblige.exe" ".\textractor-log.txt" --workspace "$env:LOCALAPPDATA\GalTranslator" --subtitle-detach --subtitle-miss-log ".\misses.txt" --subtitle-source-log --subtitle-preview-first-match
python -m gal_translator translate-log "$env:LOCALAPPDATA\GalTranslator\projects\<project-id>" ".\misses.txt" --only-new-log-entries --replay-event-log ".\miss-replay.jsonl"
python -m gal_translator translate-log "$env:LOCALAPPDATA\GalTranslator\projects\<project-id>" ".\misses.txt" --only-new-log-entries --dry-run --watch --watch-max-cycles 1
```

Expected:

- dry-run reports the planned batch count and writes the first batch files;
- real execution applies each successful Codex result;
- final progress is `ready`, or failed entries are visible for `retry-failed`.
- `translate-all --retry-failed` resets failed items and can return the project to `ready` in the same command.
- `translate-all` and `apply-result` report `translation_locked` if another translation writer is already active.
- failed `translate-all` batches include stdout/stderr tail payloads in `batches[]`, and `project-info.latestCodexBatch` exposes stdout/stderr tails plus command/result JSON summaries for the latest batch.
- play-session returns capture, translate, replay, subtitle dry-run, and project-info payloads.
- play-session with `--subtitle-detach` starts subtitle-window in a separate process and returns `subtitleWindow.detachedPid`, quick `detachedRunning` / `detachedReturnCode` status, plus detached stdout/stderr log paths without waiting for the window to close.
- play-session reports `sessionSummary.status=subtitle_exited` and points nextActions at detached stdout/stderr logs when a detached subtitle process exits immediately.
- play-session top-level `sessionSummary.status` and `nextActions` identify whether to open subtitles, repair translation, or feed misses through translate-log.
- play-session with `--session-report` writes the same final JSON payload to a recovery file and returns `sessionReportPath`.
- saved play-session and live-session outputs return `resumeCommand` for continuing translation, subtitle startup, and miss-log watcher restore from the saved report.
- `play-session --session-report` writes a `resumeCommand` that matches `session-info.commands.resumeSessionCommand` for the saved report.
- synthetic `smoke-test` reports `checks.savedResumeCommandExecutable=true` after running the saved `playSession.resumeCommand --dry-run`.
- synthetic `smoke-test` reports `checks.savedResumeCommandMatchesSessionInfo=true` and `checks.savedResumeCommandPlansWatchers=true`.
- synthetic `smoke-test` reports `checks.sourceLogFeedbackTranslated=true` after appending a new source-log line, processing it with `translate-log --watch`, and matching it through `lookup`.
- synthetic `smoke-test` reports `checks.liveSessionCompleted=true`, `checks.liveSessionReportRecoverable=true`, and `checks.liveSessionResumeExecutable=true` after running a bounded Python `live-session` dry-run, inspecting the saved report, and executing the returned resume command with `--dry-run`.
- synthetic `smoke-test` reports `checks.retryFailedResumeRecovered=true` after creating a failed-entry saved report and proving `resume-session --retry-failed` resets, translates, and returns to subtitle-ready recovery.
- self-closing UI smoke reports `checks.resumeSubtitleWindowStarted=true` after running `resume-session <report> --open-subtitle`.
- self-closing UI smoke reports `checks.subtitleWindowAutoClosed=true`, `checks.resumeSubtitleWindowAutoClosed=true`, and `subtitleAutoClose.status=passed`, proving both detached subtitle processes exited.
- self-closing UI smoke reports `checks.sourceLogSubtitleWindowDisplayed=true`, proving a real `subtitle-window --source-log --source-log-from-start` run wrote a visible exact-match event for the newly translated source-log line.
- self-closing UI smoke reports `checks.sourceLogLiveRefreshDisplayed=true`, proving a live `subtitle-window --source-log` run can see a newly appended line as unmatched and then refresh it to a visible exact match after `translate-log --watch` updates translations.
- `live-session.ps1` smoke executes the returned PowerShell `resumeCommand -DryRun` and reaches the next planned recovery action.
- session-info reads saved play-session and live-session reports, rechecks current project progress, and returns resume command arrays including `resumeSessionCommand` and `appendSessionLogCommand` for saved session logs.
- session-info includes `--open-subtitle` in `resumeSessionCommand` when a saved or default subtitle-window command is available.
- the returned `session-info.commands.resumeSessionCommand` can be rerun with `--dry-run` and reaches `status=subtitle_planned` when subtitle recovery is available.
- older saved reports without `watchMissLogCommand` get synthesized `translateMissLogCommand` / `watchMissLogCommand` from `missLogPath`, and returned resume commands can dry-run the synthesized miss-log watcher.
- older saved reports without `watchSessionLogCommand` get synthesized `translateSessionLogCommand` / `watchSessionLogCommand` from `sessionLogPath`, and returned resume commands can dry-run the synthesized session-log watcher.
- session-info returns `sessionLogInspection` for the saved capture/session log, including captureStats and no-source diagnostics.
- session-info rechecks saved live-session miss/session-log watcher pids when present and reports watcher stdout/stderr tail diagnostics plus compact `statusSummary` fields.
- resume-session reads saved reports and can execute the next recoverable step: append a saved session log into an empty project when `sessionLogInspection.status=has_source`, pending translate-all, failed-entry reset plus translation with `--retry-failed`, saved or default subtitle-window startup with `--open-subtitle`, saved miss-log watcher startup with `--start-miss-watcher`, and saved session-log watcher startup with `--start-session-log-watcher`.
- play-session reports `sessionSummary.status=no_source_text` and does not prepare/start a subtitle window when the final project state has no captured Japanese source entries.
- play-session returns `subtitleWindow.command` and, when a miss log is configured, `sessionSummary.translateMissLogCommand` plus a readiness-guarded `sessionSummary.watchMissLogCommand`.
- play-session returns `sessionSummary.translateSessionLogCommand` and readiness-guarded `sessionSummary.watchSessionLogCommand` so source-log subtitle sessions can translate newly appended Textractor/session-log lines.
- live-session with `-SubtitleSourceLog` starts a readiness-guarded `sessionLogWatcher` and reports its command plus stdout/stderr paths.
- Python `live-session` starts readiness-guarded miss/session-log watchers, runs `play-session`, writes a report, returns watcher command/log payloads with stdout/stderr tails and `statusSummary`, surfaces watcher wait reasons in top-level `nextActions`, returns a `resumeCommand` that can be run with `--dry-run`, and `session-info` recovers the saved watcher commands from that report.
- play-session `--subtitle-preview-first-match` returns `subtitleWindow.preview` and writes `--preview-source` into the reusable subtitle command.
- play-session `--subtitle-source-log` returns `subtitleWindow.input.mode=source_log` and writes `--source-log` into the reusable subtitle command.
- repeated play-session without `--append` reports `sessionSummary.replacedExistingState` and a top-level next action warning.
- play-session reports the configured subtitle miss log when `--subtitle-miss-log` is passed.
- subtitle-window `--dry-run --preview-source` returns the translated preview text for a known source line.
- subtitle-window `--dry-run --source-log` reports `input.mode=source_log`, `sourceLogPath`, and whether the source log exists.
- subtitle-window `--dry-run --save-config <json>` writes a reusable layout/style JSON; `--config <json>` reloads it, and `play-session` / `live-session` use the same file through `--subtitle-config` / `--subtitle-save-config` while allowing explicit CLI options to override saved values.
- subtitle-window `--exit-after` is reported as `config.exitAfterMs` in dry-run payloads and is passed by PowerShell wrappers.
- scoped translate-log can consume the miss log and return log-referenced entries to `ready` without translating unrelated global pending entries.
- translate-log top-level `sessionSummary.status` and `nextActions` identify whether to resume play-session or continue collecting unmatched lines.
- translate-log watch mode emits JSONL cycle payloads and can be bounded with `--watch-max-cycles`.
- translate-log watch mode reports idle `translation_state_missing` instead of exiting when live-session starts it before capture import creates the state file.
- translate-log watch mode reports idle `translation_locked` instead of racing an active translation writer.
- translate-log watch mode with `--watch-require-ready` reports idle `translation_not_ready` until the primary project has no pending or failed entries; live-session uses this to avoid racing its main translate-all run.
- project-info reports `translationLock`, and `clear-lock` removes stale locks while refusing active process ids unless `--force` is passed.

## Runtime Smoke

After applying at least one translation:

```powershell
python -m gal_translator lookup "$env:LOCALAPPDATA\GalTranslator\projects\<project-id>" "おはよう、先輩。"
```

Expected:

- translated Chinese is returned;
- `showSource` is false.
- watch-clipboard and subtitle-window runtime events omit raw source text unless `--include-source` is passed.
- watch-clipboard and subtitle-window runtime events include `missLogged` so miss-log feedback can be diagnosed without source-inclusive logs.

Replay:

```powershell
python -m gal_translator replay-log "$env:LOCALAPPDATA\GalTranslator\projects\<project-id>" ".\textractor-log.txt" --source-name textractor --event-log ".\replay-events.jsonl"
```

Expected:

- replay reports match coverage;
- replay omits source text by default.
- replay writes JSONL events when `--event-log` is provided.
- subtitle-window dry-run reports the resolved runtime event log path.
- subtitle-window and watch-clipboard reload translation-state by default; `--no-reload` is available for fixed-snapshot diagnostics.
- subtitle-window rechecks the last unmatched runtime source after translation-state reload, so miss-log feedback can show a newly translated line without waiting for the source to repeat.

## Launcher Scripts

```powershell
.\scripts\gal-translator.ps1 doctor
.\scripts\fallback-workflow.ps1 -GamePath "D:\private\otaku\game\galgame\selectoblige.exe" -LogPath ".\textractor-log.txt"
.\scripts\fallback-workflow.ps1 -GamePath "D:\private\otaku\game\galgame\selectoblige.exe" -LogPath ".\textractor-log.txt" -TranslateAll -ReplayEventLog ".\replay-events.jsonl"
.\scripts\translated-session.ps1 -GamePath "D:\private\otaku\game\galgame\selectoblige.exe" -LogPath ".\textractor-log.txt" -ReplayEventLog ".\replay-events.jsonl" -SubtitleMissLog ".\misses.txt" -DryRun
.\scripts\translated-session.ps1 -GamePath "D:\private\otaku\game\galgame\selectoblige.exe" -LogPath ".\textractor-log.txt" -RecordClipboard -RecordDuration 60 -OverwriteLog -ReplayEventLog ".\replay-events.jsonl" -SubtitleMissLog ".\misses.txt" -DryRun
.\scripts\translated-session.ps1 -GamePath "D:\private\otaku\game\galgame\selectoblige.exe" -LogPath ".\textractor-log.txt" -LaunchGame -RecordClipboard -RecordDuration 60 -OverwriteLog -ReplayEventLog ".\replay-events.jsonl" -SubtitleMissLog ".\misses.txt" -DryRun
.\scripts\live-session.ps1 -GamePath "D:\private\otaku\game\galgame\selectoblige.exe" -LogPath ".\textractor-log.txt" -SubtitleMissLog ".\misses.txt" -DryRun -NoSubtitle -WatchMaxCycles 1
.\scripts\source-log-session.ps1 -ProjectRoot "$env:LOCALAPPDATA\GalTranslator\projects\<project-id>" -SourceLog ".\lunahook-source.txt" -SourceName lunahook -DryRun
.\scripts\source-log-session.ps1 -ProjectRoot "$env:LOCALAPPDATA\GalTranslator\projects\<project-id>" -SourceLog ".\lunahook-source.txt" -SourceName lunahook -StartClipboardBridge -ClipboardDuration 30 -DryRun
.\scripts\resume-session.ps1 -SessionReport ".\live-session-report.json" -DryRun -OpenSubtitle -StartMissWatcher -StartSessionLogWatcher -RetryFailed
python -m gal_translator project-info "$env:LOCALAPPDATA\GalTranslator\projects\<project-id>"
python -m gal_translator clear-lock "$env:LOCALAPPDATA\GalTranslator\projects\<project-id>"
python -m gal_translator subtitle-window "$env:LOCALAPPDATA\GalTranslator\projects\<project-id>" --dry-run --x 120 --y 760 --clear-after 4 --exit-after 8
python -m gal_translator subtitle-window "$env:LOCALAPPDATA\GalTranslator\projects\<project-id>" --dry-run --save-config ".\subtitle-window.json"
python -m gal_translator subtitle-window "$env:LOCALAPPDATA\GalTranslator\projects\<project-id>" --dry-run --config ".\subtitle-window.json"
python -m gal_translator subtitle-window "$env:LOCALAPPDATA\GalTranslator\projects\<project-id>" --dry-run --source-log ".\textractor-log.txt" --source-log-name textractor --source-log-from-start
.\scripts\translate-miss-log.ps1 -ProjectRoot "$env:LOCALAPPDATA\GalTranslator\projects\<project-id>" -LogPath ".\misses.txt" -ReplayEventLog ".\miss-replay.jsonl" -DryRun
.\scripts\translate-miss-log.ps1 -ProjectRoot "$env:LOCALAPPDATA\GalTranslator\projects\<project-id>" -LogPath ".\misses.txt" -Watch -WatchMaxCycles 1 -DryRun
.\scripts\start-subtitle-window.ps1 -ProjectRoot "$env:LOCALAPPDATA\GalTranslator\projects\<project-id>"
.\scripts\start-subtitle-window.ps1 -ProjectRoot "$env:LOCALAPPDATA\GalTranslator\projects\<project-id>" -X 120 -Y 760 -ClearAfter 4 -ExitAfter 8 -MissLog ".\misses.txt"
.\scripts\start-subtitle-window.ps1 -ProjectRoot "$env:LOCALAPPDATA\GalTranslator\projects\<project-id>" -SourceLog ".\textractor-log.txt" -SourceLogName textractor
.\scripts\start-subtitle-window.ps1 -ProjectRoot "$env:LOCALAPPDATA\GalTranslator\projects\<project-id>" -Config ".\subtitle-window.json"
.\scripts\start-subtitle-window.ps1 -ProjectRoot "$env:LOCALAPPDATA\GalTranslator\projects\<project-id>" -NoReload
```

Expected:

- scripts launch from the repository root;
- no generated files are written into the game directory.
- subtitle window options position the window and can auto-clear stale matched text.
- `translated-session.ps1 -DryRun` returns workflow JSON and subtitle dry-run config without opening a window.
- `play-session`, `translated-session.ps1`, and `live-session.ps1` can omit the capture log path and report the default `sessionLogPath`.
- `play-session --record-clipboard` and script `-RecordClipboard` default to finite 60-second recording; explicit `--record-until-interrupted` / `-RecordUntilInterrupted` is required for an indefinite recording phase.
- `translated-session.ps1 -SessionReport` passes through to `play-session --session-report`, and `live-session.ps1` writes a top-level `sessionReportPath` by default.
- `live-session.ps1` returns `resumeCommand` pointing at `resume-session.ps1` and the saved `sessionReportPath`, including `-StartSessionLogWatcher` when source-log subtitle mode is active.
- `translated-session.ps1 -LaunchGame` starts the game exe from its own directory before clipboard recording.
- `live-session.ps1 -DryRun -NoSubtitle -WatchMaxCycles 1` starts the hidden miss watcher, runs the translated session, returns watcher command/log paths, reports whether the watcher remains running after exit, and gives dry-run-specific top-level nextActions.
- live-session top-level `nextActions` surface detached subtitle early-exit stderr/stdout log paths instead of hiding them inside the nested session payload.
- `live-session.ps1 -SubtitleDetach` keeps the miss watcher alive automatically only when the detached subtitle session starts successfully, so a failed window launch does not leave an unnecessary hidden watcher.
- `resume-session.ps1` wraps report recovery and passes subtitle, miss-watcher, session-log watcher, and retry-failed restore options through to the CLI.
- `translate-miss-log.ps1` wraps the miss-log feedback loop and can dry-run before calling Codex.
- `translate-miss-log.ps1 -Watch` passes background miss-log polling through to `translate-log --watch`.
- `start-subtitle-window.ps1 -NoReload` passes the fixed-snapshot diagnostic mode through to the CLI.
- `start-subtitle-window.ps1 -SourceLog`, `translated-session.ps1 -SubtitleSourceLog`, and `live-session.ps1 -SubtitleSourceLog` pass log-driven subtitle input through to the CLI.

## Safety Gate

Do not ship an adapter that decrypts or bypasses protected packages. For encrypted/non-plaintext package payloads, ship diagnostics plus the Textractor/clipboard fallback workflow.

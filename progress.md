# Progress

## 2026-05-24 Stale LunaHook Target Diagnostic

- Rechecked the paused real session with `source-log-status` after the previous commit.
- Current real process state showed a recovery edge case: the source-log watcher and LunaHook bridge processes are still active, but `selectoblige.exe` and the saved subtitle-window process are no longer active.
- Tightened `source-log-status` for this condition:
  - `lunaHookBridge` now reports `gameProcessActive` for the saved `gamePid`.
  - `closedLoopProof` now reports `status=hook_game_inactive` when the bridge process is alive but its target game pid is gone.
  - `closedLoopProof` includes `lunaHookGameProcessActive`.
  - `nextActions` now tells the operator to start the game and restart the source-log session with `-StartLunaHookBridge` instead of implying the old bridge can still capture new text.
- Real status after the change:
  - `status=watcher_active`
  - `closedLoopProof.status=hook_game_inactive`
  - `lunaHookBridge.currentProcessActive=true`
  - `lunaHookBridge.gameProcessActive=false`
  - Next action explicitly says `Game process is not running (selectoblige.exe)` and to restart the game/session.

Verification:

```powershell
python -m unittest tests.test_cli.CliTests.test_source_log_status_reports_paused_scoped_loop tests.test_cli.CliTests.test_source_log_status_reports_stale_lunahook_game_pid -v
```

Result: 2 tests passed.

Full regression verification:

```powershell
python -m unittest discover -v
```

Result: 145 tests passed.

## 2026-05-24 Pause Checkpoint And Commit Handoff

- User requested pausing the current task after the scoped LunaHook/source-log closed loop reached a usable state.
- Full archive translation remains intentionally paused for token control: `32978` total, `6950` translated, `26028` pending, `0` failed, `21.07%`.
- Do not resume global `translate-all` unless explicitly choosing to translate the full remaining archive; continue the MVP route with Hook/Textractor/source-log lines translated through scoped `translate-log --only-new-log-entries`.
- Current active real session:
  - Project: `C:\Users\deepd\AppData\Local\GalTranslator\real-session-selectoblige\artemis-script-project\projects\pfs-rs-extract-selectoblige-pfs-v0.2.5-b56875e0b374`
  - Source log: `C:\Users\deepd\AppData\Local\GalTranslator\real-session-selectoblige\lunahook-source.txt`
  - Session report: `logs\source-log-session-20260524-225357-report.json`
  - Game pid `26324`, source-log watcher pid `3292`, subtitle-window pid `14860`, LunaHook bridge pid `37836`, clipboard bridge disabled.
- Latest closed-loop proof after the stronger UI/control filter:
  - Hook/source text: `窶補輔≠縺ゅ∝､ｱ謨励＠縺溘Ａ`
  - Imported Artemis id: `script/01_01繝励Ο繝ｭ繝ｼ繧ｰ_01.ast:143`
  - Subtitle text: `窶披泌賦蝠奇ｼ梧裾遐ｸ莠・Ａ`
  - `closedLoopProof.status=closed_loop_displayed`, `subtitleMatchType=exact`, `subtitleVisible=true`, `subtitleMissLogged=false`.
- LunaHook was used only as an external capture bridge from the local LunaTranslator installation, not as the project's translation engine and not for in-game text replacement.
- Verification: `python -m unittest discover -v` -> 144 tests passed.

## 2026-05-24 Paused Full Archive Source-Log Status

- Confirmed the persistent `selectoblige` Artemis project remains intentionally partial: `32978` total entries, `6950` translated, `26028` pending, `0` failed, `21.07%`.
- Continued the cost-control route: do not run global `translate-all` for the remaining archive unless explicitly choosing to spend tokens on all pending entries.
- Added `python -m gal_translator source-log-status <project_root> <source_log>` for the paused full-archive play loop.
- The new status command reports project progress, source-log importability, saved source-log watcher status, subtitle-window status, optional game process checks, and Hook/Textractor process checks.
- It always frames this mode as `paused_full_archive_scoped_source_log` and returns next actions for scoped `translate-log --only-new-log-entries`, not global archive translation.
- Real status check against the active session returned `status=watching_source_log`: game `selectoblige.exe` pid `4492`, LunaTranslator pid `13540`, source-log watcher pid `11584`, subtitle-window pid `43600`.
- Real source log remains `C:\Users\deepd\AppData\Local\GalTranslator\real-session-selectoblige\lunahook-source.txt`.
- Real source-log session report remains `C:\Users\deepd\AppData\Local\GalTranslator\real-session-selectoblige\artemis-script-project\projects\pfs-rs-extract-selectoblige-pfs-v0.2.5-b56875e0b374\logs\source-log-session-20260524-210406-report.json`.
- The watcher is currently idle on `log_unchanged`, with last processed event preserved from cycle `349`: `lastProcessedSessionStatus=translation_ready`, `lastProcessedScopedTranslatedCount=1`, and `lastProcessedLogEntryIds=["script/01_01プロローグ_01.ast:16"]`.
- Launched LunaTranslator GUI from `C:\Game\LunaTranslator_x64_win10_v10.12.3\LunaTranslator_x64_win10\LunaTranslator.exe`; the remaining manual/external step is ensuring LunaHook appends actual new runtime story text to the prepared source-log path.
- Added optional source-log clipboard bridge support to `scripts/source-log-session.ps1`:
  - `-StartClipboardBridge` starts `python -m gal_translator record-clipboard <source-log>` in the background.
  - The bridge appends changed clipboard text into the same source log followed by the scoped watcher and subtitle window.
  - The session report now includes `clipboardBridge` command, pid, stdout, and stderr paths; `session-info` and `source-log-status` surface the bridge when present.
  - This is a fallback for LunaHook/Textractor setups that can copy captured text to the clipboard but do not append a file.
- Verified the bridge with a temporary run:
  - Set clipboard to `これは橋接テストです。`.
  - Ran `source-log-session.ps1 -NoWatcher -NoSubtitle -StartClipboardBridge -ClipboardDuration 1` against a temp source log.
  - The bridge wrote that line into the temp source log and reported `capturedCount=1`.
  - Restored the previous clipboard content afterward.

- Restarted the real source-log play loop as a coherent new session with clipboard bridge enabled:
  - New report: `logs\source-log-session-20260524-214004-report.json`.
  - Game `selectoblige.exe` pid: 31832.
  - LunaTranslator pid: 23440.
  - Source-log watcher pid: 33176.
  - Subtitle-window pid: 36956.
  - Clipboard bridge pid: 20228.
  - `source-log-status` reports `status=watching_source_log`, watcher/subtitle/bridge active, and full archive translation still paused at 6,950 translated / 26,028 pending.

- Added direct LunaHook bridge support to the desktop Play Output source-log session template:
  - `DesktopShellConfig` now stores LunaHook bridge settings.
  - `python -m gal_translator desktop --dry-run --source-name lunahook --start-luna-hook-bridge --luna-hook-game-process selectoblige.exe` emits a `sourceLogSession` command with `-StartLunaHookBridge`, `-LunaHookGameProcess selectoblige.exe`, the two verified Artemis hook codes, and scoped defaults `-BatchSize 1 -MaxBatches 1`.
  - Default desktop behavior remains conservative: bridge disabled unless requested, clipboard bridge not started, and no Play Output command invokes global `translate-all`.
- Fresh real status check after this desktop wiring:
  - `status=watching_source_log`, `mode=paused_full_archive_scoped_source_log`.
  - Progress remains `32978` total, `6950` translated, `26028` pending, `0` failed, `21.07%`.
  - Game pid `31832`, watcher pid `43408`, subtitle-window pid `24088`, LunaHook bridge pid `18108`.
  - Clipboard bridge disabled.

### Test Result

```powershell
python -m unittest discover -v
```

Result: 137 tests passed.

Additional focused verification:

```powershell
python -m unittest tests.test_desktop -v
python -m unittest tests.test_cli.CliTests.test_source_log_session_script_plans_scoped_watcher_and_subtitle_window tests.test_cli.CliTests.test_session_info_reads_source_log_session_report_without_recommending_global_translation tests.test_cli.CliTests.test_source_log_status_reports_paused_scoped_loop -v
```

Result: desktop tests passed with 9 tests; focused CLI source-log/LunaHook status tests passed with 3 tests.

Full regression verification:

```powershell
python -m unittest discover -v
```

Result: 140 tests passed.

## 2026-05-24 Closed-Loop Noise Cleanup And Proof Summary

- `source-log-status` now emits `closedLoopProof`, a compact proof object that brings together:
  - latest importable source-log line,
  - latest LunaHook captured text,
  - latest watcher matched entry ids,
  - latest subtitle event text/match type/visibility/miss-log state,
  - watcher/subtitle/LunaHook bridge process activity.
- During live play, LunaHook captured a non-story UI help line beginning `タッチパネル用ＵＩを左に移動します...`; this briefly added `lunahook:6`.
- Cleaned the real project state by removing that exact noise entry from `translation-state.json` and `story-entries.json`, restoring project progress to `32978` total, `6950` translated, `26028` pending, `0` failed.
- Removed the UI help line from `lunahook-source.txt`; the source log now contains only the five real story captures/replays, with one duplicate opening line from replaying START.
- `ClipboardLogImporter` now filters UI/control help lines when at least three known UI terms appear, and reports `controlLineCount` in capture stats.
- `LunaHookBridge` now seeds duplicate detection from the existing source log in append mode, so a restarted bridge does not append text already present in the source log.
- Started a fresh real integrated session after cleanup:
  - Report: `logs\source-log-session-20260524-224421-report.json`.
  - Game pid `26324`.
  - Watcher pid `34316`.
  - Subtitle-window pid `46516`.
  - LunaHook bridge pid `41028`.
  - Clipboard bridge disabled.
- Re-entered the story from the title menu. The active session captured `「これが最後の質問だ」`, displayed exact Chinese `「这是最后一个问题」`, and `source-log-status` reported `closedLoopProof.status=closed_loop_displayed`.
- Current real status remains cost-controlled:
  - `progress=6950/32978`, `26028` pending, `0` failed.
  - `sourceLogInspection.captureStats.controlLineCount=0`.
  - `closedLoopProof.subtitleMatchType=exact`, `subtitleVisible=true`, `subtitleMissLogged=false`.

Verification:

```powershell
python -m unittest tests.test_lunahook_bridge tests.test_capture_import tests.test_cli.CliTests.test_source_log_status_reports_paused_scoped_loop -v
python -m unittest discover -v
```

Result: focused tests passed with 5 tests; full regression passed with 142 tests.

Updated stronger UI-filter and active-session proof:

- Tightened UI/control filtering to catch both long and short help strings before import, including `タッチパネル用ＵＩを右に移動します。` and `直前に再生されたボイスを再生します。テキストを自動で読み進めます。`.
- LunaHook bridge now also applies the same UI/control filter before writing to the source log, emitting `skipped_control` in its status log for skipped control text.
- Cleaned the real state again after old pre-patch bridge output:
  - Removed 3 UI/control lines from `lunahook-source.txt`.
  - Removed 2 transient UI/control entries from `translation-state.json` and `story-entries.json`.
  - Project returned to `32978` total / `6950` translated / `26028` pending / `0` failed.
- Fresh active integrated session after the stronger filter:
  - Report: `logs\source-log-session-20260524-225357-report.json`.
  - Game pid `26324`.
  - Watcher pid `3292`.
  - Subtitle-window pid `14860`.
  - LunaHook bridge pid `37836`.
  - Clipboard bridge disabled.
- Advanced the game one more line with the patched bridge active:
  - Captured source: `――ああ、失敗した。`
  - Matched imported Artemis id: `script/01_01プロローグ_01.ast:143`
  - Subtitle text: `——啊啊，搞砸了。`
  - `closedLoopProof.status=closed_loop_displayed`, `subtitleMatchType=exact`, `subtitleVisible=true`, `subtitleMissLogged=false`.
- Current project progress remains cost-controlled at `6950/32978`, with no global archive translation resumed.

Verification:

```powershell
python -m unittest discover -v
```

Result: 144 tests passed.

## 2026-05-24 Game Window Closed-Loop Status Evidence

- Advanced the live `selectoblige.exe` story window once through Windows input automation while the integrated source-log session was running.
- LunaHook bridge appended the new runtime line `「選べ。認めるか、認めないか」` to `C:\Users\deepd\AppData\Local\GalTranslator\real-session-selectoblige\lunahook-source.txt`.
- The scoped watcher processed the changed source log without global archive translation:
  - Latest processed cycle: `887`.
  - `lastProcessedScopedTranslatedCount=4`.
  - Latest matched id list includes `script/01_01プロローグ_01.ast:73`.
- The external subtitle event log recorded exact visible Chinese output: `「选吧。承认，还是不承认」`, `matchType=exact`, `visible=true`, `missLogged=false`.
- `source-log-status` now includes the parsed source-log subtitle event log under `subtitleWindow.eventLog`, so one status command proves game Hook capture, scoped watcher processing, and subtitle display state.
- Fresh real status:
  - `status=watching_source_log`.
  - Source log: 5 raw lines, 4 unique importable lines, 1 duplicate.
  - Project progress still intentionally partial: `32978` total, `6950` translated, `26028` pending, `0` failed.
  - Watcher pid `43408`, subtitle-window pid `24088`, LunaHook bridge pid `18108`, game pid `31832`, clipboard bridge disabled.

Focused verification:

```powershell
python -m unittest tests.test_cli.CliTests.test_session_info_reads_source_log_session_report_without_recommending_global_translation tests.test_cli.CliTests.test_source_log_status_reports_paused_scoped_loop -v
```

Result: 2 tests passed.

Full regression verification:

```powershell
python -m unittest discover -v
```

Result: 140 tests passed.

## 2026-05-24 Runtime Source-Log Session Started

- Started the persistent real source-log play loop for the imported Artemis project without resuming full archive translation:
  - Project: `C:\Users\deepd\AppData\Local\GalTranslator\real-session-selectoblige\artemis-script-project\projects\pfs-rs-extract-selectoblige-pfs-v0.2.5-b56875e0b374`
  - Source log: `C:\Users\deepd\AppData\Local\GalTranslator\real-session-selectoblige\lunahook-source.txt`
  - Launcher: `scripts/source-log-session.ps1 -ProjectRoot <project> -SourceLog <source-log> -SourceName lunahook`
  - Report: `logs\source-log-session-20260524-210406-report.json`
- `session-info` confirmed the real session is active:
  - Source-log watcher pid: 11584.
  - Subtitle-window pid: 43600.
  - Watcher command includes `--only-new-log-entries`, `--size 1`, `--max-batches 1`, `--watch-max-cycles 0`, and no `--watch-require-ready`.
  - Subtitle command follows the same source log with a paired miss log and event log.
  - Watcher is idle with `reason=log_unchanged`, because the prepared LunaHook source log is still empty.
- Current project progress remains cost-controlled:
  - 6,950 translated.
  - 26,028 pending.
  - 0 failed.
  - 32,978 total.
  - Full archive translation remains paused; the live watcher will translate only log-referenced entries appended during play.
- Verified the already-running session reacts to the prepared source log:
  - Appended the already-translated real opening line `「これが最後の質問だ」` to `lunahook-source.txt`.
  - The running watcher processed the changed source log at cycle 349.
  - Watcher result: `sessionSummary.status=translation_ready`, `scopedTranslatedCount=1`, `plannedBatchCount=0`, `executedBatchCount=0`.
  - Matched imported id: `script/01_01プロローグ_01.ast:16`.
  - The running subtitle window wrote an event with `matchType=exact`, `visible=true`, and `missLogged=false`.
  - Project progress stayed at 6,950 translated, 26,028 pending, and 0 failed, proving the check used local matching and did not trigger full translation.
- Hardened `session-info` watcher diagnostics:
  - JSONL watcher payloads now include `stdout.lastProcessedEvent`.
  - `statusSummary` keeps current watcher state (`lastStatus`, `lastReason`) and the latest processed result (`lastProcessedCycle`, `lastProcessedSessionStatus`, `lastProcessedScopedTranslatedCount`, `lastProcessedLogEntryIds`).
  - This keeps the previous processed source-log result visible even after the watcher returns to long-running idle cycles.
- Ran a bounded real startup smoke before the persistent session:
  - Report: `logs\source-log-session-20260524-210145-report.json`
  - Result: watcher/subtitle started and exited cleanly with an empty source log, no stderr, no lingering Python processes, and `sessionSummary.status=no_new_log_entries`.
- Observed Windows launcher quirk:
  - When `source-log-session.ps1` starts the hidden watcher process, the outer PowerShell invocation can return no captured stdout even though the JSON report is written and the child processes start correctly.
  - The reliable recovery path is `python -m gal_translator session-info <sessionReportPath>` or the latest report under the project `logs` directory.
  - The script now explicitly writes the JSON payload through console output after saving the report, but the saved report remains the authoritative channel.

### Test Result

```powershell
python -m unittest tests.test_cli.CliTests.test_source_log_session_script_plans_scoped_watcher_and_subtitle_window tests.test_cli.CliTests.test_source_log_session_script_creates_missing_source_log_for_live_appenders -v
python -m unittest tests.test_cli.CliTests.test_session_info_reads_source_log_session_report_without_recommending_global_translation tests.test_cli.CliTests.test_session_info_reads_live_session_report_and_returns_runtime_commands -v
python -m unittest discover -v
```

Result: focused source-log session tests passed; focused session-info watcher diagnostics tests passed; full suite passed with 136 tests.

## 2026-05-24 Source-Log Session Launcher

- Added `scripts/source-log-session.ps1` for the paused-full-archive workflow:
  - Starts a scoped background watcher command: `translate-log --watch --only-new-log-entries`.
  - Starts `subtitle-window --source-log` against the same Hook/Textractor/source-log file.
  - Does not use `--watch-require-ready`, because imported Artemis projects can intentionally keep many unrelated entries pending.
  - Defaults to `BatchSize=1` and `MaxBatches=1` to translate only the currently encountered source-log line unless the operator opts into larger batches.
  - Writes watcher stdout/stderr, subtitle stdout/stderr, subtitle events, and miss logs under the project `logs` directory by default.
- Added PowerShell dry-run coverage:
  - Verifies the watcher command includes `--only-new-log-entries`.
  - Verifies the watcher command omits `--watch-require-ready`.
  - Verifies the subtitle command follows the same source log and writes miss/event logs.
- Ran a real-project dry-run against:
  - Project: `C:\Users\deepd\AppData\Local\GalTranslator\real-session-selectoblige\artemis-script-project\projects\pfs-rs-extract-selectoblige-pfs-v0.2.5-b56875e0b374`
  - Source log: `C:\Users\deepd\AppData\Local\GalTranslator\real-session-selectoblige\source-log-session-dryrun.txt`
  - Source name: `lunahook`
  - Result: `status=planned`, scoped watcher command ready, subtitle-window command ready, and full archive translation still paused.
- Updated README, Textractor fallback workflow docs, and release checklist with the new launcher.
- Exposed the same cost-controlled route in the desktop shell:
  - Play Output actions now include `source-log-session`.
  - `desktop --dry-run` now returns a `sourceLogSession` command template pointing at `scripts/source-log-session.ps1`.
  - The desktop payload carries scoped source-log defaults: `sourceLogBatchSize=1`, `sourceLogMaxBatches=1`, and `sourceLogWatchInterval=1.0`.
  - Added a `Start Source-Log Session` Play Output button that only requires an existing project plus a source log, matching the imported Artemis workflow.
- Hardened real startup for Hook appenders:
  - Non-dry-run `source-log-session.ps1` now creates the source log parent directory and empty source log if they are missing.
  - The returned payload includes `sourceLogExists` and `sourceLogCreated`.
  - Added regression coverage proving a missing source log is created even when watcher/subtitle startup is disabled for a bounded test.
- Added source-log session report persistence:
  - `source-log-session.ps1` now writes a default `sessionReportPath` under the project `logs` directory.
  - The report includes `restartCommand`, watcher command/log paths, subtitle command/log paths, source log state, and next actions.
  - Real bounded run wrote `logs\source-log-session-20260524-205332-report.json` for the persistent Artemis project without starting watcher/subtitle.
- Extended `session-info` for source-log session reports:
  - Recognizes top-level `sourceLog` / `watcher` / `subtitleWindow` reports as `reportType=source-log-session`.
  - Treats top-level `watcher` as the source-log watcher and reports stdout/stderr tail diagnostics plus `statusSummary`.
  - Adds `commands.sourceLogSessionCommand` for restoring the full scoped watcher + subtitle window, while preserving the original diagnostic restart command as `sourceLogSessionRestartCommand`.
  - For partially translated imported projects, `nextActions` now explicitly says not to run `translateAllCommand` unless global pending translation is intentional.
- Prepared the persistent real session source-log path without starting watcher/subtitle:
  - `C:\Users\deepd\AppData\Local\GalTranslator\real-session-selectoblige\lunahook-source.txt`
  - Result: file exists, length 0, `sourceLogCreated=true`.
  - Project progress stayed at 6,950 translated, 26,028 pending, 0 failed.

### Test Result

```powershell
python -m unittest tests.test_desktop -v
python -m unittest tests.test_cli.CliTests.test_source_log_session_script_plans_scoped_watcher_and_subtitle_window tests.test_cli.CliTests.test_source_log_session_script_creates_missing_source_log_for_live_appenders -v
python -m unittest tests.test_cli -v
python -m unittest discover -v
```

Result: desktop suite passed with 7 tests; source-log session focused tests passed with 2 tests; CLI suite passed with 74 tests in the prior script slice; full suite now passes with 136 tests.

## 2026-05-24 Source-Log Live Reload Closed Loop

- Ran a closer-to-real play-loop smoke using the persistent Artemis project:
  - Started `subtitle-window` against an initially empty source log with `--miss-log`, `--event-log`, and `--exit-after 25`.
  - Appended one pending Artemis script line to the source log while the subtitle window was already running.
  - Started a background `translate-log --watch --only-new-log-entries --size 1 --max-batches 1` process against the same source log.
- Real pending line used:
  - Entry id: `script/01_06奏命編_01.ast:4545`
  - Source: `どれだけ心が荒れ狂っていたとしても、殺意を明確に抱いた瞬間、何もかもが冷え切っていく。`
  - Translation: `无论内心如何狂乱翻涌，在明确怀抱杀意的那一瞬间，一切都彻底冷却了。`
- The subtitle event log proves live reload behavior:
  - First event: `text=""`, `matchType="unmatched"`, `visible=false`, `missLogged=true`.
  - Second event: translated Chinese text, `matchType="exact"`, `visible=true`, `missLogged=false`.
  - Event log: `logs\live-reload-smoke-subtitle-events.jsonl`
- The watcher stdout proves scoped translation:
  - `existingLogEntryIds=["script/01_06奏命編_01.ast:4545"]`
  - `scopeEntryIds=["script/01_06奏命編_01.ast:4545"]`
  - `appliedCount=1`
  - `finalScopeProgress.status=ready`
  - Watcher log: `logs\live-reload-smoke-watcher-stdout.jsonl`
- Current real translation state after this live-reload proof:
  - 6,950 translated.
  - 26,028 pending.
  - 0 failed.
  - 32,978 total.
- Note: the outer PowerShell orchestration command hit the tool timeout while waiting on child process bookkeeping, but subsequent inspection showed no remaining Python process, empty stderr logs, a completed watcher log, a completed subtitle event log, and the project state advanced exactly one entry.

### Test Result

```powershell
python -m unittest discover -v
```

Result: full suite passed with 132 tests.

## 2026-05-24 Scoped Existing-Pending Miss Closed Loop

- Fixed the scoped feedback path for the Artemis import reality: a runtime miss can already exist in `translation-state.json` as a pending imported script entry, so `translate-log --only-new-log-entries` now scopes to entries referenced by the current log, including existing pending source matches.
- Added payload fields for log scoping:
  - `append.logEntryIds`
  - `append.existingLogEntryIds`
  - `append.addedEntryIds`
- Added tests covering:
  - scoped translation does not translate unrelated global pending entries;
  - scoped logs can target existing pending entries;
  - existing translated log entries do not create unnecessary batches.
- Ran a real scoped miss translation on the persistent Artemis project:
  - Source: `本当の殺意とは……心が底冷えしていくものだと、誰かが言っていた。`
  - Existing pending id: `script/01_06奏命編_01.ast:4529`
  - Command shape: `translate-log ... --source-name artemis-runtime-miss --only-new-log-entries --size 1 --max-batches 1 --timeout 600 --replay-event-log ...`
  - Result: `existingLogEntryIds=["script/01_06奏命編_01.ast:4529"]`, `scopeEntryIds=["script/01_06奏命編_01.ast:4529"]`, `appliedCount=1`, `replayMatched=1`, `replayUnmatched=0`.
  - Translation: `真正的杀意……有人说过，是会让内心寒彻骨髓的东西。`
- Current real translation state after the scoped miss:
  - 6,949 translated.
  - 26,029 pending.
  - 0 failed.
  - 32,978 total.
- Verified the runtime display path:
  - `lookup` returned `matchType=exact` and `showSource=false`.
  - `replay-log` matched 1/1 and wrote `logs\scoped-miss-4529-replay-check-events.jsonl`.
  - `subtitle-window --dry-run --preview-source ... --source-log ...` returned the Chinese-only exact preview.
  - A real self-closing Tk subtitle window ran with `--source-log ... --source-log-from-start --exit-after 1` and wrote `logs\scoped-miss-4529-subtitle-window-events.jsonl` with `visible=true`, `matchType=exact`, and `missLogged=false`.

### Test Result

```powershell
python -m unittest discover -v
```

Result: full suite passed with 132 tests.

## 2026-05-24 Pivot To Scoped Miss-Log Translation

- Paused the "translate every remaining archive entry" approach after the real Artemis project reached 6,948 translated entries out of 32,978.
- Current persistent project:
  - `C:\Users\deepd\AppData\Local\GalTranslator\real-session-selectoblige\artemis-script-project\projects\pfs-rs-extract-selectoblige-pfs-v0.2.5-b56875e0b374`
- Current real translation state:
  - 6,948 translated.
  - 26,030 pending.
  - 0 failed.
  - 21.07% translated.
  - No active translation lock at last check.
- Latest bulk continuation before the pivot:
  - `translate-all ... --size 40 --max-batches 16 --timeout 600`
  - Summary: `logs\translate-all-summary-20260524T194733.json`
  - The run applied 640 entries cleanly, ending at `script/01_06奏命編_01.ast:4515`.
- Implemented a cost-control route for runtime feedback:
  - `CodexBatchTranslator.next_batch(...)` now accepts an optional entry-id scope.
  - `translate-log --only-new-log-entries` appends a capture/miss/source log and translates only log-referenced entries from that invocation.
  - Generated miss-log and source-log watcher commands now include `--only-new-log-entries`, so background feedback will not continue the global archive pending queue.
  - `translate-log` payloads now report `translateScope`, `scopeEntryIds`, `initialScopeProgress`, and `finalScopeProgress`.
  - No-new-line scoped runs return `sessionSummary.status=no_new_log_entries` and do not prepare a Codex batch.
- Real-project dry-run verification:
  - Replayed an already-known translated line through `translate-log --dry-run --only-new-log-entries --size 40 --max-batches 1`.
  - Result: `addedEntryCount=0`, global `pendingCount=26030`, scoped pending `0`, `firstBatch=null`.
  - This confirms the miss-log path will not spend tokens on unrelated global pending entries.

### Test Result

```powershell
python -m unittest discover -v
```

Result at that point: full suite passed with 131 tests. The current baseline after the existing-pending scoped fix is 132 tests.

### Current Recommended Runtime Translation Path

Use the translated entries as the local match base. During play, let Hook/Textractor/source-log/subtitle miss logging capture only lines that are actually encountered, then translate only those log-referenced entries:

```powershell
python -m gal_translator translate-log "<project-root>" ".\misses.txt" --only-new-log-entries --size 40 --max-batches 1 --timeout 600
```

Do not resume full `translate-all` across all 26,030 pending entries unless intentionally spending tokens for broader pretranslation.

## 2026-05-24 Artemis Translation Progress To 6308 Entries

- Continued the persistent real Artemis script translation project:
  - Project root: `C:\Users\deepd\AppData\Local\GalTranslator\real-session-selectoblige\artemis-script-project\projects\pfs-rs-extract-selectoblige-pfs-v0.2.5-b56875e0b374`
- Confirmed pre-run state: 5,668 translated, 27,310 pending, 0 failed, no translation lock.
- Ran sixteen additional real Codex batches:
  - `translate-all ... --size 40 --max-batches 16 --timeout 600`
  - The assistant shell wrapper timed out while the `translate-all` process continued in the background.
  - The background process finished, removed its translation lock, and applied all sixteen batches cleanly.
  - The original redirected summary file `logs\translate-all-summary-20260524T192139.json` is 0 bytes because the outer wrapper timed out before it could flush parsed output.
  - A recovery summary was written to `logs\translate-all-summary-20260524T192139-recovered.json` with the authoritative final state and latest batch metadata.
- Current real script translation progress: 6,308 translated, 26,670 pending, 0 failed, total 32,978.
- Verified a newly translated `01_05過去編_05ah` line through the runtime path:
  - Source: `「やめ、ばかっ、おぉい！！」`
  - Speaker: `凪`
  - Translation: `「住手，笨蛋，喂！！」`
  - `lookup` returned `matchType=exact` and `showSource=false`.
  - `replay-log` against `logs\verified-past05ah-stop-source.txt` matched 1/1 and wrote `logs\verified-past05ah-stop-replay-events.jsonl`.
  - `subtitle-window --dry-run --preview-source ... --source-log ...` returned `preview.text=「住手，笨蛋，喂！！」`, `matchType=exact`, and `showSource=false`.

### Test Result

```powershell
python -m unittest discover -v
```

Result: full suite passed with 128 tests.

### Next Translation Command

The latest run completed despite the assistant wrapper timeout. Continue with the same bounded command:

```powershell
python -m gal_translator translate-all "C:\Users\deepd\AppData\Local\GalTranslator\real-session-selectoblige\artemis-script-project\projects\pfs-rs-extract-selectoblige-pfs-v0.2.5-b56875e0b374" --size 40 --max-batches 16 --timeout 600
```

## 2026-05-24 Artemis Translation Progress To 5668 Entries

- Continued the persistent real Artemis script translation project:
  - Project root: `C:\Users\deepd\AppData\Local\GalTranslator\real-session-selectoblige\artemis-script-project\projects\pfs-rs-extract-selectoblige-pfs-v0.2.5-b56875e0b374`
- Confirmed pre-run state: 5,028 translated, 27,950 pending, 0 failed, no translation lock.
- Ran sixteen additional real Codex batches:
  - `translate-all ... --size 40 --max-batches 16 --timeout 600`
  - Full command output was saved to `logs\translate-all-summary-20260524T190105.json`.
  - All sixteen batches applied cleanly.
- Current real script translation progress: 5,668 translated, 27,310 pending, 0 failed, total 32,978.
- Verified a newly translated `01_04イヴ編_10` line through the runtime path:
  - Source: `「お、おう。分かった」`
  - Speaker: `凪`
  - Translation: `「哦、哦。明白了」`
  - `lookup` returned `matchType=exact` and `showSource=false`.
  - `replay-log` against `logs\verified-eve10-understood-source.txt` matched 1/1 and wrote `logs\verified-eve10-understood-replay-events.jsonl`.
  - `subtitle-window --dry-run --preview-source ... --source-log ...` returned `preview.text=「哦、哦。明白了」`, `matchType=exact`, and `showSource=false`.

### Test Result

```powershell
python -m unittest discover -v
```

Result: full suite passed with 128 tests.

### Next Translation Command

The latest sixteen-batch run was stable:

```powershell
python -m gal_translator translate-all "C:\Users\deepd\AppData\Local\GalTranslator\real-session-selectoblige\artemis-script-project\projects\pfs-rs-extract-selectoblige-pfs-v0.2.5-b56875e0b374" --size 40 --max-batches 16 --timeout 600
```

## 2026-05-24 Artemis Translation Progress To 5028 Entries

- Continued the persistent real Artemis script translation project:
  - Project root: `C:\Users\deepd\AppData\Local\GalTranslator\real-session-selectoblige\artemis-script-project\projects\pfs-rs-extract-selectoblige-pfs-v0.2.5-b56875e0b374`
- Confirmed pre-run state: 4,388 translated, 28,590 pending, 0 failed, no translation lock.
- Ran sixteen additional real Codex batches:
  - `translate-all ... --size 40 --max-batches 16 --timeout 600`
  - Full command output was saved to `logs\translate-all-summary-20260524T184117.json`.
  - All sixteen batches applied cleanly.
- Current real script translation progress: 5,028 translated, 27,950 pending, 0 failed, total 32,978.
- Verified a newly translated `01_04イヴ編_06_2` narration line through the runtime path:
  - Source: `こんなにも容易く、二人きりになれるとは思っていなかった。`
  - Speaker: none.
  - Translation: `没想到竟然这么轻易就能变成两人独处。`
  - `lookup` returned `matchType=exact` and `showSource=false`.
  - `replay-log` against `logs\verified-eve06-alone-source.txt` matched 1/1 and wrote `logs\verified-eve06-alone-replay-events.jsonl`.
  - `subtitle-window --dry-run --preview-source ... --source-log ...` returned `preview.text=没想到竟然这么轻易就能变成两人独处。`, `matchType=exact`, and `showSource=false`.

### Test Result

```powershell
python -m unittest discover -v
```

Result: full suite passed with 128 tests.

### Next Translation Command

The latest sixteen-batch run was stable:

```powershell
python -m gal_translator translate-all "C:\Users\deepd\AppData\Local\GalTranslator\real-session-selectoblige\artemis-script-project\projects\pfs-rs-extract-selectoblige-pfs-v0.2.5-b56875e0b374" --size 40 --max-batches 16 --timeout 600
```

## 2026-05-24 Artemis Translation Progress To 4388 Entries

- Continued the persistent real Artemis script translation project:
  - Project root: `C:\Users\deepd\AppData\Local\GalTranslator\real-session-selectoblige\artemis-script-project\projects\pfs-rs-extract-selectoblige-pfs-v0.2.5-b56875e0b374`
- Confirmed pre-run state: 3,748 translated, 29,230 pending, 0 failed, no translation lock.
- Ran sixteen additional real Codex batches:
  - `translate-all ... --size 40 --max-batches 16 --timeout 600`
  - Full command output was saved to `logs\translate-all-summary-20260524T182210.json`.
  - All sixteen batches applied cleanly.
- Current real script translation progress: 4,388 translated, 28,590 pending, 0 failed, total 32,978.
- Verified a newly translated `01_04イヴ編_03` line through the runtime path:
  - Source: `「ならんわ！！」`
  - Speaker: `凪`
  - Translation: `「才不会啊！！」`
  - `lookup` returned `matchType=exact` and `showSource=false`.
  - `replay-log` against `logs\verified-eve03-nope-source.txt` matched 1/1 and wrote `logs\verified-eve03-nope-replay-events.jsonl`.
  - `subtitle-window --dry-run --preview-source ... --source-log ...` returned `preview.text=「才不会啊！！」`, `matchType=exact`, and `showSource=false`.

### Test Result

```powershell
python -m unittest discover -v
```

Result: full suite passed with 128 tests.

### Next Translation Command

The latest sixteen-batch run was stable:

```powershell
python -m gal_translator translate-all "C:\Users\deepd\AppData\Local\GalTranslator\real-session-selectoblige\artemis-script-project\projects\pfs-rs-extract-selectoblige-pfs-v0.2.5-b56875e0b374" --size 40 --max-batches 16 --timeout 600
```

## 2026-05-24 Artemis Translation Progress To 3748 Entries

- Continued the persistent real Artemis script translation project:
  - Project root: `C:\Users\deepd\AppData\Local\GalTranslator\real-session-selectoblige\artemis-script-project\projects\pfs-rs-extract-selectoblige-pfs-v0.2.5-b56875e0b374`
- Confirmed pre-run state: 3,108 translated, 29,870 pending, 0 failed, no translation lock.
- Ran sixteen additional real Codex batches:
  - `translate-all ... --size 40 --max-batches 16 --timeout 600`
  - Full command output was saved to `logs\translate-all-summary-20260524T180230.json`.
  - All sixteen batches applied cleanly.
- Current real script translation progress: 3,748 translated, 29,230 pending, 0 failed, total 32,978.
- Verified a newly translated `01_03くくる編_06` line through the runtime path:
  - Source: `「っ……」`
  - Speaker: `くくる`
  - Translation: `「唔……」`
  - `lookup` returned `matchType=exact` and `showSource=false`.
  - `replay-log` against `logs\verified-kukuru06-short-source.txt` matched 1/1 and wrote `logs\verified-kukuru06-short-replay-events.jsonl`.
  - `subtitle-window --dry-run --preview-source ... --source-log ...` returned `preview.text=「唔……」`, `matchType=exact`, and `showSource=false`.

### Test Result

```powershell
python -m unittest discover -v
```

Result: full suite passed with 128 tests.

### Next Translation Command

The latest sixteen-batch run was stable:

```powershell
python -m gal_translator translate-all "C:\Users\deepd\AppData\Local\GalTranslator\real-session-selectoblige\artemis-script-project\projects\pfs-rs-extract-selectoblige-pfs-v0.2.5-b56875e0b374" --size 40 --max-batches 16 --timeout 600
```

## 2026-05-24 Artemis Translation Progress To 3108 Entries

- Continued the persistent real Artemis script translation project:
  - Project root: `C:\Users\deepd\AppData\Local\GalTranslator\real-session-selectoblige\artemis-script-project\projects\pfs-rs-extract-selectoblige-pfs-v0.2.5-b56875e0b374`
- Confirmed pre-run state: 2,468 translated, 30,510 pending, 0 failed, no translation lock.
- Ran sixteen additional real Codex batches:
  - `translate-all ... --size 40 --max-batches 16 --timeout 600`
  - Full command output was saved to `logs\translate-all-summary-20260524T174305.json`.
  - All sixteen batches applied cleanly.
  - The last batch reported `result_ready_process_stopped`, confirming the early-result stop path remains active.
- Current real script translation progress: 3,108 translated, 29,870 pending, 0 failed, total 32,978.
- Verified a newly translated `01_03くくる編_03_1` line through the runtime path:
  - Source: `「妙案を思いついたぞ、くくる」`
  - Speaker: `凪`
  - Translation: `「我想到个妙计了，库库露」`
  - `lookup` returned `matchType=exact` and `showSource=false`.
  - `replay-log` against `logs\verified-kukuru03-plan-source.txt` matched 1/1 and wrote `logs\verified-kukuru03-plan-replay-events.jsonl`.
  - `subtitle-window --dry-run --preview-source ... --source-log ...` returned `preview.text=「我想到个妙计了，库库露」`, `matchType=exact`, and `showSource=false`.

### Test Result

```powershell
python -m unittest discover -v
```

Result: full suite passed with 128 tests.

### Next Translation Command

The latest sixteen-batch run was stable:

```powershell
python -m gal_translator translate-all "C:\Users\deepd\AppData\Local\GalTranslator\real-session-selectoblige\artemis-script-project\projects\pfs-rs-extract-selectoblige-pfs-v0.2.5-b56875e0b374" --size 40 --max-batches 16 --timeout 600
```

## 2026-05-24 Artemis Translation Progress To 2468 Entries

- Continued the persistent real Artemis script translation project:
  - Project root: `C:\Users\deepd\AppData\Local\GalTranslator\real-session-selectoblige\artemis-script-project\projects\pfs-rs-extract-selectoblige-pfs-v0.2.5-b56875e0b374`
- Confirmed the post-run state from the previous continuation: 2,428 translated, 30,548 pending, 2 failed, total 32,978.
- Inspected the two failed entries:
  - `script/01_02龍司編_08.ast:2157`, source `「もしよろしければ、空と花ちゃんで対応しましょうか」`, speaker `空`.
  - `script/01_02龍司編_08.ast:2182`, source `「むむっ！　それがいいと思います。奏命様に結婚を申し込むような不埒者ですからね」`, speaker `花`.
  - Both failures were `Codex output missing id`, with `retryCount=0` and `maxRetryReached=false`.
- Ran one targeted retry/continuation batch:
  - `translate-all ... --retry-failed --size 40 --max-batches 1 --timeout 600`
  - Full command output was saved to `logs\translate-all-retry-failed-summary-20260524T173826.json`.
  - The retry reset both failed entries, applied them successfully, and then translated 38 additional pending entries.
  - Apply result: 40 applied, 0 failed, 0 missing, 0 unknown, 0 duplicate, 0 empty.
- Current real script translation progress: 2,468 translated, 30,510 pending, 0 failed, total 32,978.
- Verified a newly translated `01_02龍司編_09` line through the runtime path:
  - Source: `「友達、だからね」`
  - Speaker: `帝雄`
  - Translation: `「因为我们是朋友嘛。」`
  - `lookup` returned `matchType=exact` and `showSource=false`.
  - `replay-log` against `logs\verified-ryuji09-thought-source.txt` matched 1/1 and wrote `logs\verified-ryuji09-thought-replay-events.jsonl`.
  - `subtitle-window --dry-run --preview-source ... --source-log ...` returned `preview.text=「因为我们是朋友嘛。」`, `matchType=exact`, and `showSource=false`.

### Test Result

```powershell
python -m unittest discover -v
```

Result: full suite passed with 128 tests.

### Next Translation Command

The failed-entry retry is clean, so the next continuation can go back to bounded normal batches:

```powershell
python -m gal_translator translate-all "C:\Users\deepd\AppData\Local\GalTranslator\real-session-selectoblige\artemis-script-project\projects\pfs-rs-extract-selectoblige-pfs-v0.2.5-b56875e0b374" --size 40 --max-batches 16 --timeout 600
```

## 2026-05-24 Artemis Translation Progress To 1790 Entries

- Continued the persistent real Artemis script translation project:
  - Project root: `C:\Users\deepd\AppData\Local\GalTranslator\real-session-selectoblige\artemis-script-project\projects\pfs-rs-extract-selectoblige-pfs-v0.2.5-b56875e0b374`
- Confirmed pre-run state: 1,150 translated, 31,828 pending, 0 failed, no translation lock.
- Ran sixteen additional real Codex batches:
  - `translate-all ... --size 40 --max-batches 16 --timeout 600`
  - Full command output was saved to `logs\translate-all-summary-20260524T170152.json`.
  - All sixteen batches applied cleanly.
- Current real script translation progress: 1,790 translated, 31,188 pending, 0 failed, total 32,978.
- Verified a newly translated `01_02龍司編_03a` line through the runtime path:
  - Source: `「そもそも学園を案内してた時は、蓼科様って呼んでた気がするんだけど」`
  - Speaker: `凪`
  - Translation: `「而且最开始带我参观学园的时候，你好像是叫她蓼科大人来着」`
  - `lookup` returned `matchType=exact` and `showSource=false`.
  - `replay-log` against `logs\verified-ryuji03a-tadeshina-source.txt` matched 1/1.
  - `subtitle-window --dry-run --preview-source ... --source-log ...` returned a Chinese-only exact preview. Dry-run preview does not create a subtitle JSONL event file.

### Test Result

```powershell
python -m unittest discover -v
```

Result: full suite passed with 128 tests.

### Next Translation Command

The latest sixteen-batch run was stable:

```powershell
python -m gal_translator translate-all "C:\Users\deepd\AppData\Local\GalTranslator\real-session-selectoblige\artemis-script-project\projects\pfs-rs-extract-selectoblige-pfs-v0.2.5-b56875e0b374" --size 40 --max-batches 16 --timeout 600
```

## 2026-05-24 Artemis Translation Progress To 1150 Entries

- Continued the persistent real Artemis script translation project:
  - Project root: `C:\Users\deepd\AppData\Local\GalTranslator\real-session-selectoblige\artemis-script-project\projects\pfs-rs-extract-selectoblige-pfs-v0.2.5-b56875e0b374`
- Confirmed pre-run state: 830 translated, 32,148 pending, 0 failed, no translation lock.
- Ran eight additional real Codex batches:
  - `translate-all ... --size 40 --max-batches 8 --timeout 600`
  - Full command output was saved to `logs\translate-all-summary-20260524T165043.json` to avoid flooding the working context.
  - All eight batches applied cleanly.
- Current real script translation progress: 1,150 translated, 31,828 pending, 0 failed, total 32,978.
- Verified a newly translated `01_01プロローグ_10` line through the runtime path:
  - Source: `「なるほど……つまりは、こういうことだ」`
  - Speaker: `凪`
  - Translation: `「原来如此……也就是说，是这么回事。」`
  - `lookup` returned `matchType=exact` and `showSource=false`.
  - `replay-log` against `logs\verified-prologue10-thus-source.txt` matched 1/1.
  - `subtitle-window --dry-run --preview-source ... --source-log ...` returned a Chinese-only exact preview. Dry-run preview does not create a subtitle JSONL event file.

### Test Result

```powershell
python -m unittest discover -v
```

Result: full suite passed with 128 tests.

### Next Translation Command

The latest eight-batch run was stable:

```powershell
python -m gal_translator translate-all "C:\Users\deepd\AppData\Local\GalTranslator\real-session-selectoblige\artemis-script-project\projects\pfs-rs-extract-selectoblige-pfs-v0.2.5-b56875e0b374" --size 40 --max-batches 8 --timeout 600
```

## 2026-05-24 Artemis Translation Progress To 830 Entries

- Continued the persistent real Artemis script translation project:
  - Project root: `C:\Users\deepd\AppData\Local\GalTranslator\real-session-selectoblige\artemis-script-project\projects\pfs-rs-extract-selectoblige-pfs-v0.2.5-b56875e0b374`
- Confirmed pre-run state: 510 translated, 32,468 pending, 0 failed, no translation lock.
- Ran eight additional real Codex batches:
  - `translate-all ... --size 40 --max-batches 8 --timeout 600`
  - All eight batches applied cleanly.
- Current real script translation progress: 830 translated, 32,148 pending, 0 failed, total 32,978.
- Verified a newly translated `01_01プロローグ_07a` line through the runtime path:
  - Source: `「嘘じゃないぞ！　ここで偶然会ったんだが、話してみると気が合うもんでさ！」`
  - Speaker: `凪`
  - Translation: `「我没撒谎哦！我们是在这里偶然遇到的，聊了一下发现挺合得来嘛！」`
  - `lookup` returned `matchType=exact` and `showSource=false`.
  - `replay-log` against `logs\verified-prologue07a-lie-source.txt` matched 1/1.
  - `subtitle-window --dry-run --preview-source ... --source-log ...` returned a Chinese-only exact preview. Dry-run preview does not create a subtitle JSONL event file.

### Test Result

```powershell
python -m unittest discover -v
```

Result: full suite passed with 128 tests.

### Next Translation Command

The latest eight-batch run was stable:

```powershell
python -m gal_translator translate-all "C:\Users\deepd\AppData\Local\GalTranslator\real-session-selectoblige\artemis-script-project\projects\pfs-rs-extract-selectoblige-pfs-v0.2.5-b56875e0b374" --size 40 --max-batches 8 --timeout 600
```

## 2026-05-24 Artemis Translation Progress To 510 Entries

- Continued the persistent real Artemis script translation project:
  - Project root: `C:\Users\deepd\AppData\Local\GalTranslator\real-session-selectoblige\artemis-script-project\projects\pfs-rs-extract-selectoblige-pfs-v0.2.5-b56875e0b374`
- Confirmed pre-run state: 350 translated, 32,628 pending, 0 failed, no translation lock.
- Ran four additional real Codex batches:
  - `translate-all ... --size 40 --max-batches 4 --timeout 600`
  - All four batches applied cleanly.
- Current real script translation progress: 510 translated, 32,468 pending, 0 failed, total 32,978.
- Verified a newly translated `01_01プロローグ_03_2` line through the runtime path:
  - Source: `「凪様のサポートが私の仕事ですから。お役に立てたなら何よりですの」`
  - Speaker: `ファイブ`
  - Translation: `「支持凪大人本来就是我的工作。能帮上忙的话，我就再高兴不过了呢」`
  - `lookup` returned `matchType=exact` and `showSource=false`.
  - `replay-log` against `logs\verified-prologue03-support-source.txt` matched 1/1.
  - `subtitle-window --dry-run --preview-source ... --source-log ...` returned a Chinese-only exact preview. Dry-run preview still does not create a subtitle JSONL event file.

### Test Result

```powershell
python -m unittest discover -v
```

Result: full suite passed with 128 tests.

### Next Translation Command

The latest four-batch run was stable:

```powershell
python -m gal_translator translate-all "C:\Users\deepd\AppData\Local\GalTranslator\real-session-selectoblige\artemis-script-project\projects\pfs-rs-extract-selectoblige-pfs-v0.2.5-b56875e0b374" --size 40 --max-batches 4 --timeout 600
```

## 2026-05-24 Artemis Translation Progress To 350 Entries

- Continued the persistent real Artemis script translation project:
  - Project root: `C:\Users\deepd\AppData\Local\GalTranslator\real-session-selectoblige\artemis-script-project\projects\pfs-rs-extract-selectoblige-pfs-v0.2.5-b56875e0b374`
- Confirmed pre-run state: 270 translated, 32,708 pending, 0 failed, no translation lock.
- Ran two additional real Codex batches:
  - `translate-all ... --size 40 --max-batches 2 --timeout 600`
  - Both batches applied cleanly.
- Current real script translation progress: 350 translated, 32,628 pending, 0 failed, total 32,978.
- Verified a newly translated `01_01プロローグ_03_1` line through the runtime path:
  - Source: `「評価をいくらか改善できた所で、部屋に着きましたの」`
  - Speaker: `ファイブ`
  - Translation: `「评价多少改善了一些的时候，我们也到房间了呢。」`
  - `lookup` returned `matchType=exact` and `showSource=false`.
  - `replay-log` against `logs\verified-prologue03-room-source.txt` matched 1/1.
  - `subtitle-window --dry-run --preview-source ... --source-log ...` returned a Chinese-only exact preview. As with the prior dry-run, preview validation did not create a subtitle JSONL event file.

### Test Result

```powershell
python -m unittest discover -v
```

Result: full suite passed with 128 tests.

### Next Translation Command

```powershell
python -m gal_translator translate-all "C:\Users\deepd\AppData\Local\GalTranslator\real-session-selectoblige\artemis-script-project\projects\pfs-rs-extract-selectoblige-pfs-v0.2.5-b56875e0b374" --size 40 --max-batches 2 --timeout 600
```

## 2026-05-24 Artemis Translation Early-Stop And 270-Line Progress

- Hardened real Codex batch execution so `translate-all` now polls the prepared batch `result.json` while Codex is still running.
- When the output file already contains every expected batch id, the runner stops the Codex process tree and records the batch as `result_ready_process_stopped` instead of waiting for a later process timeout.
- Added Windows process-tree termination for this path so child PowerShell/Codex wrapper processes do not keep stdout/stderr files open after early result detection.
- Updated the timeout recovery regression so a complete result written before a long sleep is applied through the new early-stop path.
- Continued the persistent Artemis script translation project:
  - Project root: `C:\Users\deepd\AppData\Local\GalTranslator\real-session-selectoblige\artemis-script-project\projects\pfs-rs-extract-selectoblige-pfs-v0.2.5-b56875e0b374`
- Confirmed pre-run state: 150 translated, 32,828 pending, 0 failed, no translation lock.
- Ran two real Codex translation batches:
  - `translate-all ... --size 40 --max-batches 1 --timeout 600`
  - `translate-all ... --size 40 --max-batches 2 --timeout 600`
- Current real script translation progress: 270 translated, 32,708 pending, 0 failed, total 32,978.
- Verified a newly translated `01_01プロローグ_03_1` line through the runtime path:
  - Source: `「ん……どうした、ファイブ」`
  - Speaker: `凪`
  - Translation: `「嗯……怎么了，Five」`
  - `lookup` returned `matchType=exact` and `showSource=false`.
  - `replay-log` against `logs\verified-prologue03-source.txt` matched 1/1.
  - `subtitle-window --dry-run --preview-source ... --source-log ...` returned a Chinese-only exact preview. The dry-run preview did not create a JSONL event file in this run.

### Test Result

```powershell
python -m unittest discover -v
```

Result: full suite passed with 128 tests.

### Next Translation Command

The latest size-40 batches were stable after early result-stop handling:

```powershell
python -m gal_translator translate-all "C:\Users\deepd\AppData\Local\GalTranslator\real-session-selectoblige\artemis-script-project\projects\pfs-rs-extract-selectoblige-pfs-v0.2.5-b56875e0b374" --size 40 --max-batches 2 --timeout 600
```

## 2026-05-24 Artemis Script Translation Continuation

- Continued the persistent Artemis script translation project:
  - Project root: `C:\Users\deepd\AppData\Local\GalTranslator\real-session-selectoblige\artemis-script-project\projects\pfs-rs-extract-selectoblige-pfs-v0.2.5-b56875e0b374`
- Confirmed pre-run state: 110 translated, 32,868 pending, 0 failed, no translation lock.
- Ran two additional conservative real Codex batches:
  - `translate-all ... --size 20 --max-batches 1 --timeout 600`
  - First batch applied 20 entries from `script\01_01プロローグ_02.ast:408` through `:818`.
  - Second batch applied 20 entries from `script\01_01プロローグ_02.ast:837` through `:1247`.
- Current real script translation progress: 150 translated, 32,828 pending, 0 failed, total 32,978.
- Verified a newly translated `01_01プロローグ_02` line through the runtime path:
  - Source: `「大きなお世話だ。お前は黙っていろ」`
  - Translation: `「少管闲事。你给我闭嘴。」`
  - `lookup` returned `matchType=exact` and `showSource=false`.
  - `replay-log` against `logs\verified-prologue02-source.txt` matched 1/1.
  - `subtitle-window --dry-run --preview-source ... --source-log ...` previewed the exact Chinese-only translation.

### Next Translation Command

```powershell
python -m gal_translator translate-all "C:\Users\deepd\AppData\Local\GalTranslator\real-session-selectoblige\artemis-script-project\projects\pfs-rs-extract-selectoblige-pfs-v0.2.5-b56875e0b374" --size 20 --max-batches 1 --timeout 600
```

## 2026-05-24 Artemis Script Translation Closed-Loop Progress

- Created the persistent real Artemis script project:
  - Project root: `C:\Users\deepd\AppData\Local\GalTranslator\real-session-selectoblige\artemis-script-project\projects\pfs-rs-extract-selectoblige-pfs-v0.2.5-b56875e0b374`
  - Export root: `C:\Users\deepd\AppData\Local\GalTranslator\real-session-selectoblige\pfs-rs-extract-selectoblige-pfs-v0.2.5`
- Imported 220 Artemis `.ast` scripts into the project, producing 32,978 merged story entries.
- Ran real Codex translation batches against the imported script project:
  - First batch: size 10, applied 10 entries.
  - Second batch: size 40, applied 40 entries.
  - Third batch: size 40 timed out after Codex had already written a valid `result.json`; manually applied that result and recovered 40 entries.
  - Fourth batch: size 20, applied 20 entries.
- Current real script translation progress: 110 translated, 32,868 pending, 0 failed, total 32,978.
- Verified local matching for the first script line:
  - Source: `「これが最後の質問だ」`
  - Translation: `「这是最后一个问题」`
  - `lookup` returned `matchType=exact` and `showSource=false`.
  - `replay-log` against `logs\verified-opening-source.txt` matched 1/1 with `matchPercent=100.0`.
  - `subtitle-window --dry-run --preview-source ... --source-log ...` returned `status=ready` and previewed the same Chinese-only translation.
  - A real Tk `subtitle-window` was opened with `--exit-after 3`; `logs\verified-opening-subtitle-events.jsonl` records an exact visible event for `「这是最后一个问题」`.
- Hardened `translate-all` after the real timeout: if Codex times out but has already written a valid result for the prepared batch, `translate-all` now applies it, records `status=timeout_result_applied`, preserves `executionStatus` / `executionReturnCode`, and continues instead of wasting the completed output.
- Added a CLI regression test for timeout-with-valid-result recovery.

### Test Result

```powershell
python -m unittest tests.test_cli.CliTests.test_translate_all_applies_valid_result_written_before_timeout -v
python -m unittest tests.test_cli.CliTests.test_translate_all_runs_fake_codex_until_ready tests.test_cli.CliTests.test_translate_all_failure_reports_batch_log_tails -v
python -m unittest discover -v
```

Result: focused timeout recovery tests passed, and the full suite passed with 128 tests.

### Next Translation Command

Use conservative batches until more timeout behavior is understood:

```powershell
python -m gal_translator translate-all "C:\Users\deepd\AppData\Local\GalTranslator\real-session-selectoblige\artemis-script-project\projects\pfs-rs-extract-selectoblige-pfs-v0.2.5-b56875e0b374" --size 20 --max-batches 1 --timeout 600
```

## 2026-05-24 Artemis AST Importer

- Added a dedicated Artemis `.ast` importer/parser for exported script folders.
- The importer copies exported `**/*.ast` files into the project workspace and parses only `text = { ... ja = { ... } }` story blocks.
- `name = {...}` is preserved as `speaker`, using the final display-name value when Artemis stores both an internal and displayed name.
- Consecutive quoted Japanese strings in one `text.ja` entry are merged into one translation entry, while inline control commands such as `{"rt2"}` and `{"txruby"}` are skipped.
- Each generated story entry keeps `file`, `line`, and a stable `id` based on the source `.ast` path and first text line.
- `python -m gal_translator import <exported-folder>` now automatically uses the Artemis path when `.ast` files are present.
- Added the explicit command `python -m gal_translator import-artemis-ast <exported-folder> --workspace <workspace>`.
- Real export smoke against `C:\Users\deepd\AppData\Local\GalTranslator\real-session-selectoblige\pfs-rs-extract-selectoblige-pfs-v0.2.5` imported 220 scripts and generated 32,978 merged pending translation entries. This is lower than the earlier raw string-segment estimate because multi-line dialogue fragments are now combined per message block.
- The real sample smoke confirms the first parsed entry from `script\01_01プロローグ_01.ast` is `「これが最後の質問だ」` with speaker `？？？`.

### Test Result

```powershell
python -m unittest tests.test_artemis_import -v
python -m unittest tests.test_direct_import -v
python -m unittest tests.test_capture_import -v
python -m unittest tests.test_cli -v
python -m unittest discover -v
```

Result: Artemis importer tests passed, focused direct/capture/CLI regressions passed, and the full suite passed with 127 tests.

### Remaining Near-Term Work

1. Decide the first safe batch size for real `selectoblige` script translation from the 32,978-entry imported state.
2. Add a project-info/import summary view that distinguishes raw string segments from merged story entries if the desktop UI needs that explanation.
3. Continue real-play validation through local matching and the external subtitle window after enough imported script entries have translations.

## 2026-05-24 Artemis PFS Script Export Test

- Used the existing `skill-installer` workflow to check requested skills:
  - `skill-creator` is already preinstalled under the system skills directory.
  - `any-search` was not found in the OpenAI curated skill list, and the experimental list path was unavailable.
- Installed the user-provided AnySearch skill globally from `https://github.com/anysearch-ai/anysearch-skill.git` into `C:\Users\deepd\.codex\skills\any-search`. Restart Codex to load it in new sessions.
- Downloaded `pfs-rs` v0.2.5 Windows x64 from GitHub into `C:\Users\deepd\AppData\Local\GalTranslator\tools\pfs-rs_v0.2.5`.
- Verified the downloaded zip SHA256 against the release checksum: `3c93bdf48f03067c23b8bebc240f34018c1b0f39d01e548508dbaa4000b4579d`.
- Ran `pfs-rs list` against `D:\private\otaku\game\galgame\selectoblige.pfs`; the tool recognized the archive and listed contents.
- Ran a read-only extraction experiment into `C:\Users\deepd\AppData\Local\GalTranslator\real-session-selectoblige\pfs-rs-extract-selectoblige-pfs-v0.2.5`.
- Extracted `script\*.ast` count: 220 files, about 14.5 MB total.
- Confirmed the extracted `.ast` scripts are readable UTF-8 Artemis script text. The line previously captured through LunaHook, `「これが最後の質問だ」`, appears in `script\01_01プロローグ_01.ast`.
- Quick source-volume estimate:
  - 197 `.ast` files contain story string segments.
  - About 50,924 Japanese story string segments.
  - About 866,592 Japanese story characters.
  - 297 Japanese `text="..."` attributes.
  - 80 unique Japanese speaker/display names.

### Next Implementation Step

Build an Artemis `.ast` importer for exported script folders. It should parse `text.ja` blocks, combine multi-line message strings separated by runtime markers, preserve speaker names, skip asset/control commands, and feed the existing Codex batch translation pipeline.

## 2026-05-24 First Desktop Product Shell

- Added `gal_translator/desktop.py`, a Tk desktop shell that wraps the verified CLI workflow instead of duplicating translation logic.
- The shell has two user-facing entries:
  - Translation Preparation: browse/select game path, source log, project root, miss log, and workspace; run scan, inspect-log, direct import, capture/append log import, project-info, translate-all, and retry-failed.
  - Play Output: open the existing styled `subtitle-window` against a project/source log, run subtitle dry-run checks, or start `live-session` with source-log following and miss-log feedback.
- The preparation UI updates the project root from command JSON, shows translation progress from returned payloads, and surfaces the existing 3-retry-limit abandon/ignore warning when retry payloads skip failed entries.
- The play UI uses `subtitle-window --source-log --miss-log` and `live-session --subtitle-source-log --subtitle-detach --subtitle-miss-log`, keeping runtime behavior local-match/external-window only.
- Added `python -m gal_translator desktop` and `python -m gal_translator desktop --dry-run`; dry-run emits the two entries, MVP scope flags, default config, and CLI command templates.
- Added `tests/test_desktop.py` for the dry-run payload, MVP-scope exclusions, translate retry command, source-log subtitle command, and live-session miss feedback command.

### Test Result

```powershell
python -m unittest tests.test_desktop -v
python -m gal_translator desktop --dry-run
python -m unittest discover -v
```

Result: desktop tests passed, desktop dry-run returned `status=ready`, and the full suite passed with 124 tests.

### Remaining Near-Term Work

1. Run an interactive desktop-shell smoke during real play.
2. Tune the UI around actual operator friction from choosing Hook/source logs and reading command output.
3. Continue hardening recovery messages when real logs expose new failure modes.

## 2026-05-24 Session Memory And Next Product Target

- Current validated baseline remains the LunaHook real-game closed loop for `selectoblige.exe`: live hook capture, import, real Codex batch translation, replay match, and external subtitle-window display have all been verified.
- Failed translation recovery is now bounded at 3 retry resets per entry. After that, retry commands skip the entry and surface a reminder that the user can usually abandon an isolated failed line.
- Product direction is now one desktop software with two user-facing areas:
  - Translation entry: choose game directory/source log, inspect/import text, batch translate, show progress, retry failed work, warn on 3-time failures.
  - Play output entry: open during gameplay, follow Hook/Textractor/clipboard/source-log text, locally match translated entries, and display a polished external bilingual or translated subtitle window.
- Next development target is to build the product shell around the already verified CLI workflow, while keeping MVP scope to external subtitle output and local matching.

## 2026-05-24 Failed Translation Retry Limit

- Added per-entry retry tracking to `translation-state.json`: new and appended items now carry `retryCount` and `maxRetryReached`.
- `retry-failed`, `translate-all --retry-failed`, and `resume-session --retry-failed` now respect a default retry limit of 3 resets per failed entry.
- After an entry has already been retried 3 times and fails again, it is left in `failed` instead of being moved back to `pending`.
- Retry payloads now report `skippedCount`, `retryLimit`, `skippedIds`, and a `nextActions` reminder that isolated lines can usually be abandoned after three failed retries.
- `project-info` now exposes `failedRetry` and changes `nextActions` when failed entries have reached the 3-retry limit, so the future UI can show a clear warning.
- Added tests covering the retry limit at both tracker and CLI payload levels.

### Test Result

```powershell
python -m unittest discover -v
```

Result: 118 tests passed.

## 2026-05-24 Real Hooked Story Closed Loop

- Downloaded the official LunaTranslator x64 Windows 10 portable release into `C:\Users\deepd\AppData\Local\GalTranslator\tools\LunaTranslator_x64_win10_v10.15.8.22` and used its bundled LunaHook host DLL directly for a non-GUI capture smoke.
- Confirmed the target game is x64 and that LunaHook identifies `D:\private\otaku\game\galgame\selectoblige.exe` as Artemis.
- LunaHook inserted working Artemis hooks for this sample:
  - `ENHVXN-24@195720:selectoblige.exe` (`Artemis64x`)
  - `HVXN-4C@1971E0:selectoblige.exe` (`Artemis`)
- Captured real hooked story text while the game was running: `「これが最後の質問だ」`.
- `inspect-log` on the LunaHook output reported `status=ready_to_import`, `rawLineCount=6`, `uniqueImportedEntryCount=1`, and skipped non-Japanese/duplicate lines.
- Imported the hooked story log into `C:\Users\deepd\AppData\Local\GalTranslator\real-session-selectoblige\luna-story-project\projects\galgame-48e307fe10a8`.
- Ran real Codex translation with `translate-all --size 1 --timeout 600`; final progress was `ready` with 1 translated, 0 pending, 0 failed.
- Codex translation for `「これが最後の質問だ」`: `“这是最后一个问题。”`.
- Verified `replay-log` matched 1/1 hooked story line at `matchPercent=100.0`, `matchType=exact`, and `showSource=false`.
- Ran a live closed-loop session: launched the game, moved the off-screen Artemis window onto the primary display, started `subtitle-window --source-log` against a live LunaHook log, appended real Hook output, matched locally, and showed the Simplified Chinese subtitle while the game showed the corresponding Japanese text.
- Closed the game, subtitle window, and leftover temporary watcher processes after verification.

### Real Hook Artifacts

- Raw Hook text log: `C:\Users\deepd\AppData\Local\GalTranslator\real-session-selectoblige\luna-story-smoke-2\text.txt`
- Hook event log: `C:\Users\deepd\AppData\Local\GalTranslator\real-session-selectoblige\luna-story-smoke-2\events.jsonl`
- Project root: `C:\Users\deepd\AppData\Local\GalTranslator\real-session-selectoblige\luna-story-project\projects\galgame-48e307fe10a8`
- Replay event log: `C:\Users\deepd\AppData\Local\GalTranslator\real-session-selectoblige\luna-story-project\replay-events.jsonl`
- Live source log: `C:\Users\deepd\AppData\Local\GalTranslator\real-session-selectoblige\closed-loop-lunahook-final\live-lunahook.txt`
- Live subtitle event log: `C:\Users\deepd\AppData\Local\GalTranslator\real-session-selectoblige\closed-loop-lunahook-final\subtitle-events.jsonl`
- Closed-loop screenshot: `C:\Users\deepd\AppData\Local\GalTranslator\real-session-selectoblige\closed-loop-lunahook-final\target-line-game-and-subtitle.png`

### Test Result

```powershell
python -m unittest discover -v
```

Result: 116 tests passed.

## 2026-05-24 Real Game Launch And Menu Translation Smoke

- Launched `D:\private\otaku\game\galgame\selectoblige.exe` repeatedly under controlled scripts and confirmed every launched `selectoblige` process was closed afterward.
- Installed Textractor through `winget`; the usable files were unpacked to `C:\Users\deepd\Desktop\Textractor\x64` and `x86`.
- Found that `TextractorCLI.exe` must be started first and then controlled through stdin; direct process arguments only print usage.
- Attached `TextractorCLI.exe` to the game process through stdin, but automatic hooks only emitted the Clipboard thread and did not capture game/menu/story text for this Artemis/PF8 sample.
- Found the game window launches off the visible primary screen at coordinates similar to `1911,-1933,4487,-365`; moved it back to the primary screen with Win32 `MoveWindow` before interaction.
- Fixed a real Windows clipboard crash in `WindowsClipboardProvider`: `GlobalLock` / `GlobalUnlock` and related Win32 calls now declare pointer-sized argument types, so 64-bit clipboard handles no longer overflow.
- Added a Windows regression test covering real clipboard reads without handle overflow.
- Used actual visible menu text from the running game (`ゲームを始める`, `前回の続きから始める`, `ロードして始める`, `環境設定`, `ゲームを終了する`) as a manual source-log smoke because automatic Textractor capture was not available.
- Imported those 5 visible menu lines into `C:\Users\deepd\AppData\Local\GalTranslator\real-session-selectoblige\projects\galgame-48e307fe10a8`.
- Ran real Codex translation with `translate-all --size 5 --timeout 600`; final progress was `ready` with 5 translated, 0 pending, 0 failed.
- Verified `replay-log` matched 5/5 lines at 100% with Chinese-only runtime text.
- Verified `lookup "ゲームを始める"` returns `开始游戏` with `showSource=false`.
- Verified `subtitle-window --source-log --source-log-from-start` over the running game wrote exact visible runtime events for all 5 Chinese menu translations and showed the final Chinese subtitle `结束游戏` in a real window screenshot.

### Test Result

```powershell
python -m unittest discover -v
```

Result: 116 tests passed.

### Real Smoke Artifacts

- Manual visible-menu source log: `C:\Users\deepd\AppData\Local\GalTranslator\real-session-selectoblige\selectoblige-menu-visible-text.txt`
- Project root: `C:\Users\deepd\AppData\Local\GalTranslator\real-session-selectoblige\projects\galgame-48e307fe10a8`
- Replay event log: `C:\Users\deepd\AppData\Local\GalTranslator\real-session-selectoblige\menu-replay-events.jsonl`
- Subtitle source-log event log: `C:\Users\deepd\AppData\Local\GalTranslator\real-session-selectoblige\menu-subtitle-source-log-events.jsonl`
- Screenshot showing the game and external subtitle window: `C:\Users\deepd\AppData\Local\GalTranslator\real-session-selectoblige\game-with-subtitle-source-log.png`

### Remaining Near-Term Work

1. Get a real Textractor hook or hook code for this Artemis/PF8 sample; current TextractorCLI auto-attach did not capture game text.
2. Capture actual story text through Textractor/clipboard instead of a manual visible-menu source log.
3. Repeat `inspect-log` -> `capture-log`/`append-log` -> `translate-all` -> `replay-log` -> live `subtitle-window` with that hooked story log.

## 2026-05-24 Resume Record And Recovery Command Hardening

- Confirmed the repository already has `PROJECT_RECORD.md` as the compact new-conversation handoff file.
- Refreshed `PROJECT_RECORD.md` with the current baseline, verified commands, real-sample scan status, and next external blockers.
- Ran `python -m gal_translator doctor`: status `ready`; Python 3.10.6, Codex on PATH, Tkinter importable, and workspace writable.
- Rechecked the real sample `D:\private\otaku\game\galgame\selectoblige.exe` with `scan`; it still reports `pf8_pfs_ast` first, with `selectoblige.pfs` exposing 220 visible `.ast` script entries in the archive table.
- Rechecked `archive-list --scripts-only --limit 5`; it lists five `script\*.ast` entries from `selectoblige.pfs`. This remains diagnostic-only, with no archive extraction/decryption.
- No real Textractor/clipboard story log was found in the repository, so real import/translate/replay/subtitle validation remains blocked on captured runtime text.
- Fixed synthesized default `subtitle-window` resume commands so unset position values are omitted instead of emitted as `--x None --y None`.
- Added CLI regression coverage for the resume-session path that synthesizes a default subtitle command after pending translation completes.

### Test Result

```powershell
python -m unittest discover -v
```

Result after the code change: 115 tests passed.

Focused regression checks after the code change:

```powershell
python -m unittest tests.test_cli.CliTests.test_resume_session_translates_pending_entries_from_report -v
python -m unittest tests.test_cli.CliTests.test_session_info_points_empty_project_with_source_log_at_resume_session -v
```

Result: both focused tests passed.

Additional CLI smoke:

```powershell
python -m gal_translator smoke-test --workspace .tmp-smoke-resume-record-afterfix
```

Result: synthetic workflow `status=passed`; every `checks` value was true.

### Remaining Near-Term Work

1. Rerun the full test suite after the resume-command patch before handing off.
2. Use `inspect-log` on a real Textractor/clipboard log and require `status=ready_to_import` or `ready_with_repeated_sources`.
3. Import the real log, run real `translate-all`, replay the same log, and verify a visible subtitle window during actual play.

## 2026-05-22 Inspect Log Diagnostics

- Added repeated-source diagnostics to capture statistics: `uniqueImportedEntryCount` and `repeatedSourceCount`.
- `inspect-log` now reports a top-level `status` such as `ready_to_import`, `ready_with_repeated_sources`, `empty_log`, `no_candidate_text`, or `no_japanese_text`.
- `inspect-log.nextActions` now points real-log validation at hook/encoding repair when no Japanese text is found, and tells users to treat `uniqueImportedEntryCount` as the expected pending translation count for repeated Textractor logs.
- Updated README, Textractor fallback workflow docs, release checklist, and `PROJECT_RECORD.md` to use the new real-log validation fields.

### Test Result

```powershell
python -m unittest discover -v
```

Result: 115 tests passed.

Additional CLI smoke:

```powershell
python -m gal_translator smoke-test --workspace .tmp-smoke-inspectdiagnostics
```

Result: synthetic workflow `status=passed`; all smoke `checks` values were true, and `inspectLog.status=ready_to_import` with `uniqueImportedEntryCount=2`.

### Remaining Near-Term Work

1. Use `inspect-log` on a real Textractor/clipboard log and require `status=ready_to_import` or `ready_with_repeated_sources`.
2. Use `captureStats.uniqueImportedEntryCount` as the expected translation-entry count, then run `capture-log` or `append-log`.
3. Run real `translate-all`, `replay-log --event-log`, and visible `subtitle-window` validation.

## 2026-05-21 Local End-to-End Smoke Test

- Added `PROJECT_RECORD.md` as the compact project record and task board for new conversations. It records the project goal, repository structure, current baseline, main workflow commands, completed/in-progress/next tasks, external blockers, and a ready-to-use resume prompt.
- Added `python -m gal_translator smoke-test` as a synthetic local workflow check.
- The command creates a disposable fake game, fake Textractor-style log, and fake Codex launcher.
- The smoke path verifies `inspect-log`, capture import, `translate-all`, result apply, `replay-log`, subtitle-window dry-run payloads, saved play-session reports, `session-info`, and `resume-session --dry-run --open-subtitle --start-miss-watcher --start-session-log-watcher`.
- Added `subtitle-window --preview-source` so dry-run payloads can show the exact translated preview for one captured source line, and real windows can open with that translated line already visible before clipboard polling takes over.
- Added `play-session --subtitle-preview-source` and `--subtitle-preview-first-match`; the one-command session path can now seed `subtitle-window` with a known translated line and returns `subtitleWindow.preview`.
- `scripts/translated-session.ps1` and `scripts/live-session.ps1` expose `-SubtitlePreviewSource` and `-SubtitlePreviewFirstMatch`.
- Added `smoke-test --open-subtitle` so the synthetic end-to-end smoke can optionally launch the translated subtitle window as a detached process and report detached startup status.
- Added `subtitle-window --exit-after`, plus `play-session --subtitle-exit-after`, `smoke-test --subtitle-exit-after`, and PowerShell wrapper pass-through, so UI smoke runs can close themselves.
- Fixed detached subtitle startup in repository/dev mode by launching detached module commands from the caller cwd instead of the project workspace cwd.
- Added `subtitle-window --source-log` and `play-session --subtitle-source-log` so the runtime subtitle window can follow appended Textractor/clipboard log lines directly, using the same cleaning/filtering as `inspect-log` and `capture-log`.
- `scripts/start-subtitle-window.ps1`, `scripts/translated-session.ps1`, and `scripts/live-session.ps1` now pass through log-driven subtitle input options.
- `subtitle-window` now rechecks the last unmatched source during idle polls, so a line captured into the miss-log feedback loop can appear after `translate-log --watch` applies its translation without waiting for the source text to repeat.
- `session-info` now rechecks saved live-session miss watcher pids when available and reports watcher stdout/stderr tail diagnostics, making hidden watcher failures visible during recovery.
- `play-session` / `session-info` now expose `translateSessionLogCommand` and readiness-guarded `watchSessionLogCommand`, so `subtitle-window --source-log` has a matching background translator for newly appended Textractor/session-log lines.
- `resume-session` and `scripts/resume-session.ps1` now accept `--start-session-log-watcher` / `-StartSessionLogWatcher`, and saved `resumeCommand` arrays include it when a source-log subtitle session has a saved watcher command.
- `scripts/live-session.ps1 -SubtitleSourceLog` now starts a hidden readiness-guarded `sessionLogWatcher` for the same capture log, and `session-info` reports its process/log diagnostics alongside the miss watcher.
- `capture-log`, capture append, `append-log`, and `translate-log` now keep one project translation entry per unique captured source text, so growing Textractor logs do not add duplicate pending translations when the same line appears at a new line id.
- `session-info` now adds watcher `statusSummary` fields derived from the last JSONL event, including last status/reason/cycle and last added/pending/translated counts where available.
- `session-info` now includes `sessionLogInspection` for the saved session/capture log, reusing captureStats so no-source reports show whether the saved log actually contains importable Japanese lines.
- `session-info` now returns `appendSessionLogCommand`, and `resume-session` can append a saved session log into an empty project before continuing translation.
- `session-info` now returns `resumeSessionCommand` and points empty-project recovery at it when the saved log already has importable Japanese source lines.
- `smoke-test` now treats `sessionInfo.commands.resumeSessionCommand` as a required check, so saved-report recovery command regressions fail the local smoke.
- `resume-session --open-subtitle` now builds a default subtitle-window command when an older saved report has no subtitle command, following the saved session log when it exists.
- `session-info` now includes `--open-subtitle` in `resumeSessionCommand` when recovery can use either a saved or default subtitle-window command.
- `smoke-test` now requires returned `resumeSessionCommand` to include `--open-subtitle` whenever `session-info` exposes a subtitle-window command.
- The default-subtitle recovery test now executes the returned `session-info.commands.resumeSessionCommand` in dry-run mode, proving the advertised command reaches `subtitle_planned`.
- `session-info` now synthesizes `translateMissLogCommand` and `watchMissLogCommand` from saved `missLogPath` for older reports, and returned resume commands can start the synthesized miss-log watcher.
- `session-info` now synthesizes `translateSessionLogCommand` and `watchSessionLogCommand` from saved `sessionLogPath` for older reports, and returned resume commands can start the synthesized session-log watcher.
- Saved `play-session --session-report` payloads now build `resumeCommand` with the same synthesized subtitle, miss-log watcher, and session-log watcher recovery flags that `session-info` reports later.
- `smoke-test` now executes the saved `playSession.resumeCommand` with `--dry-run` in a subprocess, so the user-facing report command is verified instead of only the internal resume helper.
- `smoke-test` now also requires the saved `resumeCommand` to match `session-info.commands.resumeSessionCommand` and to dry-run both miss-log and session-log watcher recovery plans.
- `smoke-test --open-subtitle --subtitle-exit-after <seconds>` now also runs `resume-session <report> --open-subtitle` as a real subprocess, proving saved-report recovery can start a detached subtitle window while the auto-close guard prevents a leftover window.
- Self-closing UI smoke now waits for both detached subtitle processes to exit and reports `subtitleWindowAutoClosed` / `resumeSubtitleWindowAutoClosed`, so `smoke-test` itself catches leftover subtitle windows.
- `smoke-test` now appends a new simulated Textractor/source-log line after the initial session, runs `translate-log --watch --watch-require-ready` through the real CLI, and verifies `lookup` can immediately match the newly translated line.
- Self-closing UI smoke now also starts a real `subtitle-window --source-log --source-log-from-start` after the feedback translation and verifies the runtime event log contains the newly translated line as a visible exact match.
- Self-closing UI smoke now also verifies the live tailing path: `subtitle-window --source-log` starts before a new line is appended, records the line as unmatched, then records the same line as a visible exact match after `translate-log --watch` updates the project.
- Added a first-class Python `live-session` CLI supervisor that starts readiness-guarded miss/session-log watchers, runs `play-session`, writes a live-session report, and returns a `resumeCommand` without requiring the PowerShell wrapper.
- Python `live-session` now includes watcher stdout/stderr tails and `statusSummary` in its own returned payload and saved report, so watcher wait states are visible without a separate `session-info` run.
- Python `live-session.nextActions` now turns watcher wait reasons such as `log_missing`, `translation_not_ready`, and `translation_locked` into direct recovery guidance.
- Failed Codex batches now expose stdout/stderr tails and result JSON summaries directly in `translate-all` batch payloads, and `project-info.latestCodexBatch` reports the same tail diagnostics for later recovery.
- `translate-all --retry-failed` now resets failed entries to pending inside the same translation lock before running batches.
- `play-session` and `live-session` expose the same full-translation retry behavior as `--translate-retry-failed`; their saved resume commands include `--retry-failed` when requested.
- `resume-session --retry-failed` and `scripts/resume-session.ps1 -RetryFailed` now reset failed translation entries to pending and continue the saved-report translation flow.
- `smoke-test` now includes a retry-failed saved-report recovery scenario and requires `checks.retryFailedResumeRecovered=true`.
- `subtitle-window` now supports reusable layout/style JSON through `--config` and `--save-config`, with explicit CLI window options overriding loaded config values.
- `play-session` and `live-session` expose the same config path through `--subtitle-config` / `--subtitle-save-config`.
- `scripts/start-subtitle-window.ps1`, `scripts/translated-session.ps1`, and `scripts/live-session.ps1` pass the subtitle config options through.
- `smoke-test` now runs a bounded Python `live-session` dry-run and requires the saved report to round-trip through `session-info` plus the returned `resumeCommand --dry-run`.
- `live-session.ps1` smoke coverage now executes the returned PowerShell `resumeCommand -DryRun`, proving the wrapper's saved recovery command reaches the next planned recovery action.
- Added a CLI integration test covering the smoke command from the real `python -m gal_translator` entry point.
- Updated README, Textractor fallback workflow docs, and release checklist to run `smoke-test` before real game/Textractor validation and to document subtitle preview checks.

### Test Result

```powershell
python -m unittest discover -v
```

Result: 112 tests passed.

Additional CLI smoke:

```powershell
python -m gal_translator smoke-test --workspace .tmp-smoke
python -m gal_translator smoke-test --help
python -m gal_translator subtitle-window --help
python -m gal_translator play-session --help
python -m gal_translator smoke-test --workspace .tmp-smoke-ui3 --open-subtitle --subtitle-exit-after 1
```

Result: synthetic workflow status `passed`; all smoke `checks` values were true, including `subtitlePreviewMatched`; subtitle-window help exposes `--preview-source`; play-session help exposes `--subtitle-preview-source` and `--subtitle-preview-first-match`.
Additional UI smoke: `smoke-test --open-subtitle --subtitle-exit-after 1` started a detached subtitle window successfully, returned `status=passed` with `subtitleWindowStarted=true`, and auto-closed.
Additional log-input smoke: targeted tests cover `TextLogRuntimeInput`, `subtitle-window --dry-run --source-log`, and `play-session --subtitle-source-log` command generation. `python -m gal_translator smoke-test --workspace .tmp-smoke-loginput` returned `status=passed` and wrote `--source-log` into the saved subtitle-window command.
Additional runtime refresh smoke: subtitle view-model tests cover unmatched-source refresh after the translation index changes, and confirm cleared subtitles are not restored by idle refresh.
Additional session recovery smoke: saved live-session reports with a stale watcher pid now show `missWatcher.currentProcessActive=false` and expose `missWatcher.stdout.lastEvent`.
Additional session-log watcher smoke: play-session payload tests confirm `translateSessionLogCommand` / `watchSessionLogCommand` point at the session log with the original source name, live-session starts `sessionLogWatcher` in source-log mode, session-info returns saved `watchSessionLogCommand` plus watcher diagnostics, and resume-session dry-run plans both miss-log and session-log watcher restore.
Additional capture idempotency smoke: capture replace and append-log now skip already-known source text even when a later Textractor line gives it a different line id, while still preserving collision-safe ids for different text at the same line id.
Additional watcher diagnostic smoke: session-info now reports compact `statusSummary` fields for miss/session-log watchers and turns active wait reasons like `translation_not_ready` into explicit nextActions.
Additional session log inspection smoke: session-info now reports `sessionLogInspection.status=has_source` for useful saved logs and `no_source_text` with a direct nextAction when the saved log contains no importable Japanese source.
Additional resume recovery smoke: resume-session now plans `append-log` in dry-run when the saved session log has source text but the project is empty, and a real resume appends that log before running translate-all.
Additional session-info recovery smoke: empty projects with a saved importable session log now return `resumeSessionCommand` and make it the first recovery action.
Additional smoke coverage: the synthetic end-to-end smoke now requires `checks.sessionInfoResumeCommand=true`.
Additional subtitle recovery smoke: resume-session dry-run can now plan a default `subtitle-window --source-log` command for translated projects whose saved report lacked a subtitle command.
Additional resume command smoke: session-info now returns `resumeSessionCommand` with `--open-subtitle` for older translated reports whose subtitle command is synthesized during recovery.
Additional executable resume command smoke: the returned `session-info.commands.resumeSessionCommand` is executed with `--dry-run` and reaches `status=subtitle_planned`.
Additional retry recovery smoke: `resume-session --retry-failed --dry-run` reports `retry_failed_planned`, and a real `resume-session --retry-failed` resets failed entries, reruns fake Codex through `translate-all`, and reaches `subtitle_ready`.
Additional retry recovery smoke gate: synthetic `smoke-test` now creates a failed-entry saved report and requires the same `resume-session --retry-failed` path to reach a ready translated project.
Additional direct retry smoke: `translate-all --retry-failed` resets a failed item, translates it with pending items, and reaches final progress `ready`.
Additional subtitle config smoke: `subtitle-window --dry-run --config <json> --save-config <json>` loads reusable layout/style settings, applies explicit CLI overrides, and writes the resolved config JSON.
Additional miss-log watcher recovery smoke: older reports without saved watcher commands now get synthesized `watchMissLogCommand`, and the returned resume command dry-run plans miss-log translation.
Additional session-log watcher recovery smoke: older reports without saved watcher commands now get synthesized `watchSessionLogCommand`, and the returned resume command dry-run plans session-log translation.
Additional saved report recovery smoke: `play-session --session-report` now writes a `resumeCommand` that matches `session-info.commands.resumeSessionCommand`.
Additional executable saved report smoke: synthetic `smoke-test` now requires `checks.savedResumeCommandExecutable=true` after running the saved `resumeCommand --dry-run`.
Additional saved report parity smoke: synthetic `smoke-test` now requires `checks.savedResumeCommandMatchesSessionInfo=true` and `checks.savedResumeCommandPlansWatchers=true`.
Additional resume UI smoke: self-closing UI smoke now verifies `checks.resumeSubtitleWindowStarted=true` after running `resume-session <report> --open-subtitle`.
Additional subtitle auto-close smoke: self-closing UI smoke now verifies `checks.subtitleWindowAutoClosed=true`, `checks.resumeSubtitleWindowAutoClosed=true`, and `subtitleAutoClose.status=passed`.
Additional source-log feedback smoke: synthetic smoke now verifies `checks.sourceLogFeedbackTranslated=true` after appending a new source-log line, processing it with `translate-log --watch`, and matching it through `lookup`.
Additional source-log subtitle-window smoke: self-closing UI smoke now verifies `checks.sourceLogSubtitleWindowDisplayed=true` after a real subtitle window reads the source log and writes a visible exact-match runtime event for the newly translated line.
Additional live source-log refresh smoke: self-closing UI smoke now verifies `checks.sourceLogLiveRefreshDisplayed=true`; the runtime event log must contain both an unmatched event before translation and an exact visible event after project reload, without repeating the source line.
Additional Python live-session smoke: `python -m gal_translator live-session ... --translate-dry-run --no-subtitle --subtitle-source-log --watch-max-cycles 1` now returns watcher command/log payloads with `statusSummary`, writes a session report, surfaces watcher wait reasons in `nextActions`, its `resumeCommand --dry-run` reaches `translation_planned`, and `session-info` recovers the saved watcher commands from the report.
Additional top-level live-session smoke: synthetic `smoke-test` now requires `checks.liveSessionCompleted=true`, `checks.liveSessionReportRecoverable=true`, and `checks.liveSessionResumeExecutable=true`.
Additional executable live-session resume smoke: the PowerShell `live-session.ps1` test now runs the returned `resumeCommand -DryRun` and confirms it reaches `translation_planned`.
Additional UI smoke: `python -m gal_translator smoke-test --workspace .tmp-smoke-defaultsubtitle-ui --open-subtitle --subtitle-exit-after 1` returned `status=passed`, started a detached subtitle window, and auto-closed.

### Remaining Near-Term Work

1. Use `inspect-log` on a real Textractor log, then `capture-log` or `append-log`.
2. Run real `translate-all`, then `replay-log --event-log`, against that same captured log.
3. Start the actual subtitle window while a game is running and confirm runtime clipboard/Textractor matching.

## 2026-05-18

- 创建独立仓库：`C:\Programming\gal-translator`。
- 初始化 git 仓库。
- 写入项目 README。
- 写入仓库协作说明 `AGENTS.md`。
- 写入需求文档 `docs/requirements.md`。
- 写入规格文档 `docs/spec.md`。
- 写入恢复用计划文件 `task_plan.md`。
- 写入调研记录 `findings.md`。

## 下一步

在有 Galgame 样本的本地电脑上收集目标游戏目录结构，不需要解包。

建议先收集：

```powershell
Get-ChildItem "D:\Games\目标游戏" | Select-Object Name,Length,Mode
Get-ChildItem "D:\Games\目标游戏" -Recurse -File | Group-Object Extension | Sort-Object Count -Descending | Select-Object Count,Name
```

拿到文件列表后，决定第一批实现 Ren'Py、Kirikiri、NScripter 还是直接脚本导入。

## 2026-05-18 原型开发

- 确认当前电脑没有 Galgame 样本时仍可推进无样本核心模块。
- 选择 Python 3 作为第一批核心扫描/识别库实现，暂不引入第三方依赖。
- 新增 `gal_translator.scanner.GameScanner`，支持 exe 输入时以 exe 所在目录作为游戏根目录，并生成轻量扫描报告。
- 新增 `gal_translator.detector.EngineDetector`，基于 `.xp3/.rpa/.rpy/.rpyc/.ks/0.txt/nscript.dat/scenario/script` 等特征输出候选引擎。
- 新增 `python -m gal_translator scan <exe-or-dir>` CLI，输出 UTF-8 JSON 诊断报告。
- 新增 `tests/test_scanner_detector.py` 和 `tests/test_cli.py`，用临时目录 fixture 验证扫描、识别和 CLI 输出。
- 更新 `README.md` 记录扫描诊断命令和测试命令。

### 测试结果

```powershell
python -m unittest discover -v
```

结果：3 个测试通过。

### 下一步

- 实现一种直接脚本导入器，优先支持 `.ks/.rpy/.txt` fixture。
- 然后实现基础 ScriptParser，把直接脚本文本转成统一台词条目。

## 2026-05-18 Local Project Workspace

- Updated requirements/spec for a local-only tool model.
- Recorded the fixed initial language pair: Japanese to Simplified Chinese (`ja` -> `zh-Hans`).
- Added `TranslationProjectManager` to create isolated per-game project workspaces under a caller-provided workspace root.
- Added `ExtractorProfileRegistry` with a built-in `direct_script` profile for `.ks/.rpy/.txt/.json/.csv` scripts and `scenario/` or `script/` directories.
- Added `python -m gal_translator init <exe-or-dir> [--workspace <dir>]`.
- Noted that future AI-facing specs and plans can be written in English.

### Test Result

```powershell
python -m unittest discover -v
```

Result: 6 tests passed.

## 2026-05-18 Verifiable CLI Pipeline

- Added `DirectScriptImporter` for directly readable script files.
- Added `ScriptParser` and `StoryTextFilter` for fixture-based `.ks/.rpy/.txt` story extraction and system-text filtering.
- Added `python -m gal_translator import <exe-or-dir> [--workspace <dir>]`, which creates `story-entries.json` and `translation-state.json`.
- Added `TranslationProgressTracker` and `python -m gal_translator progress <project-root>`.
- Added `CodexBatchTranslator` core for pending batch selection, Galgame-style Japanese-to-Simplified-Chinese prompt generation, and JSON result application.
- Added `python -m gal_translator batch <project-root> --size <n>` and `python -m gal_translator apply-result <project-root> <result.json>`.
- Added `MatchIndex`, `RuntimeSubtitleService`, and `python -m gal_translator lookup <project-root> <text>` for translated-Chinese-only runtime output.
- Added `ClipboardRuntimeInput` abstraction with duplicate/empty text suppression; real OS clipboard provider remains a later integration point.
- Added JSON extractor profile loading via `ExtractorProfileRegistry.from_directories(...)`, so local engine/import knowledge can be accumulated outside the game folder.
- Added `CodexCliInvocation` for local verification of the `codex exec --ephemeral -m gpt-5.5 --output-schema ... -o ... -` command shape and output schema generation.

### Test Result

```powershell
python -m unittest discover -v
```

Result: 22 tests passed.

## Next Session Goal

Resume on the formal game PC with actual Galgame files.

Concrete next steps:

1. Pull or clone the repository.
2. Run `python -m unittest discover -v` to confirm the environment.
3. Run `python -m gal_translator scan <game-exe-or-dir>` on 1-2 real games.
4. Save the scan JSON and inspect candidate engines/profiles.
5. Try `python -m gal_translator import <game-exe-or-dir> --workspace <workspace-dir>` for directly readable scripts.
6. If the game uses packaged resources, create or adjust an extractor profile based only on the actual file structure and tool output.
7. Validate Codex CLI batch size and JSON stability with real story entries.
8. Validate Textractor/clipboard output against imported story text.

Current stopping point: all fixture-verifiable development is complete; real game validation is now required.

## 2026-05-18 Real Sample Scan: Select Oblige

- Ran the existing test suite after repository review: 22 tests passed before changes.
- Scanned `D:\private\otaku\game\galgame\selectoblige.exe`.
- Confirmed the real sample uses large `selectoblige.pfs` / `selectoblige.pfs.000` / `.001` / `.002` resource containers with `pf8` headers.
- Added lightweight read-only `PFS/pf8` archive diagnostics to `scan`; it samples archive headers/file-table-like data only and does not extract, decrypt, or modify game files.
- Real scan now reports `pf8_pfs_ast` as the highest-confidence candidate and shows visible archive script entries such as `script\01_01_01.ast`.
- Tightened the built-in `direct_script` profile so root `readme.txt` and patch notes no longer trigger direct import or get copied as scripts.
- Smoke-tested real sample import with a temporary workspace; result was `importedScriptCount: 0` and `progress.status: empty`, as expected until a real `.pfs/.ast` extractor/importer exists.
- Added `python -m gal_translator archive-list <pfs-or-game-path> [--scripts-only] [--limit N]` to list structured `PFS/pf8` entries without extraction.
- Verified `archive-list` on the real sample: `selectoblige.pfs` reports 14,301 structured entries and can list `.ast` script entries with offsets/sizes.
- Read two `.ast` payloads by file-table offset/size for diagnostics only; the bytes are not UTF-8/CP932/Shift-JIS plaintext, so extraction/import remains unsupported until a verified decoder/tool is available.
- Public references confirm PF8 is an Artemis archive format and includes XOR encryption. This project therefore keeps PF8 support diagnostic-only unless the user provides verified decoded scripts or an acceptable external workflow.
- Added `capture-log` to import Textractor/clipboard logs into the normal translation-state pipeline.
- Added Windows `watch-clipboard` runtime lookup CLI for local subtitle matching after translations are available.
- Added `prepare-codex` to write prompt/schema/command files for the next pending batch.
- Added guarded `run-codex` with dry-run preparation, stdout/stderr logs, timeout handling, command-not-found handling, and optional `--apply`.
- Added `subtitle-window`, a minimal local always-on-top Tkinter subtitle surface.
- Added `capture-log --append`, preserving existing translations while adding new captured entries.
- Added `doctor` environment diagnostics for Python, platform, Codex CLI, Tkinter, and workspace writability.
- Added `project-info` and scan `nextActions` for resumable workflow guidance.
- Added PowerShell launcher scripts under `scripts/`.
- Added `docs/release_checklist.md`.
- Added `retry-failed` to move failed translation entries back to pending.
- Added `append-log` to append captured text to an existing project without rescanning large game archives.
- Moved CLI implementation from `gal_translator.__main__` into `gal_translator.cli`; `__main__` is now a thin entry point.
- Added `workflow-fallback` to run doctor, scan, capture import, project info, and Codex batch preparation in one command.
- Added `docs/development_roadmap.md` and `docs/textractor_fallback_workflow.md`.
- Smoke-tested real sample fallback end to end: capture log -> apply translation JSON -> lookup returns translated Chinese only.

### Test Result

```powershell
python -m unittest discover -v
```

Result: 38 tests passed.

### Next Work

1. Add a real `pf8_pfs` extraction adapter only if a verified non-DRM tool or documented container parser is available.
2. Add an `.ast` parser once decoded sample scripts can be inspected.
3. Use `capture-log` / `watch-clipboard` as the supported fallback for unsupported packaged games.

## 2026-05-19 Phase 7 Hardening Start

- Started the workflow-hardening track from `docs/development_roadmap.md`.
- `CodexBatchTranslator.apply_result` now returns structured application counts and ids.
- Empty translations for known entries are marked `failed`.
- Missing expected ids are marked `failed` when the result is applied against a prepared batch.
- Unknown ids, duplicate ids, and invalid result items are reported without corrupting project state.
- `prepare-codex` now writes `batch.json` with the expected entry ids and includes `batchPath` / `entryIds` in the CLI payload.
- Default Codex batch logs now use per-run directories under `logs/codex-batches/` instead of overwriting one fixed `codex-batch` directory. Explicit `--out-dir` still writes to the requested path.
- `apply-result` now returns a JSON error payload for unreadable or invalid result JSON instead of a traceback.
- `run-codex --apply` reports `result_invalid` if Codex exits successfully but the result file cannot be read as valid JSON.

### Test Result

```powershell
python -m unittest discover -v
```

Result: 41 tests passed.

### Remaining Near-Term Work

1. Add structured JSON error payloads for other common CLI file/state failures.
2. Add a testable subtitle view-model layer before expanding Tkinter behavior.
3. Run the real Textractor/clipboard and subtitle-window smoke test on Windows with the target game.

## 2026-05-20 Phase 7 Hardening Continued

- Added structured JSON error payloads for missing `translation-state.json` in `progress`, `retry-failed`, `batch`, `prepare-codex`, `run-codex`, `apply-result`, `lookup`, `watch-clipboard`, and `subtitle-window`.
- Added structured JSON error payloads for unreadable Textractor/clipboard logs in `capture-log`, `append-log`, and `workflow-fallback`.
- Added structured JSON error handling for invalid `batch.json` beside a Codex result file.
- Added tests for missing translation state, missing capture log, and invalid batch metadata.
- Added `SubtitleViewModel` and `SubtitleViewState` so subtitle-window display behavior can be tested without opening Tkinter.
- Tkinter subtitle rendering now consumes the view-model state; unmatched runtime text remains quiet and does not display Japanese source text.

### Test Result

```powershell
python -m unittest discover -v
```

Result: 46 tests passed.

### Remaining Near-Term Work

1. Add more subtitle-window options only after they are backed by view-model tests.
2. Run the real Textractor/clipboard and subtitle-window smoke test on Windows with the target game.
3. Record any real-game runtime matching issues in `findings.md`.

## 2026-05-20 Subtitle Window Config Hardening

- Added test-backed subtitle-window configuration helpers for geometry, opacity clamping, and poll interval clamping.
- Added subtitle-window options: `--x`, `--y`, `--font-family`, `--background`, `--foreground`, and `--clear-after`.
- Added optional stale subtitle clearing in `SubtitleViewModel`; matched text can now clear after a configured number of seconds without displaying source Japanese.
- Added `subtitle-window --dry-run` to validate project state and window configuration without opening Tkinter.
- Updated `scripts/start-subtitle-window.ps1` to pass position, colors, font family, and clear-after options.
- Updated README, Textractor fallback workflow, and release checklist with the new subtitle-window examples.

### Test Result

```powershell
python -m unittest discover -v
```

Result: 50 tests passed.

### Additional Check

```powershell
python -m gal_translator subtitle-window --help
```

Result: command help shows the new subtitle-window options.

### Remaining Near-Term Work

1. Run real Windows Textractor/clipboard and subtitle-window smoke tests with the target game.
2. If the dry-run config is sufficient, capture one real translated line and verify `--clear-after` behavior manually.
3. Record any matching or window-placement issues in `findings.md`.

## 2026-05-20 Runtime Replay And Project Info

- Added `replay-log` to replay a Textractor/clipboard log through runtime matching without using the Windows clipboard.
- `replay-log` reports total, matched, unmatched, match percent, and per-entry runtime display events.
- `replay-log` omits source text by default and only includes it with `--include-source`.
- Added `replay-log --event-log <path>` to write replayed runtime events as JSONL.
- Updated README, Textractor fallback workflow, and release checklist with replay-log examples.
- Enhanced `project-info` with runtime event log status and latest default Codex batch metadata.

### Test Result

```powershell
python -m unittest discover -v
```

Result: 51 tests passed.

### Additional Check

```powershell
python -m gal_translator replay-log --help
```

Result: command help shows replay options including `--event-log`.

### Remaining Near-Term Work

1. Run real Windows Textractor/clipboard and subtitle-window smoke tests with the target game.
2. Use `replay-log --event-log` on a real captured log before opening the subtitle window.
3. Record real matching/window findings in `findings.md`.

## 2026-05-20 Capture Log Diagnostics

- Added capture log statistics to `ClipboardLogImporter`: raw line count, candidate line count, duplicate line count, non-Japanese line count, and imported entry count.
- `capture-log`, `append-log`, `workflow-fallback`, and `replay-log` now expose `captureStats`.
- Added `inspect-log` for checking Textractor/clipboard log quality without a game path or project workspace.
- `inspect-log` can preview imported entries and only includes source text when `--include-source` is passed.
- Updated README, Textractor fallback workflow, and release checklist to recommend `inspect-log` before capture import.

### Test Result

```powershell
python -m unittest discover -v
```

Result: 52 tests passed.

### Additional Check

```powershell
python -m gal_translator inspect-log --help
```

Result: command help shows inspect options.

### Remaining Near-Term Work

1. Use `inspect-log` on a real Textractor log and confirm importedEntryCount is useful.
2. Use `capture-log` or `append-log`, then `replay-log --event-log`, against that same real log.
3. Run `watch-clipboard` / `subtitle-window` manual smoke and record findings.

## 2026-05-24 Scoped LunaHook Bridge Closed Loop

- Added `python -m gal_translator luna-hook-bridge <game_pid> <source_log>` as a minimal LunaHook capture bridge that uses the local LunaTranslator `LunaHost64.dll` / `LunaHook64.dll` files directly instead of relying on the Luna GUI clipboard output path.
- The bridge inserts the verified Artemis hook codes:
  - `ENHVXN-24@195720:selectoblige.exe`
  - `HVXN-4C@1971E0:selectoblige.exe`
- Recovered from a clipboard-bridge noise incident by stopping the old clipboard bridge, removing accidental `lunahook:2` and `lunahook:4` entries from the real project, clearing the miss log, and restoring progress to `32978` total / `6950` translated / `26028` pending / `0` failed.
- Restarted a clean source-log session without clipboard bridge:
  - Report: `logs/source-log-session-20260524-215636-report.json`
  - Watcher pid: `31704`
  - Subtitle-window pid: `30304`
  - Clipboard bridge: disabled
- Verified the real game loop on `selectoblige.exe`:
  - Started from the title menu by clicking `START`.
  - LunaHook bridge captured `「これが最後の質問だ」` into the prepared source log.
  - Advanced the story by clicking the game's next-arrow.
  - LunaHook bridge captured `「ワン・ズ・ギフトの権利を不正に手に入れたと認めれば、法の下で裁いてやる」`.
  - The scoped watcher matched existing imported Artemis ids `script/01_01プロローグ_01.ast:16` and `script/01_01プロローグ_01.ast:35`, so project progress stayed at `6950/32978` and no global full-archive translation resumed.
  - The running subtitle window logged exact visible Chinese output: `「只要你承认是非法取得了 One's Gift 的权利，我就会依法审判你」`.
- Started a longer background bridge for continued play:
  - Bridge pid: `6252`
  - Stdout: `logs/lunahook-bridge-20260524-220805-stdout.json`
  - Stderr: `logs/lunahook-bridge-20260524-220805-stderr.txt`
- Evidence screenshot:
  - `C:\Users\deepd\AppData\Local\GalTranslator\real-session-selectoblige\selectoblige-scoped-lunahook-bridge-closed-loop.png`

Focused verification:

```powershell
python -m unittest tests.test_cli.CliTests.test_luna_hook_bridge_dry_run_plans_source_log_capture -v
```

Result: passed.

Full verification:

```powershell
python -m unittest discover -v
```

Result: 138 tests passed.

## 2026-05-24 Unified Source-Log Session With LunaHook Bridge

- Integrated LunaHook bridge startup into `scripts/source-log-session.ps1` with `-StartLunaHookBridge`.
- The session report now records `lunaHookBridge` with pid, game pid, command, stdout/stderr paths, and a live JSONL status log.
- `python -m gal_translator session-info <report>` and `source-log-status <project> <source-log> --session-report <report>` now surface `lunaHookBridge`, including whether the process is active and the last bridge status event.
- Restarted the real clean play loop through the unified session launcher:
  - Report: `logs/source-log-session-20260524-221940-report.json`
  - Source-log watcher pid: `43408`
  - Subtitle-window pid: `24088`
  - LunaHook bridge pid: `18108`
  - Clipboard bridge: disabled
- The bridge status log confirms startup, process connection, hook insertion, hook events, and captures:
  - Status log: `logs/source-log-session-20260524-221940-lunahook-status.jsonl`
  - Last captured line: `「もし認めないのなら……」`
- The scoped watcher processed the appended runtime line without global translation:
  - `lastProcessedLogEntryIds`: `script/01_01プロローグ_01.ast:16`, `script/01_01プロローグ_01.ast:35`, `script/01_01プロローグ_01.ast:55`
  - Project progress remains `32978` total / `6950` translated / `26028` pending / `0` failed.
- The running subtitle window logged exact visible Chinese for the new line:
  - `「如果你不承认的话……」`

Full verification after the unified-session integration:

```powershell
python -m unittest discover -v
```

Result: 138 tests passed.

## 2026-05-24 Paused Full Archive Source-Log Status

- Confirmed the persistent `selectoblige` Artemis project remains intentionally partial: `32978` total entries, `6950` translated, `26028` pending, `0` failed, `21.07%`.
- Continued the cost-control route: do not run global `translate-all` for the remaining archive unless explicitly choosing to spend tokens on all pending entries.
- Added `python -m gal_translator source-log-status <project_root> <source_log>` for the paused full-archive play loop.
- The new status command reports project progress, source-log importability, saved source-log watcher status, subtitle-window status, optional game process checks, and Hook/Textractor process checks.
- It always frames this mode as `paused_full_archive_scoped_source_log` and returns next actions for scoped `translate-log --only-new-log-entries`, not global archive translation.
- Real status check against the active session returned `status=watching_source_log`: game `selectoblige.exe` pid `4492`, LunaTranslator pid `13540`, source-log watcher pid `11584`, subtitle-window pid `43600`.
- Real source log remains `C:\Users\deepd\AppData\Local\GalTranslator\real-session-selectoblige\lunahook-source.txt`.
- Real source-log session report remains `C:\Users\deepd\AppData\Local\GalTranslator\real-session-selectoblige\artemis-script-project\projects\pfs-rs-extract-selectoblige-pfs-v0.2.5-b56875e0b374\logs\source-log-session-20260524-210406-report.json`.
- The watcher is currently idle on `log_unchanged`, with last processed event preserved from cycle `349`: `lastProcessedSessionStatus=translation_ready`, `lastProcessedScopedTranslatedCount=1`, and `lastProcessedLogEntryIds=["script/01_01プロローグ_01.ast:16"]`.
- Launched LunaTranslator GUI from `C:\Game\LunaTranslator_x64_win10_v10.12.3\LunaTranslator_x64_win10\LunaTranslator.exe`; the remaining manual/external step is ensuring LunaHook appends actual new runtime story text to the prepared source-log path.

### Test Result

```powershell
python -m unittest discover -v
```

Result: 137 tests passed.

## 2026-05-20 Translate All Automation

- Added `translate-all` to run repeated Codex batches until no pending entries remain.
- `translate-all --dry-run` reports planned batch count and writes the first batch files without executing Codex.
- Real `translate-all` execution applies each successful result immediately and records per-batch payloads.
- Codex command execution now resolves the binary with `shutil.which(...)` first, so Windows `codex.cmd` launchers on `PATH` work reliably.
- `project-info` now recommends `translate-all` when entries are pending.
- Added tests for dry-run planning and a fake Codex end-to-end completion path.
- `workflow-fallback` can now run `translate-all` after capture and optionally write replay JSONL events in the same command.
- `scripts/fallback-workflow.ps1` exposes `-TranslateAll`, `-TranslateDryRun`, timeout/max-batch options, and `-ReplayEventLog`.
- Added `scripts/translated-session.ps1` to run capture, full translation, replay event logging, and subtitle-window launch as one local play-session entry point.
- `subtitle-window` now writes runtime JSONL events by default, supports `--event-log`, `--no-log`, and source-inclusive diagnostic logs via `--include-source`.
- Lowered `pyproject.toml` `requires-python` to `>=3.10`, matching the verified local Python 3.10.6 environment.
- Rechecked real `selectoblige.exe` scan/archive-list after the workflow changes; PF8 diagnostics still report 220 visible `.ast` script entries.
- Smoke-tested `scripts/translated-session.ps1 -DryRun -NoSubtitle` with a temporary fake game/log workspace.
- Added `record-clipboard` to record changed Windows clipboard text into a UTF-8 log for later `inspect-log` / `capture-log`.
- `scripts/translated-session.ps1` can now run `-RecordClipboard` before import/translation, with duration/event limits and overwrite support.
- Fixed real Codex execution on Windows by sending prompt stdin with explicit UTF-8 encoding.
- Updated the Codex output schema for current strict structured-output requirements: object schemas now set `additionalProperties: false`, and nullable `notes` is required.
- Verified a real one-line Codex smoke path: `capture-log` -> `translate-all` -> Codex result -> apply -> final progress `ready`.
- Hardened repeated capture imports: if a new log reuses an existing line id for different text, append now derives a collision-safe id instead of dropping the new line.
- `scripts/translated-session.ps1` now supports `-LaunchGame` to start the game executable before clipboard recording and subtitle launch.
- Added first-class `play-session` CLI orchestration for launch, clipboard recording, capture import, translate-all, replay, and subtitle-window setup.
- `scripts/translated-session.ps1` now delegates to `python -m gal_translator play-session`.
- Added optional runtime miss logs for `watch-clipboard`, `subtitle-window`, and `play-session`; unmatched source text is written only when the user passes an explicit miss-log path.
- `scripts/start-subtitle-window.ps1` and `scripts/translated-session.ps1` expose miss-log options.
- Added `translate-log` for the incremental miss-log feedback loop: append a log to an existing project, translate pending entries, and optionally replay that log.
- Added `scripts/translate-miss-log.ps1` as the PowerShell wrapper for miss-log append/translate/replay rounds.
- Added top-level `sessionSummary` and `nextActions` to `play-session` and `translate-log` so one-command runs report whether to open subtitles, repair translation, or feed misses back into the loop.
- `play-session` now returns a reusable `subtitleWindow.command`, `sessionSummary.translateMissLogCommand`, and readiness-guarded `sessionSummary.watchMissLogCommand` when the matching options are configured.
- Added `play-session --subtitle-detach` plus script pass-through switches, so a translated session can start the subtitle window in a separate process and return JSON immediately with `subtitleWindow.detachedPid`, quick `detachedRunning` / `detachedReturnCode` status, and detached stdout/stderr log paths.
- Detached subtitle early exit now produces `sessionSummary.status=subtitle_exited` and nextActions pointing at detached stdout/stderr logs instead of being reported as a normal subtitle start.
- `play-session` now reports capture mode and warns through `replacedExistingState` / `nextActions` when a repeated run replaced an existing project state instead of appending.
- `watch-clipboard`, `subtitle-window`, and play-session subtitle windows now reload `translation-state.json` by default, so miss-log translations can appear without restarting the runtime display. `--no-reload`, `--subtitle-no-reload`, and script pass-through switches remain available for diagnostics.
- Added `translate-log --watch` and `scripts/translate-miss-log.ps1 -Watch` for a background miss-log translation loop while the subtitle window keeps collecting unmatched lines.
- Added `scripts/live-session.ps1`, a PowerShell supervisor that resolves the project root, starts the miss-log watcher in a hidden process, then runs `translated-session.ps1`.
- `scripts/live-session.ps1` now returns the exact miss watcher command, reports whether the watcher remains running after launcher exit, keeps the watcher alive automatically for detached subtitle sessions, and derives top-level `nextActions` from the nested session status instead of always telling the user to keep a subtitle window open.
- `scripts/live-session.ps1` now surfaces detached subtitle early-exit stderr/stdout paths in its own top-level `nextActions`, so the one-command wrapper does not hide window startup failures inside nested JSON.
- `scripts/live-session.ps1` no longer keeps the hidden miss watcher alive automatically when the detached subtitle window exits immediately; `-KeepMissWatcher` remains available when the watcher should be forced to persist.
- `scripts/live-session.ps1 -SubtitleSourceLog` now starts a second hidden watcher for the session capture log itself, using the original source name and readiness guard.
- Hardened `translate-log --watch` so it waits with an idle `translation_state_missing` event instead of exiting when a live session starts the watcher before capture import creates `translation-state.json`.
- Added `translate-log --watch-require-ready` and wired it into `scripts/live-session.ps1`, so the background miss watcher waits for the primary project to finish its main translation before processing old or changed miss logs.
- Added a project-level `logs/translation.lock` guard for `translate-all`, `translate-log`, and `apply-result`; watch mode now idles on `translation_locked` instead of racing the active writer.
- Added `clear-lock` for stale translation lock recovery, with Windows-safe process-id checks; `project-info` now exposes `translationLock` so interrupted runs can be diagnosed before resuming.
- Aligned `watch-clipboard` with subtitle-window runtime privacy: runtime events now omit raw clipboard source text by default and only include it with `--include-source`; explicit miss logs still capture unmatched source lines when requested.
- Runtime JSONL events from `watch-clipboard` and `subtitle-window` now include `missLogged`, making it clear whether an unmatched line was newly written to the miss log while still omitting raw source text by default.
- `play-session`, `scripts/translated-session.ps1`, and `scripts/live-session.ps1` now allow the capture log path to be omitted. The default is `workspace/captures/<game>-live-capture.txt`, reported as `sessionLogPath`, so launch/record/translate/subtitle runs need fewer manual path choices.
- `play-session --record-clipboard` and script `-RecordClipboard` now default to a finite 60-second recording phase; `--record-until-interrupted` / `-RecordUntilInterrupted` is the explicit opt-in for indefinite recording before translation starts.
- `play-session` now reports `sessionSummary.status=no_source_text` and skips subtitle startup when the final project has no source entries, while still allowing subtitle startup when an existing translated project has no new log lines in the current session.
- `play-session --session-report` and `scripts/translated-session.ps1 -SessionReport` now persist the final session JSON, and `scripts/live-session.ps1` writes a top-level `sessionReportPath` by default under the project logs directory.
- Added `session-info` to read saved play-session or live-session reports, recheck the current project state, and return concrete resume command arrays for translation, subtitle startup, miss-log feedback, and lock recovery.
- Added `resume-session` to execute the next recoverable step from a saved report: it continues pending `translate-all` work, can start the saved subtitle-window command with `--open-subtitle`, restart the saved miss-log watcher with `--start-miss-watcher`, and restart the saved session-log watcher with `--start-session-log-watcher`.
- Added `scripts/resume-session.ps1` as the PowerShell wrapper for saved report recovery, including subtitle, miss-watcher, and session-log watcher restore switches.
- Saved play-session and live-session outputs now include `resumeCommand`, so users can continue from `sessionReportPath` without reconstructing commands.

### Test Result

```powershell
python -m unittest discover -v
```

Result: 94 tests passed. Real Codex CLI smoke also reached final progress `ready` for a temporary one-line project.
Additional dry-run smoke: `play-session --translate-dry-run --subtitle-dry-run --subtitle-miss-log` returns `sessionSummary.status=translation_planned` with reusable subtitle, one-shot miss-log, and watch miss-log commands.
Additional detached subtitle smoke: `python -m gal_translator play-session --help` exposes `--subtitle-detach`, and the detached process helper is covered by unit tests including detached stdout/stderr log payloads and quick process health fields.
Additional script smoke: `scripts/translate-miss-log.ps1 -DryRun` returns `sessionSummary.status=translation_planned` and appends one miss-log entry in a temporary project.
Additional reload smoke: `subtitle-window --dry-run` reports `reloadEnabled=true` for a temporary captured project.
Additional watch smoke: `translate-log --dry-run --watch --watch-max-cycles 1` processes one changed miss log and emits a JSONL `processed` cycle.
Additional script watch smoke: `scripts/translate-miss-log.ps1 -DryRun -Watch -WatchMaxCycles 1` returns a JSONL `processed` cycle with one appended miss entry.
Additional live-session smoke: `scripts/live-session.ps1 -DryRun -NoSubtitle -SubtitleSourceLog -WatchMaxCycles 1` creates a project, starts miss-log and session-log watchers, and returns a completed session summary with watcher command/log paths, post-exit running state, and dry-run-specific nextActions.
Additional live-session watcher smoke: `scripts/live-session.ps1 -DryRun -NoSubtitle -WatchMaxCycles 2` writes watcher JSONL events instead of exiting before the translation state exists.
Additional live-session readiness smoke: `scripts/live-session.ps1 -DryRun -NoSubtitle -SubtitleMissLog <existing misses> -WatchMaxCycles 5` makes the watcher emit idle `translation_not_ready` instead of processing misses before the primary translation is complete.
Additional live-session detached-exit smoke: a mocked `translated-session.ps1` returning `sessionSummary.status=subtitle_exited` confirms top-level stderr/stdout guidance and that the hidden watcher is not marked to keep running.
Additional default-log smoke: `play-session` without `log_file` and `scripts/live-session.ps1` without `-LogPath` use `workspace/captures/<game>-live-capture.txt`; direct `scripts/translated-session.ps1` without `-LogPath` also dry-runs successfully.
Additional record-duration smoke: `python -m gal_translator play-session --help` shows `--record-until-interrupted`, and a unit test confirms the default play-session recording phase is finite.
Additional no-source smoke: empty/non-Japanese logs produce `sessionSummary.status=no_source_text` with no subtitle payload; existing translated projects with no new log lines still return subtitle-ready state.
Additional runtime event smoke: subtitle-window and watch-clipboard event payload tests cover `missLogged` for default-private and source-inclusive diagnostic modes.
Additional session-report smoke: `play-session --session-report` writes a recovery JSON file, and `scripts/live-session.ps1` returns a default `sessionReportPath` whose file contains the nested session summary.
Additional session-info smoke: saved play-session reports return `translateAllCommand` for pending dry-run projects, and saved live-session reports for ready projects return subtitle and miss-watch resume commands.
Additional resume-session smoke: a saved pending report runs fake Codex through `translate-all` to project `ready`, and a saved ready report plans subtitle plus miss-watcher/session-log watcher startup with `--open-subtitle --start-miss-watcher --start-session-log-watcher --dry-run`.
Additional script recovery smoke: `scripts/resume-session.ps1 -DryRun -OpenSubtitle -StartMissWatcher -StartSessionLogWatcher` passes through to the CLI and returns planned subtitle/miss-watcher/session-log watcher payloads.
Additional resume-command smoke: `play-session --session-report` and `scripts/live-session.ps1` now return recovery command arrays tied to the saved report path.
Additional lock smoke: `scripts/live-session.ps1 -DryRun -NoSubtitle -WatchMaxCycles 2` completes without leaving `logs/translation.lock` behind.
Additional lock recovery smoke: `python -m gal_translator clear-lock --help` confirms the stale-lock recovery command is wired.
Additional watch-clipboard smoke: `python -m gal_translator watch-clipboard --help` confirms the source-inclusive diagnostic flag is wired.

### Remaining Near-Term Work

1. Use `inspect-log` on a real Textractor log, then `capture-log` or `append-log`.
2. Run `translate-all --dry-run`, then `translate-all`, then `replay-log --event-log`.
3. Start `subtitle-window` after at least one translated line is available.

## 2026-05-21 Recovery Log Tail Diagnostics

- Added bounded `tailLines` arrays to the shared log summary payload used by failed Codex batch logs and saved watcher stdout/stderr diagnostics.
- Kept existing `lastLine` and JSONL `lastEvent` fields intact, so existing recovery consumers remain compatible while `project-info`, `session-info`, `translate-all`, and live watcher payloads expose more context directly.
- Extended CLI tests so failed Codex stdout/stderr and saved miss/session-log watcher JSONL outputs verify both the final event and the short diagnostic tail.

### Test Result

```powershell
python -m unittest discover -v
```

Result: 112 tests passed.

Additional smoke:

```powershell
python -m gal_translator smoke-test --workspace .tmp-smoke-taildiagnostics
```

Result: `status=passed` with all smoke `checks` true.

### Remaining Near-Term Work

1. Use `inspect-log` on a real Textractor log, then `capture-log` or `append-log`.
2. Run `translate-all --dry-run`, then `translate-all`, then `replay-log --event-log`.
3. Start `subtitle-window` after at least one translated line is available.

## 2026-05-20 Project Info Recovery Hardening

- Hardened `project-info` so it remains usable as a recovery command when auxiliary project JSON is malformed.
- `project-info` now reports `diagnostics` for invalid `project.json`, `story-entries.json`, `translation-state.json`, and latest Codex `batch.json` instead of emitting a Python traceback.
- Latest Codex batch metadata now includes `hasBatchJson` and `batchJsonValid`.
- Corrupt `translation-state.json` produces a repair-oriented `nextActions` message while preserving the rest of the project-info payload.

### Test Result

```powershell
python -m unittest discover -v
```

Result: 54 tests passed.

### Remaining Near-Term Work

1. Use `inspect-log` on a real Textractor log and confirm importedEntryCount is useful.
2. Use `capture-log` or `append-log`, then `replay-log --event-log`, against that same real log.
3. Run `watch-clipboard` / `subtitle-window` manual smoke and record findings.

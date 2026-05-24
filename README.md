# Gal Translator

独立的 Galgame 文本批量翻译与外置双语字幕项目。

本仓库只放 Gal 翻译相关文件，不复用小说/EPUB 翻译项目的代码。小说翻译项目可以作为架构参考，但本项目的目标、输入源、展示方式和兼容策略独立设计。

## 当前方向

- 用户选择 Galgame 的 `exe` 或游戏目录。
- 程序扫描 exe 所在目录，自动识别常见资源包和脚本文件。
- 能预提取脚本时，使用 Codex CLI / GPT-5.5 离线批量翻译。
- 游玩时通过 Textractor/剪贴板拿到当前原文。
- 本地数据库按原文匹配译文，外置窗口即时显示双语。
- 实时阶段默认不调用 Codex，避免读一句等一句。

## MVP 边界

第一版优先验证完整链路：

1. 游戏目录扫描与诊断报告。
2. 常见脚本/资源形态识别。
3. Codex CLI 批量翻译后端。
4. 原文到译文的本地匹配索引。
5. Textractor/剪贴板输入。
6. 外置双语字幕窗口。

暂不承诺：

- 100% 自动解包所有 Galgame。
- 游戏内文本框回写。
- 自研进程 hook。
- OCR 作为主输入源。
- 对加密封包做通用破解。

## 参考游戏类型

以常见日式 Windows 硬盘版 Galgame 为参考对象，例如 9-nine- 系列、柚子社作品这类“用户只看到 exe 和若干资源包”的使用场景。

注意：具体引擎和资源格式必须以实际目录文件特征为准，不能仅凭作品名假设。

## 当前可运行功能

### 扫描诊断

```powershell
python -m gal_translator scan "D:\Games\目标游戏\game.exe"
python -m gal_translator scan "D:\Games\目标游戏"
```

输出为 UTF-8 JSON，包含：

- 输入路径和识别出的游戏根目录。
- 文件数量、目录列表、扩展名计数。
- 轻量文件清单。
- 根据 `.xp3/.rpa/.rpy/.rpyc/.ks/0.txt/nscript.dat/scenario/script` 等特征得到的候选引擎。

### 创建翻译工程

```powershell
python -m gal_translator init "D:\Games\目标游戏\game.exe"
python -m gal_translator init "D:\Games\目标游戏" --workspace "$env:LOCALAPPDATA\GalTranslator"
```

The project workspace is separate from the game folder. It stores scan reports, extracted files, scripts, logs, and future translation state under the workspace directory. The current translation direction is Japanese to Simplified Chinese (`ja` -> `zh-Hans`).

### Direct Script Import And Translation State

```powershell
python -m gal_translator doctor
python -m gal_translator import "D:\Games\目标游戏" --workspace "$env:LOCALAPPDATA\GalTranslator"
python -m gal_translator session-info ".\live-session-report.json"
python -m gal_translator resume-session ".\live-session-report.json" --open-subtitle --start-miss-watcher --start-session-log-watcher --retry-failed
.\scripts\resume-session.ps1 -SessionReport ".\live-session-report.json" -OpenSubtitle -StartMissWatcher -StartSessionLogWatcher -RetryFailed
python -m gal_translator project-info "$env:LOCALAPPDATA\GalTranslator\projects\<project-id>"
python -m gal_translator progress "$env:LOCALAPPDATA\GalTranslator\projects\<project-id>"
python -m gal_translator retry-failed "$env:LOCALAPPDATA\GalTranslator\projects\<project-id>"
python -m gal_translator batch "$env:LOCALAPPDATA\GalTranslator\projects\<project-id>" --size 40
python -m gal_translator prepare-codex "$env:LOCALAPPDATA\GalTranslator\projects\<project-id>" --size 40
python -m gal_translator translate-all "$env:LOCALAPPDATA\GalTranslator\projects\<project-id>" --size 40 --dry-run
python -m gal_translator translate-all "$env:LOCALAPPDATA\GalTranslator\projects\<project-id>" --size 40 --timeout 600
python -m gal_translator apply-result "$env:LOCALAPPDATA\GalTranslator\projects\<project-id>" ".\result.json"
python -m gal_translator lookup "$env:LOCALAPPDATA\GalTranslator\projects\<project-id>" "おはよう、先輩"
python -m gal_translator replay-log "$env:LOCALAPPDATA\GalTranslator\projects\<project-id>" ".\textractor-log.txt" --source-name textractor --event-log ".\replay-events.jsonl"
python -m gal_translator translate-log "$env:LOCALAPPDATA\GalTranslator\projects\<project-id>" ".\misses.txt" --only-new-log-entries --replay-event-log ".\miss-replay.jsonl"
python -m gal_translator watch-clipboard "$env:LOCALAPPDATA\GalTranslator\projects\<project-id>"
python -m gal_translator subtitle-window "$env:LOCALAPPDATA\GalTranslator\projects\<project-id>"
python -m gal_translator subtitle-window "$env:LOCALAPPDATA\GalTranslator\projects\<project-id>" --dry-run --x 120 --y 760 --clear-after 4 --preview-source "おはよう、先輩"
python -m gal_translator subtitle-window "$env:LOCALAPPDATA\GalTranslator\projects\<project-id>" --source-log ".\textractor-log.txt" --source-log-name textractor
python -m gal_translator subtitle-window "$env:LOCALAPPDATA\GalTranslator\projects\<project-id>" --x 120 --y 760 --width 1200 --height 120 --font-size 30 --opacity 0.82 --clear-after 4 --event-log ".\runtime-events.jsonl" --miss-log ".\misses.txt"
```

The current CLI flow can import directly readable scripts (`.ks/.rpy/.txt/.json/.csv`), extract likely story text, initialize translation progress, print a Codex-ready prompt, apply a strict JSON result, and look up Chinese-only runtime display text.

Before using a real game/log, run the local synthetic smoke test:

```powershell
python -m gal_translator smoke-test --workspace "$env:LOCALAPPDATA\GalTranslatorSmoke"
python -m gal_translator smoke-test --workspace "$env:LOCALAPPDATA\GalTranslatorSmoke" --open-subtitle --subtitle-exit-after 8
```

`smoke-test` creates a disposable fake game and Textractor-style log, runs capture import, fake Codex batch translation, replay matching, subtitle-window dry-run, saved session report inspection, resume-session dry-run, and a source-log feedback pass that appends a new line, translates it with `translate-log --watch`, then verifies `lookup` can match it. It also runs a bounded Python `live-session` dry-run and verifies that the saved live-session report can be inspected with `session-info` and resumed with the returned `resumeCommand --dry-run`; a separate retry-recovery smoke creates a failed entry and proves `resume-session --retry-failed` can reset it, translate it, and return to subtitle-ready state. It does not need a real game, Textractor, or the real Codex CLI, so it is the fastest check that the local end-to-end translator path is still wired. Add `--open-subtitle` when you want the same synthetic workflow to start the subtitle window as a detached process with a translated preview line visible; add `--subtitle-exit-after <seconds>` for an auto-closing UI smoke that also verifies real `subtitle-window --source-log` runs, including a live tailing case where the window sees a new line as unmatched and then refreshes it to a visible exact match after `translate-log --watch` updates translations.

For packaged games where script extraction is not available, import a Textractor or clipboard log:

```powershell
python -m gal_translator inspect-log ".\textractor-log.txt" --source-name textractor --include-source
python -m gal_translator record-clipboard ".\textractor-log.txt" --duration 60 --overwrite
python -m gal_translator capture-log "D:\Games\Game\game.exe" ".\textractor-log.txt" --workspace "$env:LOCALAPPDATA\GalTranslator" --source-name textractor
python -m gal_translator append-log "$env:LOCALAPPDATA\GalTranslator\projects\<project-id>" ".\textractor-log.txt" --source-name textractor
python -m gal_translator workflow-fallback "D:\Games\Game\game.exe" ".\textractor-log.txt" --workspace "$env:LOCALAPPDATA\GalTranslator"
python -m gal_translator workflow-fallback "D:\Games\Game\game.exe" ".\textractor-log.txt" --workspace "$env:LOCALAPPDATA\GalTranslator" --translate-all --translate-timeout 600 --replay-event-log ".\replay-events.jsonl"
python -m gal_translator play-session "D:\Games\Game\game.exe" ".\textractor-log.txt" --workspace "$env:LOCALAPPDATA\GalTranslator" --launch-game --record-clipboard --record-duration 60 --overwrite-log --replay-event-log ".\replay-events.jsonl" --subtitle-miss-log ".\misses.txt" --subtitle-preview-first-match --subtitle-source-log
python -m gal_translator live-session "D:\Games\Game\game.exe" ".\textractor-log.txt" --workspace "$env:LOCALAPPDATA\GalTranslator" --subtitle-detach --subtitle-miss-log ".\misses.txt" --subtitle-source-log --subtitle-preview-first-match
```

This initializes the same translation-state pipeline from captured Japanese lines.

`prepare-codex` writes `prompt.txt`, `schema.json`, `batch.json`, `result.json`, and `command.json` paths for the next pending batch, so the generated Codex command can be reviewed before running. `batch.json` records the expected entry ids, allowing `apply-result` to mark missing or empty Codex translations as failed for later retry.

`translate-all` is the normal full-translation command after import/capture. It repeats Codex batches until no pending entries remain, applies each result immediately, and stores every batch under `logs/codex-batches/`. Use `--dry-run` first to see the planned batch count and write the first batch files without running Codex. Add `--retry-failed` when you want the same run to reset failed entries back to pending before continuing; `play-session` and `live-session` expose the same behavior as `--translate-retry-failed`.
Translation-state writes are guarded by `logs/translation.lock`, so `translate-all`, `translate-log`, and manual `apply-result` do not update the same project concurrently. If a command reports `translation_locked`, run `project-info` to inspect `translationLock`; then use `clear-lock` only after confirming no Gal Translator translation process is still running. `clear-lock --force` is reserved for a lock that still points at a live process id but is known to be stale.

`play-session` is the first-class one-command path for actual play: it can launch the game, record clipboard text, import the log, run all pending Codex batches, replay the captured log, and open the subtitle window. The `log_file` argument is optional; when omitted, the session uses `workspace/captures/<game>-live-capture.txt` and reports the resolved path as `sessionLogPath`. Clipboard recording in `play-session` defaults to a finite 60 seconds so the workflow can proceed to translation and subtitles; use `--record-duration`, `--record-max-events`, or explicit `--record-until-interrupted` to change that. Add `--session-report <path>` to save the final JSON payload for later recovery, even if the terminal output is closed. Use `--subtitle-preview-first-match` to seed the subtitle window with the first translated line from the captured log, or `--subtitle-preview-source "<source line>"` for an explicit startup preview. Add `--subtitle-source-log` when Textractor writes to the same log file during play and you want the subtitle window to follow new log lines directly instead of polling the clipboard. Use `--subtitle-detach` when the command should start the subtitle window in a separate process, return JSON immediately, and include `subtitleWindow.detachedPid`, quick `detachedRunning` / `detachedReturnCode` status, plus detached stdout/stderr log paths.
Its top-level `sessionSummary.status` and `nextActions` summarize whether the session is ready for subtitle display, still needs translation repair, captured no Japanese source text, whether a detached subtitle process exited immediately, or should feed misses back through `translate-log`. The subtitle payload also includes a `command` array for reopening the same subtitle window config. `sessionSummary.translateSessionLogCommand` and `sessionSummary.watchSessionLogCommand` can translate log-referenced Textractor/session-log lines while `subtitle-window --source-log` follows that same file. When a miss log is configured, `sessionSummary.translateMissLogCommand` and `sessionSummary.watchMissLogCommand` provide one-shot and background watcher commands for translating log-referenced unmatched lines. When a report is saved, `resumeCommand` is also returned for continuing from that report.
On repeated sessions, pass `--append` if the new log should extend the existing project instead of replacing the current captured state; `sessionSummary.replacedExistingState` warns when an existing state was overwritten.

`live-session` is the Python CLI supervisor for the same real-play workflow. It starts readiness-guarded background `translate-log --watch` processes for the miss log and, when `--subtitle-source-log` is used, the session log itself; then it runs `play-session`, writes a live-session report, and returns `resumeCommand` for restoring translation, subtitle display, and watcher processes later. The returned `missWatcher` and `sessionLogWatcher` payloads include stdout/stderr tails plus `statusSummary`, and `nextActions` names common watcher wait states such as a missing watched log, an active translation lock, or a watcher waiting for the main translation to finish. This is the preferred non-PowerShell one-command entry point when you want the subtitle window open while appended Textractor/source-log lines keep getting translated in the background.

Use `session-info <session-report.json>` to recover after a launcher window closes. It reads `play-session --session-report`, Python `live-session`, or `live-session.ps1` reports, rechecks the current project state, inspects the saved session log as `sessionLogInspection`, rechecks saved miss/session-log watcher processes when pids are available, reads watcher log tails, summarizes them as `missWatcher.statusSummary` / `sessionLogWatcher.statusSummary`, and returns command arrays such as `resumeSessionCommand`, `appendSessionLogCommand`, `translateAllCommand`, `subtitleWindowCommand`, `translateMissLogCommand`, `watchMissLogCommand`, and `watchSessionLogCommand`. When a subtitle window can be opened from either a saved or default command, `resumeSessionCommand` includes `--open-subtitle`; when saved miss/session log paths are available, older reports can also get synthesized watcher commands and matching resume flags.
Use `resume-session <session-report.json>` when you want the tool to take the next step automatically: it can append the saved session log when the project is empty but the report log contains importable Japanese lines, continues pending `translate-all` work, resets failed entries with `--retry-failed` before translating again, or with `--open-subtitle` starts the saved subtitle-window command. If an older report has no saved subtitle command, recovery builds a default subtitle-window command for the translated project and follows the saved session log when it exists. Add `--start-miss-watcher` to restore the saved or synthesized background miss-log translator alongside the subtitle window. Add `--start-session-log-watcher` to restore the saved or synthesized session-log translator used by `subtitle-window --source-log`. Add `--dry-run` to inspect the action without executing it.

Capture commands include `captureStats` with raw line count, candidate line count, skipped consecutive duplicates, skipped non-Japanese lines, imported entry count, unique imported source count, and repeated source count. `inspect-log` also returns a `status` such as `ready_to_import`, `ready_with_repeated_sources`, or `no_japanese_text`, plus `nextActions` for hook/encoding repair. Project import keeps one translation entry per unique captured source text, so repeated Textractor lines do not keep adding duplicate pending translations when a log grows; use `uniqueImportedEntryCount` as the expected pending-entry count for a repeated real log.

`project-info` is also the recovery-oriented status command. It reports malformed project metadata in a `diagnostics` array instead of crashing, so it is safe to run when a project workspace is partially written or a batch metadata file is damaged. Its `latestCodexBatch` payload includes stdout/stderr tails plus command/result JSON summaries, which is the fastest way to see why the last `translate-all` batch failed.

`replay-log` replays a Textractor/clipboard log against the translated project state without touching the Windows clipboard. Use it before `watch-clipboard` or `subtitle-window` to check match coverage and verify that runtime output remains Chinese-only. Add `--event-log` to write JSONL runtime events for review.

`watch-clipboard` and `subtitle-window` write runtime JSONL events by default to `logs/runtime-events.jsonl`; pass `--event-log` for a custom path or `--no-log` to disable this. Raw source text is not written unless `--include-source` is set. Runtime events include `missLogged`, so you can tell whether an unmatched line was newly written to the configured miss log without exposing the source text. Both runtime modes reload `translation-state.json` by default, so translations applied by a miss-log round can become visible without restarting the runtime display; `subtitle-window` also rechecks the last unmatched source during idle polls, so a line that just entered the miss-log feedback loop can appear after the background translation is applied. Pass `--no-reload` only for diagnostics. Use `subtitle-window --dry-run --preview-source "<source line>"` to verify what a captured line will display before opening the real window; without `--dry-run`, the same option seeds the window with that translated line before polling takes over. Use `--source-log <path>` when the runtime source should be appended Textractor/clipboard log lines instead of the OS clipboard; by default it tails only new imported Japanese lines, while `--source-log-from-start` replays existing clean log lines. Use `subtitle-window --save-config <json>` after tuning position/style, then reuse it with `--config <json>`; `play-session` and `live-session` use the same file through `--subtitle-config` / `--subtitle-save-config`. Explicit window CLI options override the config file. Use `--exit-after <seconds>` for auto-closing UI smoke runs.

Use `--miss-log` / `--subtitle-miss-log` to explicitly record unmatched runtime source text into a plain text log. That log can be fed back through scoped `translate-log --only-new-log-entries` for incremental coverage without translating the full global pending queue.

`translate-log --only-new-log-entries` is the shortcut for that feedback loop on an existing project: append or inspect a captured/miss log, translate only entries referenced by that log, and optionally replay that same log. This includes existing imported pending script entries whose source text appears in the log, so pre-extracted Artemis projects can translate just the line encountered during play.
It also returns `sessionSummary` / `nextActions`, so a miss-log round trip can immediately tell you whether to resume `play-session` or keep collecting untranslated lines.
Add `--watch` to keep a background miss-log translator running while the subtitle window writes unmatched lines; each changed-log cycle emits one JSONL result, and the runtime display reloads the updated translations automatically. Omit `--only-new-log-entries` only when intentionally continuing every global pending entry in the project.

See `docs/textractor_fallback_workflow.md` for the full fallback workflow used by packaged Artemis/PF8 samples.

Launcher scripts are available under `scripts/`:

`live-session.ps1` is the highest-level local launcher: it starts the miss-log watcher in a hidden PowerShell process, runs `translated-session.ps1`, and returns a JSON summary with watcher commands plus log paths. With `-SubtitleSourceLog`, it also starts a readiness-guarded session-log watcher so newly appended Textractor/session-log lines can be translated directly while the subtitle window follows the same file. If `-LogPath` is omitted, it uses `Workspace\captures\<game>-live-capture.txt`, which makes `-LaunchGame -RecordClipboard` usable without preselecting a log filename. It writes the top-level summary to `sessionReportPath` by default under the project `logs` directory; pass `-SessionReport` to choose a specific file. It also returns `resumeCommand`, a PowerShell command array for `resume-session.ps1` with subtitle, miss-watcher, and source-log watcher restore flags when those commands are available. Its watchers wait for the primary project translation to become ready before processing log changes, so old miss/session logs do not race the main `translate-all` run. The top-level `nextActions` mirror the nested session status, so dry runs, no-subtitle runs, detached subtitle early exits, and active subtitle sessions produce different follow-up guidance. `missWatcher.running` and `sessionLogWatcher.running` report whether each watcher will remain alive after the launcher exits; `-SubtitleDetach` keeps them alive automatically only when the detached subtitle session starts successfully, and `-KeepMissWatcher` is available for other detached watcher cases.

`source-log-session.ps1` is the cost-controlled launcher for an already imported script project. It starts a scoped `translate-log --watch --only-new-log-entries` process for the live Hook/Textractor source log and opens `subtitle-window --source-log` against the same file. Unlike `live-session.ps1`, it does not use `--watch-require-ready`, so it works when full archive translation is intentionally paused and the project still has many pending entries. Default batch size and max batches are `1`, so the watcher translates only the line currently encountered during play unless you override those values. On non-dry-run startup it creates the source log parent directory and an empty source log if needed, so Hook/logging tools have a stable file to append. If the Hook tool can only copy text to the clipboard, add `-StartClipboardBridge`; the launcher starts `record-clipboard` in the background and appends changed clipboard text into the same source log. It also writes a default `sessionReportPath` under project `logs` with `restartCommand`, watcher/subtitle/clipboard commands, pids, and log paths. `session-info <sessionReportPath>` recognizes this report as `source-log-session` and returns `sourceLogSessionCommand` for restoring the full scoped watcher plus subtitle window without switching back to global full translation.

The desktop shell exposes the same route under Play Output as `source-log-session`; `python -m gal_translator desktop --dry-run` includes a `sourceLogSession` command template with the same scoped defaults.

```powershell
.\scripts\gal-translator.ps1 doctor
.\scripts\fallback-workflow.ps1 -GamePath "D:\Games\目标游戏\game.exe" -LogPath ".\textractor-log.txt"
.\scripts\fallback-workflow.ps1 -GamePath "D:\Games\目标游戏\game.exe" -LogPath ".\textractor-log.txt" -TranslateAll -ReplayEventLog ".\replay-events.jsonl"
.\scripts\translated-session.ps1 -GamePath "D:\Games\目标游戏\game.exe" -LogPath ".\textractor-log.txt" -ReplayEventLog ".\replay-events.jsonl" -SubtitleMissLog ".\misses.txt" -SubtitlePreviewFirstMatch
.\scripts\translated-session.ps1 -GamePath "D:\Games\目标游戏\game.exe" -LogPath ".\textractor-log.txt" -RecordClipboard -RecordDuration 60 -OverwriteLog -ReplayEventLog ".\replay-events.jsonl" -SubtitleMissLog ".\misses.txt"
.\scripts\translated-session.ps1 -GamePath "D:\Games\目标游戏\game.exe" -LogPath ".\textractor-log.txt" -LaunchGame -RecordClipboard -RecordDuration 60 -OverwriteLog -ReplayEventLog ".\replay-events.jsonl" -SubtitleMissLog ".\misses.txt"
.\scripts\translated-session.ps1 -GamePath "D:\Games\目标游戏\game.exe" -LogPath ".\textractor-log.txt" -SubtitleMissLog ".\misses.txt" -SubtitleDetach
.\scripts\live-session.ps1 -GamePath "D:\Games\目标游戏\game.exe" -LogPath ".\textractor-log.txt" -LaunchGame -RecordClipboard -RecordDuration 60 -OverwriteLog -ReplayEventLog ".\replay-events.jsonl" -SubtitleMissLog ".\misses.txt" -SubtitlePreviewFirstMatch -SubtitleSourceLog
.\scripts\source-log-session.ps1 -ProjectRoot "$env:LOCALAPPDATA\GalTranslator\projects\<project-id>" -SourceLog ".\lunahook-source.txt" -SourceName lunahook -DryRun
.\scripts\source-log-session.ps1 -ProjectRoot "$env:LOCALAPPDATA\GalTranslator\projects\<project-id>" -SourceLog ".\lunahook-source.txt" -SourceName lunahook
.\scripts\source-log-session.ps1 -ProjectRoot "$env:LOCALAPPDATA\GalTranslator\projects\<project-id>" -SourceLog ".\lunahook-source.txt" -SourceName lunahook -StartClipboardBridge
python -m gal_translator project-info "$env:LOCALAPPDATA\GalTranslator\projects\<project-id>"
python -m gal_translator clear-lock "$env:LOCALAPPDATA\GalTranslator\projects\<project-id>"
.\scripts\translate-miss-log.ps1 -ProjectRoot "$env:LOCALAPPDATA\GalTranslator\projects\<project-id>" -LogPath ".\misses.txt" -ReplayEventLog ".\miss-replay.jsonl"
.\scripts\translate-miss-log.ps1 -ProjectRoot "$env:LOCALAPPDATA\GalTranslator\projects\<project-id>" -LogPath ".\misses.txt" -Watch
.\scripts\start-subtitle-window.ps1 -ProjectRoot "$env:LOCALAPPDATA\GalTranslator\projects\<project-id>"
.\scripts\start-subtitle-window.ps1 -ProjectRoot "$env:LOCALAPPDATA\GalTranslator\projects\<project-id>" -X 120 -Y 760 -ClearAfter 4 -ExitAfter 8 -MissLog ".\misses.txt"
.\scripts\start-subtitle-window.ps1 -ProjectRoot "$env:LOCALAPPDATA\GalTranslator\projects\<project-id>" -SourceLog ".\textractor-log.txt" -SourceLogName textractor
.\scripts\start-subtitle-window.ps1 -ProjectRoot "$env:LOCALAPPDATA\GalTranslator\projects\<project-id>" -Config ".\subtitle-window.json"
.\scripts\start-subtitle-window.ps1 -ProjectRoot "$env:LOCALAPPDATA\GalTranslator\projects\<project-id>" -NoReload
```

### Archive Listing Diagnostics

Packaged games can be inspected without modifying or extracting game files:

```powershell
python -m gal_translator archive-list "D:\Games\Game\game.exe" --scripts-only --limit 50
python -m gal_translator archive-list "D:\Games\Game\data.pfs" --scripts-only --limit 50
```

The current `PFS/pf8` support is diagnostic-only. It parses visible file-table entries such as `.ast` script names, offsets, and sizes, but it does not decode, decrypt, or unpack resource contents.

### Extractor Profiles

User-specific extractor profiles can be stored as JSON files under a workspace-side `extractor-profiles` directory. Example:

```json
{
  "profileId": "custom_old_gal",
  "label": "Custom old Gal profile",
  "sourceLang": "ja",
  "targetLang": "zh-Hans",
  "extensions": [".dat"],
  "directories": ["scenario"],
  "scriptGlobs": ["scenario/**/*.txt"],
  "encoding": "cp932"
}
```

Profiles are local configuration. They are intended to accumulate engine/package handling knowledge without modifying game folders.

### 运行测试

```powershell
python -m unittest discover -v
```

from __future__ import annotations

import argparse
import csv
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import io
import json
import os
import shutil
from pathlib import Path
import subprocess
import sys
import time
from typing import Any

from gal_translator.archives import ArchiveInspector, is_script_entry
from gal_translator.capture import ClipboardLogImporter
from gal_translator.clipboard import ClipboardRuntimeInput, ClipboardTextRecorder, TextLogRuntimeInput, WindowsClipboardProvider
from gal_translator.desktop import DesktopShellConfig, desktop_shell_payload, launch_desktop_shell
from gal_translator.detector import EngineDetector, EngineCandidate
from gal_translator.importer import ArtemisAstImporter, ArtemisAstParser, DirectScriptImporter, ImportedScript
from gal_translator.lunahook_bridge import LunaHookBridge, LunaHookBridgeConfig
from gal_translator.matching import MatchIndex, TranslationRecord
from gal_translator.parser import ScriptEntry, ScriptParser
from gal_translator.profiles import ExtractorProfile, ExtractorProfileRegistry
from gal_translator.progress import TranslationProgressTracker, TranslationSummary
from gal_translator.project import TranslationProject, TranslationProjectManager
from gal_translator.runtime import ReloadableRuntimeSubtitleService, RuntimeSubtitleService
from gal_translator.scanner import GameScanner, ScanReport, ScannedFile
from gal_translator.subtitle_window import SubtitleWindow, SubtitleWindowConfig
from gal_translator.story_filter import StoryTextFilter
from gal_translator.translator import CodexBatchTranslator, CodexCliInvocation


_DETACHED_PROCESSES: list[subprocess.Popen[Any]] = []


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(prog="gal-translator")
    subparsers = parser.add_subparsers(dest="command", required=True)

    doctor_parser = subparsers.add_parser("doctor", help="check local environment readiness")
    doctor_parser.add_argument(
        "--workspace",
        default=Path.home() / "AppData" / "Local" / "GalTranslator",
        help="workspace root to check for writability",
    )

    smoke_parser = subparsers.add_parser("smoke-test", help="run a synthetic local end-to-end workflow smoke test")
    smoke_parser.add_argument(
        "--workspace",
        default=None,
        help="workspace root for smoke artifacts; defaults to LOCALAPPDATA/GalTranslator/smoke-tests/<run-id>",
    )
    smoke_parser.add_argument("--model", default="gpt-5.5", help="model name to pass through the fake Codex command")
    smoke_parser.add_argument("--open-subtitle", action="store_true", help="open the synthetic subtitle window in a detached process after translation")
    smoke_parser.add_argument("--subtitle-exit-after", type=float, default=0.0, help="auto-close the synthetic subtitle window after N seconds; 0 keeps it open")
    smoke_parser.add_argument("--keep-fake-codex", action="store_true", help="keep the generated fake Codex launcher in the smoke workspace")

    desktop_parser = subparsers.add_parser("desktop", help="open the local desktop product shell")
    desktop_parser.add_argument("--workspace", default=Path.home() / "AppData" / "Local" / "GalTranslator", help="workspace root for Gal Translator projects")
    desktop_parser.add_argument("--source-name", default="textractor", help="logical source name for Hook/Textractor/source-log lines")
    desktop_parser.add_argument("--batch-size", type=int, default=40, help="items per Codex batch")
    desktop_parser.add_argument("--model", default="gpt-5.5", help="Codex model name")
    desktop_parser.add_argument("--translate-timeout", type=int, default=600, help="per-batch Codex timeout in seconds")
    desktop_parser.add_argument("--start-luna-hook-bridge", action="store_true", help="include the LunaHook bridge in Play Output source-log sessions")
    desktop_parser.add_argument("--luna-hook-game-process", default="selectoblige", help="game process name used when starting the LunaHook bridge from the desktop shell")
    desktop_parser.add_argument("--luna-hook-code", action="append", default=[], help="LunaHook hook code to include in desktop source-log session commands; can be repeated")
    desktop_parser.add_argument("--luna-hook-duration", type=float, default=3600.0, help="seconds for the desktop LunaHook bridge to run")
    desktop_parser.add_argument("--luna-hook-max-events", type=int, default=0, help="stop the desktop LunaHook bridge after N captured events; 0 disables")
    desktop_parser.add_argument("--luna-hook-idle-timeout", type=float, default=0.0, help="stop the desktop LunaHook bridge after N idle seconds once output was captured; 0 disables")
    desktop_parser.add_argument("--dry-run", action="store_true", help="print shell capabilities without opening Tk")

    scan_parser = subparsers.add_parser("scan", help="scan a Galgame exe or game directory")
    scan_parser.add_argument("path", help="path to game exe or game directory")

    init_parser = subparsers.add_parser("init", help="create a local translation project")
    init_parser.add_argument("path", help="path to game exe or game directory")
    init_parser.add_argument(
        "--workspace",
        default=Path.home() / "AppData" / "Local" / "GalTranslator",
        help="workspace root for Gal Translator projects",
    )

    import_parser = subparsers.add_parser("import", help="import direct scripts into a project")
    import_parser.add_argument("path", help="path to game exe or game directory")
    import_parser.add_argument(
        "--workspace",
        default=Path.home() / "AppData" / "Local" / "GalTranslator",
        help="workspace root for Gal Translator projects",
    )

    artemis_import_parser = subparsers.add_parser(
        "import-artemis-ast",
        help="import exported Artemis .ast scripts into a project",
    )
    artemis_import_parser.add_argument("path", help="path to exported Artemis script directory")
    artemis_import_parser.add_argument(
        "--workspace",
        default=Path.home() / "AppData" / "Local" / "GalTranslator",
        help="workspace root for Gal Translator projects",
    )

    progress_parser = subparsers.add_parser("progress", help="show translation progress")
    progress_parser.add_argument("project_root", help="path to an existing translation project")

    retry_parser = subparsers.add_parser("retry-failed", help="move failed translation items back to pending")
    retry_parser.add_argument("project_root", help="path to an existing translation project")

    clear_lock_parser = subparsers.add_parser("clear-lock", help="clear a stale project translation lock")
    clear_lock_parser.add_argument("project_root", help="path to an existing translation project")
    clear_lock_parser.add_argument("--force", action="store_true", help="remove the lock even if its recorded process appears active")

    info_parser = subparsers.add_parser("project-info", help="show project status and recommended next actions")
    info_parser.add_argument("project_root", help="path to an existing translation project")

    session_info_parser = subparsers.add_parser("session-info", help="inspect a saved play/live session report and show resume actions")
    session_info_parser.add_argument("session_report", help="path to a saved session report JSON")

    source_log_status_parser = subparsers.add_parser("source-log-status", help="inspect the paused full-archive source-log play loop")
    source_log_status_parser.add_argument("project_root", help="path to an existing translation project")
    source_log_status_parser.add_argument("source_log", help="path to the Hook/Textractor/source-log file")
    source_log_status_parser.add_argument("--session-report", default=None, help="optional saved source-log-session report JSON")
    source_log_status_parser.add_argument("--source-name", default="lunahook", help="logical source name for source-log lines")
    source_log_status_parser.add_argument("--encoding", default="utf-8", help="source-log encoding")
    source_log_status_parser.add_argument("--game-process", action="append", default=[], help="game process image name to check, e.g. selectoblige.exe")
    source_log_status_parser.add_argument("--hook-process", action="append", default=[], help="hook/capture process image name to check")

    luna_hook_bridge_parser = subparsers.add_parser("luna-hook-bridge", help="append LunaHook output directly to a source log")
    luna_hook_bridge_parser.add_argument("game_pid", type=int, help="running game process id")
    luna_hook_bridge_parser.add_argument("source_log", help="path to append captured Hook text")
    luna_hook_bridge_parser.add_argument(
        "--luna-root",
        default=r"C:\Game\LunaTranslator_x64_win10_v10.12.3\LunaTranslator_x64_win10",
        help="LunaTranslator portable root containing files/LunaHook",
    )
    luna_hook_bridge_parser.add_argument("--hook-code", action="append", default=[], help="LunaHook hook code to insert; can be repeated")
    luna_hook_bridge_parser.add_argument("--duration", type=float, default=0.0, help="seconds to run; 0 means until interrupted or max-events")
    luna_hook_bridge_parser.add_argument("--max-events", type=int, default=0, help="stop after N captured Japanese outputs; 0 disables")
    luna_hook_bridge_parser.add_argument("--idle-timeout", type=float, default=0.0, help="stop after N idle seconds once output has been captured; 0 disables")
    luna_hook_bridge_parser.add_argument("--overwrite-log", action="store_true", help="overwrite the source log instead of appending")
    luna_hook_bridge_parser.add_argument("--include-non-japanese", action="store_true", help="append non-Japanese hook output too")
    luna_hook_bridge_parser.add_argument("--status-log", default=None, help="write bridge lifecycle/capture events as JSONL")
    luna_hook_bridge_parser.add_argument("--dry-run", action="store_true", help="print the bridge plan without loading LunaHook DLLs")

    resume_session_parser = subparsers.add_parser("resume-session", help="continue translation or subtitle startup from a saved session report")
    resume_session_parser.add_argument("session_report", help="path to a saved session report JSON")
    resume_session_parser.add_argument("--dry-run", action="store_true", help="report the next action without executing it")
    resume_session_parser.add_argument("--open-subtitle", action="store_true", help="open the saved subtitle window command when the project is translated")
    resume_session_parser.add_argument("--start-miss-watcher", action="store_true", help="start the saved miss-log watch command after the project is ready")
    resume_session_parser.add_argument("--start-session-log-watcher", action="store_true", help="start the saved session-log watch command after the project is ready")
    resume_session_parser.add_argument("--subtitle-foreground", action="store_true", help="run subtitle-window in the foreground instead of a detached process")
    resume_session_parser.add_argument("--retry-failed", action="store_true", help="reset failed translation entries to pending before resuming translation")

    batch_parser = subparsers.add_parser("batch", help="print the next translation batch prompt")
    batch_parser.add_argument("project_root", help="path to an existing translation project")
    batch_parser.add_argument("--size", type=int, default=40, help="maximum items in the batch")

    prepare_parser = subparsers.add_parser("prepare-codex", help="write Codex prompt/schema files for the next batch")
    prepare_parser.add_argument("project_root", help="path to an existing translation project")
    prepare_parser.add_argument("--size", type=int, default=40, help="maximum items in the batch")
    prepare_parser.add_argument("--model", default="gpt-5.5", help="Codex model name")
    prepare_parser.add_argument("--out-dir", default=None, help="output directory for prompt/schema/result files")

    run_parser = subparsers.add_parser("run-codex", help="prepare and optionally execute a Codex batch")
    run_parser.add_argument("project_root", help="path to an existing translation project")
    run_parser.add_argument("--size", type=int, default=40, help="maximum items in the batch")
    run_parser.add_argument("--model", default="gpt-5.5", help="Codex model name")
    run_parser.add_argument("--out-dir", default=None, help="output directory for prompt/schema/result/log files")
    run_parser.add_argument("--dry-run", action="store_true", help="write files and command but do not execute Codex")
    run_parser.add_argument("--apply", action="store_true", help="apply result JSON when Codex succeeds")
    run_parser.add_argument("--timeout", type=int, default=0, help="Codex execution timeout in seconds; 0 means no timeout")

    translate_all_parser = subparsers.add_parser("translate-all", help="run Codex batches until all pending entries are translated")
    translate_all_parser.add_argument("project_root", help="path to an existing translation project")
    translate_all_parser.add_argument("--size", type=int, default=40, help="maximum items per Codex batch")
    translate_all_parser.add_argument("--model", default="gpt-5.5", help="Codex model name")
    translate_all_parser.add_argument("--max-batches", type=int, default=0, help="maximum batches to execute; 0 means all pending batches")
    translate_all_parser.add_argument("--timeout", type=int, default=0, help="per-batch Codex timeout in seconds; 0 means no timeout")
    translate_all_parser.add_argument("--dry-run", action="store_true", help="write the first batch files and report the execution plan without running Codex")
    translate_all_parser.add_argument("--retry-failed", action="store_true", help="reset failed entries to pending before running batches")

    apply_parser = subparsers.add_parser("apply-result", help="apply a Codex result JSON file")
    apply_parser.add_argument("project_root", help="path to an existing translation project")
    apply_parser.add_argument("result_json", help="path to Codex output JSON")

    lookup_parser = subparsers.add_parser("lookup", help="look up translated display text")
    lookup_parser.add_argument("project_root", help="path to an existing translation project")
    lookup_parser.add_argument("text", help="current Japanese text from clipboard or hook")

    replay_parser = subparsers.add_parser("replay-log", help="replay a Textractor/clipboard log through runtime matching")
    replay_parser.add_argument("project_root", help="path to an existing translation project")
    replay_parser.add_argument("log_file", help="path to captured text log")
    replay_parser.add_argument("--encoding", default="utf-8", help="text log encoding")
    replay_parser.add_argument("--source-name", default="replay", help="logical source name for replay entries")
    replay_parser.add_argument("--limit", type=int, default=0, help="maximum replay events; 0 means all")
    replay_parser.add_argument("--include-source", action="store_true", help="include raw source text in replay output")
    replay_parser.add_argument("--event-log", default=None, help="write replay events as JSONL to this path")

    archive_parser = subparsers.add_parser("archive-list", help="list visible entries in PFS/pf8 archives")
    archive_parser.add_argument("path", help="path to a .pfs archive, game exe, or game directory")
    archive_parser.add_argument("--scripts-only", action="store_true", help="only include script-like entries")
    archive_parser.add_argument("--limit", type=int, default=200, help="maximum entries per archive")

    inspect_log_parser = subparsers.add_parser("inspect-log", help="inspect a Textractor/clipboard text log without creating a project")
    inspect_log_parser.add_argument("log_file", help="path to captured text log")
    inspect_log_parser.add_argument("--encoding", default="utf-8", help="text log encoding")
    inspect_log_parser.add_argument("--source-name", default=None, help="logical source name for entry ids")
    inspect_log_parser.add_argument("--limit", type=int, default=10, help="maximum imported entries to preview")
    inspect_log_parser.add_argument("--include-source", action="store_true", help="include captured source text in preview")

    capture_parser = subparsers.add_parser("capture-log", help="import a Textractor/clipboard text log")
    capture_parser.add_argument("path", help="path to game exe or game directory")
    capture_parser.add_argument("log_file", help="path to captured text log")
    capture_parser.add_argument(
        "--workspace",
        default=Path.home() / "AppData" / "Local" / "GalTranslator",
        help="workspace root for Gal Translator projects",
    )
    capture_parser.add_argument("--encoding", default="utf-8", help="text log encoding")
    capture_parser.add_argument("--source-name", default=None, help="logical source name for entry ids")
    capture_parser.add_argument("--append", action="store_true", help="append new entries to an existing project state")

    append_log_parser = subparsers.add_parser("append-log", help="append a Textractor/clipboard log to an existing project")
    append_log_parser.add_argument("project_root", help="path to an existing translation project")
    append_log_parser.add_argument("log_file", help="path to captured text log")
    append_log_parser.add_argument("--encoding", default="utf-8", help="text log encoding")
    append_log_parser.add_argument("--source-name", default=None, help="logical source name for entry ids")

    translate_log_parser = subparsers.add_parser("translate-log", help="append a text log to an existing project and translate pending entries")
    translate_log_parser.add_argument("project_root", help="path to an existing translation project")
    translate_log_parser.add_argument("log_file", help="path to captured, recorded, or miss text log")
    translate_log_parser.add_argument("--encoding", default="utf-8", help="text log encoding")
    translate_log_parser.add_argument("--source-name", default="misses", help="logical source name for entry ids")
    translate_log_parser.add_argument("--size", type=int, default=40, help="items per Codex batch")
    translate_log_parser.add_argument("--model", default="gpt-5.5", help="Codex model name")
    translate_log_parser.add_argument("--timeout", type=int, default=600, help="per-batch Codex timeout in seconds")
    translate_log_parser.add_argument("--max-batches", type=int, default=0, help="maximum batches to translate; 0 means all")
    translate_log_parser.add_argument(
        "--only-new-log-entries",
        action="store_true",
        help="translate only entries referenced by this log invocation, including existing pending source matches",
    )
    translate_log_parser.add_argument("--dry-run", action="store_true", help="append the log and prepare the first batch without running Codex")
    translate_log_parser.add_argument("--replay-event-log", default=None, help="write replay events for this log as JSONL")
    translate_log_parser.add_argument("--replay-include-source", action="store_true", help="include source text in replay payload")
    translate_log_parser.add_argument("--watch", action="store_true", help="keep watching the log and translate when it changes")
    translate_log_parser.add_argument("--watch-interval", type=float, default=5.0, help="seconds between watch polls")
    translate_log_parser.add_argument("--watch-max-cycles", type=int, default=0, help="maximum watch cycles; 0 means unlimited")
    translate_log_parser.add_argument("--watch-idle-cycles", type=int, default=0, help="stop after N unchanged/missing-log cycles; 0 means unlimited")
    translate_log_parser.add_argument("--watch-require-ready", action="store_true", help="wait until the existing project has no pending or failed translations before processing changed logs")

    workflow_parser = subparsers.add_parser("workflow-fallback", help="run the Textractor/clipboard fallback workflow")
    workflow_parser.add_argument("path", help="path to game exe or game directory")
    workflow_parser.add_argument("log_file", help="path to captured text log")
    workflow_parser.add_argument(
        "--workspace",
        default=Path.home() / "AppData" / "Local" / "GalTranslator",
        help="workspace root for Gal Translator projects",
    )
    workflow_parser.add_argument("--encoding", default="utf-8", help="text log encoding")
    workflow_parser.add_argument("--source-name", default="textractor", help="logical source name for entry ids")
    workflow_parser.add_argument("--append", action="store_true", help="append to the existing project state")
    workflow_parser.add_argument("--prepare-size", type=int, default=40, help="items to include in prepared Codex batch")
    workflow_parser.add_argument("--model", default="gpt-5.5", help="Codex model name")
    workflow_parser.add_argument("--translate-all", action="store_true", help="run and apply Codex batches after capture import")
    workflow_parser.add_argument("--translate-dry-run", action="store_true", help="plan translate-all after capture without running Codex")
    workflow_parser.add_argument("--translate-timeout", type=int, default=0, help="per-batch Codex timeout in seconds for --translate-all")
    workflow_parser.add_argument("--translate-max-batches", type=int, default=0, help="maximum batches for --translate-all; 0 means all")
    workflow_parser.add_argument("--replay-event-log", default=None, help="write replay events after capture/translation as JSONL")
    workflow_parser.add_argument("--replay-include-source", action="store_true", help="include source text in replay payload")

    record_parser = subparsers.add_parser("record-clipboard", help="record changed clipboard text to a UTF-8 log")
    record_parser.add_argument("log_file", help="path to write captured clipboard text")
    record_parser.add_argument("--interval", type=float, default=0.25, help="poll interval in seconds")
    record_parser.add_argument("--max-events", type=int, default=0, help="stop after N captured entries; 0 means unlimited")
    record_parser.add_argument("--duration", type=float, default=0.0, help="maximum recording duration in seconds; 0 means record until interrupted or max-events is reached")
    record_parser.add_argument("--overwrite", action="store_true", help="overwrite the log instead of appending")

    session_parser = subparsers.add_parser("play-session", help="run capture, translation, replay, and subtitle setup for a local play session")
    session_parser.add_argument("path", help="path to game exe or game directory")
    session_parser.add_argument("log_file", nargs="?", help="path to captured or recorded text log; defaults to workspace/captures/<game>-live-capture.txt")
    session_parser.add_argument(
        "--workspace",
        default=Path.home() / "AppData" / "Local" / "GalTranslator",
        help="workspace root for Gal Translator projects",
    )
    session_parser.add_argument("--encoding", default="utf-8", help="text log encoding")
    session_parser.add_argument("--source-name", default="textractor", help="logical source name for entry ids")
    session_parser.add_argument("--append", action="store_true", help="append to the existing project state")
    session_parser.add_argument("--launch-game", action="store_true", help="start the game exe before recording/importing")
    session_parser.add_argument("--record-clipboard", action="store_true", help="record changed clipboard text to log_file before importing")
    session_parser.add_argument("--record-interval", type=float, default=0.25, help="clipboard recording poll interval in seconds")
    session_parser.add_argument("--record-max-events", type=int, default=0, help="maximum clipboard entries to record; 0 means unlimited")
    session_parser.add_argument("--record-duration", type=float, default=60.0, help="clipboard recording duration in seconds for play-session; default is 60")
    session_parser.add_argument("--record-until-interrupted", action="store_true", help="record clipboard indefinitely until interrupted or --record-max-events is reached")
    session_parser.add_argument("--overwrite-log", action="store_true", help="overwrite log_file when recording clipboard")
    session_parser.add_argument("--batch-size", type=int, default=40, help="items per Codex batch")
    session_parser.add_argument("--model", default="gpt-5.5", help="Codex model name")
    session_parser.add_argument("--translate-dry-run", action="store_true", help="prepare the first translation batch without running Codex")
    session_parser.add_argument("--translate-timeout", type=int, default=600, help="per-batch Codex timeout in seconds")
    session_parser.add_argument("--translate-max-batches", type=int, default=0, help="maximum batches to translate; 0 means all")
    session_parser.add_argument("--translate-retry-failed", action="store_true", help="reset failed entries to pending before running session translation")
    session_parser.add_argument("--replay-event-log", default=None, help="write replay events after translation as JSONL")
    session_parser.add_argument("--replay-include-source", action="store_true", help="include source text in replay payload")
    session_parser.add_argument("--no-subtitle", action="store_true", help="do not start or dry-run the subtitle window")
    session_parser.add_argument("--subtitle-dry-run", action="store_true", help="validate subtitle config without opening a window")
    session_parser.add_argument("--subtitle-detach", action="store_true", help="start subtitle-window in a separate process and return immediately")
    session_parser.add_argument("--subtitle-preview-source", default=None, help="initially show the translation for this exact source text when starting subtitle-window")
    session_parser.add_argument("--subtitle-preview-first-match", action="store_true", help="initially show the first translated line from this session's captured log")
    session_parser.add_argument("--subtitle-source-log", action="store_true", help="make subtitle-window poll this session log instead of the clipboard")
    session_parser.add_argument("--subtitle-source-log-from-start", action="store_true", help="when using --subtitle-source-log, replay existing translated log lines from the start")
    session_parser.add_argument("--interval", type=float, default=0.25, help="subtitle runtime source poll interval in seconds")
    session_parser.add_argument("--font-size", type=int, default=30, help="subtitle font size")
    session_parser.add_argument("--opacity", type=float, default=0.82, help="window opacity from 0.2 to 1.0")
    session_parser.add_argument("--width", type=int, default=1200, help="window width")
    session_parser.add_argument("--height", type=int, default=120, help="window height")
    session_parser.add_argument("--x", type=int, default=120, help="window x position")
    session_parser.add_argument("--y", type=int, default=760, help="window y position")
    session_parser.add_argument("--font-family", default="Microsoft YaHei UI", help="subtitle font family")
    session_parser.add_argument("--background", default="#050505", help="window background color")
    session_parser.add_argument("--foreground", default="#f5f5f5", help="subtitle text color")
    session_parser.add_argument("--clear-after", type=float, default=4.0, help="clear visible text after N seconds; 0 disables")
    session_parser.add_argument("--subtitle-exit-after", type=float, default=0.0, help="auto-close subtitle-window after N seconds; 0 keeps it open")
    session_parser.add_argument("--not-topmost", action="store_true", help="do not keep the subtitle window above others")
    session_parser.add_argument("--subtitle-config", default=None, help="load subtitle window layout/style JSON before applying explicit CLI options")
    session_parser.add_argument("--subtitle-save-config", default=None, help="write the resolved subtitle window layout/style JSON")
    session_parser.add_argument("--subtitle-event-log", default=None, help="subtitle runtime JSONL event log path")
    session_parser.add_argument("--subtitle-no-log", action="store_true", help="do not write subtitle runtime event logs")
    session_parser.add_argument("--subtitle-include-source", action="store_true", help="include source text in subtitle event logs")
    session_parser.add_argument("--subtitle-miss-log", default=None, help="write unmatched runtime source text to this plain-text log")
    session_parser.add_argument("--subtitle-no-reload", action="store_true", help="do not reload translation-state.json while the subtitle window is open")
    session_parser.add_argument("--session-report", default=None, help="write the final play-session JSON payload to this path")

    live_parser = subparsers.add_parser("live-session", help="run a supervised local play session with background log translators")
    live_parser.add_argument("path", help="path to game exe or game directory")
    live_parser.add_argument("log_file", nargs="?", help="path to captured or recorded text log; defaults to workspace/captures/<game>-live-capture.txt")
    live_parser.add_argument("--workspace", default=Path.home() / "AppData" / "Local" / "GalTranslator", help="workspace root for Gal Translator projects")
    live_parser.add_argument("--encoding", default="utf-8", help="text log encoding")
    live_parser.add_argument("--source-name", default="textractor", help="logical source name for entry ids")
    live_parser.add_argument("--append", action="store_true", help="append to the existing project state")
    live_parser.add_argument("--launch-game", action="store_true", help="start the game exe before recording/importing")
    live_parser.add_argument("--record-clipboard", action="store_true", help="record changed clipboard text to log_file before importing")
    live_parser.add_argument("--record-interval", type=float, default=0.25, help="clipboard recording poll interval in seconds")
    live_parser.add_argument("--record-max-events", type=int, default=0, help="maximum clipboard entries to record; 0 means unlimited")
    live_parser.add_argument("--record-duration", type=float, default=60.0, help="clipboard recording duration in seconds")
    live_parser.add_argument("--record-until-interrupted", action="store_true", help="record clipboard indefinitely until interrupted or --record-max-events is reached")
    live_parser.add_argument("--overwrite-log", action="store_true", help="overwrite log_file when recording clipboard")
    live_parser.add_argument("--batch-size", type=int, default=40, help="items per Codex batch")
    live_parser.add_argument("--model", default="gpt-5.5", help="Codex model name")
    live_parser.add_argument("--translate-dry-run", action="store_true", help="prepare the first translation batch without running Codex")
    live_parser.add_argument("--translate-timeout", type=int, default=600, help="per-batch Codex timeout in seconds")
    live_parser.add_argument("--translate-max-batches", type=int, default=0, help="maximum batches to translate; 0 means all")
    live_parser.add_argument("--translate-retry-failed", action="store_true", help="reset failed entries to pending before running session translation")
    live_parser.add_argument("--replay-event-log", default=None, help="write replay events after translation as JSONL")
    live_parser.add_argument("--replay-include-source", action="store_true", help="include source text in replay payload")
    live_parser.add_argument("--no-subtitle", action="store_true", help="do not start or dry-run the subtitle window")
    live_parser.add_argument("--subtitle-dry-run", action="store_true", help="validate subtitle config without opening a window")
    live_parser.add_argument("--subtitle-detach", action="store_true", help="start subtitle-window in a separate process and return immediately")
    live_parser.add_argument("--subtitle-preview-source", default=None, help="initially show the translation for this exact source text")
    live_parser.add_argument("--subtitle-preview-first-match", action="store_true", help="initially show the first translated line")
    live_parser.add_argument("--subtitle-source-log", action="store_true", help="make subtitle-window poll this session log instead of clipboard")
    live_parser.add_argument("--subtitle-source-log-from-start", action="store_true", help="replay existing source-log lines from the start")
    live_parser.add_argument("--interval", type=float, default=0.25, help="subtitle runtime source poll interval in seconds")
    live_parser.add_argument("--font-size", type=int, default=30, help="subtitle font size")
    live_parser.add_argument("--opacity", type=float, default=0.82, help="window opacity from 0.2 to 1.0")
    live_parser.add_argument("--width", type=int, default=1200, help="window width")
    live_parser.add_argument("--height", type=int, default=120, help="window height")
    live_parser.add_argument("--x", type=int, default=120, help="window x position")
    live_parser.add_argument("--y", type=int, default=760, help="window y position")
    live_parser.add_argument("--font-family", default="Microsoft YaHei UI", help="subtitle font family")
    live_parser.add_argument("--background", default="#050505", help="window background color")
    live_parser.add_argument("--foreground", default="#f5f5f5", help="subtitle text color")
    live_parser.add_argument("--clear-after", type=float, default=4.0, help="clear visible text after N seconds; 0 disables")
    live_parser.add_argument("--subtitle-exit-after", type=float, default=0.0, help="auto-close subtitle-window after N seconds; 0 keeps it open")
    live_parser.add_argument("--not-topmost", action="store_true", help="do not keep the subtitle window above others")
    live_parser.add_argument("--subtitle-config", default=None, help="load subtitle window layout/style JSON before applying explicit CLI options")
    live_parser.add_argument("--subtitle-save-config", default=None, help="write the resolved subtitle window layout/style JSON")
    live_parser.add_argument("--subtitle-event-log", default=None, help="subtitle runtime JSONL event log path")
    live_parser.add_argument("--subtitle-no-log", action="store_true", help="do not write subtitle runtime event logs")
    live_parser.add_argument("--subtitle-include-source", action="store_true", help="include source text in subtitle event logs")
    live_parser.add_argument("--subtitle-miss-log", default=None, help="write unmatched runtime source text to this plain-text log")
    live_parser.add_argument("--subtitle-no-reload", action="store_true", help="do not reload translation-state.json while the subtitle window is open")
    live_parser.add_argument("--session-report", default=None, help="write the final live-session JSON payload to this path")
    live_parser.add_argument("--no-miss-watcher", action="store_true", help="do not start a background miss-log translator")
    live_parser.add_argument("--no-session-log-watcher", action="store_true", help="do not start a background source-log translator")
    live_parser.add_argument("--keep-watchers", action="store_true", help="leave started watcher processes running after this command exits")
    live_parser.add_argument("--watch-interval", type=float, default=5.0, help="seconds between watcher polls")
    live_parser.add_argument("--watch-max-cycles", type=int, default=0, help="maximum watcher cycles; 0 means unlimited")
    live_parser.add_argument("--watch-idle-cycles", type=int, default=0, help="stop watchers after N idle cycles; 0 means unlimited")

    watch_parser = subparsers.add_parser("watch-clipboard", help="watch clipboard text and output subtitle matches")
    watch_parser.add_argument("project_root", help="path to an existing translation project")
    watch_parser.add_argument("--interval", type=float, default=0.25, help="poll interval in seconds")
    watch_parser.add_argument("--max-events", type=int, default=0, help="stop after N emitted events; 0 means forever")
    watch_parser.add_argument("--once", action="store_true", help="poll once and exit")
    watch_parser.add_argument("--no-reload", action="store_true", help="do not reload translation-state.json while watching")
    watch_parser.add_argument("--no-log", action="store_true", help="do not write runtime event logs")
    watch_parser.add_argument("--event-log", default=None, help="runtime JSONL event log path")
    watch_parser.add_argument("--include-source", action="store_true", help="include raw clipboard text in diagnostic output and event logs")
    watch_parser.add_argument("--miss-log", default=None, help="write unmatched raw clipboard text to this plain-text log")

    window_parser = subparsers.add_parser("subtitle-window", help="show a local always-on-top subtitle window")
    window_parser.add_argument("project_root", help="path to an existing translation project")
    window_parser.add_argument("--interval", type=float, default=0.25, help="runtime source poll interval in seconds")
    window_parser.add_argument("--font-size", type=int, default=28, help="subtitle font size")
    window_parser.add_argument("--opacity", type=float, default=0.85, help="window opacity from 0.2 to 1.0")
    window_parser.add_argument("--width", type=int, default=900, help="window width")
    window_parser.add_argument("--height", type=int, default=140, help="window height")
    window_parser.add_argument("--x", type=int, default=None, help="window x position")
    window_parser.add_argument("--y", type=int, default=None, help="window y position")
    window_parser.add_argument("--font-family", default="Microsoft YaHei UI", help="subtitle font family")
    window_parser.add_argument("--background", default="#050505", help="window background color")
    window_parser.add_argument("--foreground", default="#f5f5f5", help="subtitle text color")
    window_parser.add_argument("--clear-after", type=float, default=0.0, help="clear visible text after N seconds; 0 disables")
    window_parser.add_argument("--exit-after", type=float, default=0.0, help="auto-close the window after N seconds; 0 keeps it open")
    window_parser.add_argument("--dry-run", action="store_true", help="validate config and project state without opening a window")
    window_parser.add_argument("--preview-source", default=None, help="preview or initially show the translation for this source text")
    window_parser.add_argument("--source-log", default=None, help="poll this Textractor/clipboard log for new source lines instead of the clipboard")
    window_parser.add_argument("--source-log-encoding", default="utf-8", help="encoding for --source-log")
    window_parser.add_argument("--source-log-name", default=None, help="logical source name for --source-log line ids")
    window_parser.add_argument("--source-log-from-start", action="store_true", help="emit existing --source-log lines from the start instead of tailing only new lines")
    window_parser.add_argument("--no-reload", action="store_true", help="do not reload translation-state.json while the window is open")
    window_parser.add_argument("--not-topmost", action="store_true", help="do not keep the window above others")
    window_parser.add_argument("--config", default=None, help="load subtitle window layout/style JSON before applying explicit CLI options")
    window_parser.add_argument("--save-config", default=None, help="write the resolved subtitle window layout/style JSON")
    window_parser.add_argument("--no-log", action="store_true", help="do not write runtime event logs")
    window_parser.add_argument("--event-log", default=None, help="runtime JSONL event log path")
    window_parser.add_argument("--include-source", action="store_true", help="include raw source text in subtitle event logs")
    window_parser.add_argument("--miss-log", default=None, help="write unmatched raw runtime source text to this plain-text log")

    args = parser.parse_args()
    if args.command == "doctor":
        print(json.dumps(_doctor_payload(Path(args.workspace)), ensure_ascii=False, indent=2))
        return 0
    if args.command == "smoke-test":
        payload, return_code = _smoke_test_payload(args)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return return_code
    if args.command == "desktop":
        config = DesktopShellConfig(
            workspace=Path(args.workspace),
            source_name=args.source_name,
            batch_size=args.batch_size,
            model=args.model,
            translate_timeout=args.translate_timeout,
            start_luna_hook_bridge=args.start_luna_hook_bridge,
            luna_hook_game_process=args.luna_hook_game_process,
            luna_hook_codes=tuple(args.luna_hook_code) if args.luna_hook_code else DesktopShellConfig().luna_hook_codes,
            luna_hook_duration=args.luna_hook_duration,
            luna_hook_max_events=args.luna_hook_max_events,
            luna_hook_idle_timeout=args.luna_hook_idle_timeout,
        )
        if args.dry_run:
            print(json.dumps(desktop_shell_payload(config), ensure_ascii=False, indent=2))
            return 0
        launch_desktop_shell(config)
        return 0
    if args.command == "scan":
        report = GameScanner().scan(Path(args.path))
        candidates = EngineDetector().detect(report)
        print(json.dumps(_scan_payload(report, candidates), ensure_ascii=False, indent=2))
        return 0
    if args.command == "init":
        project = TranslationProjectManager(Path(args.workspace)).create_project(Path(args.path))
        profiles = ExtractorProfileRegistry.default().match(project.scan_report)
        print(json.dumps(_project_payload(project, profiles), ensure_ascii=False, indent=2))
        return 0
    if args.command == "import":
        project = TranslationProjectManager(Path(args.workspace)).create_project(Path(args.path))
        if _has_artemis_ast_scripts(project.game_root):
            payload = _import_artemis_ast_payload(project)
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 0
        profiles = ExtractorProfileRegistry.default().match(project.scan_report)
        if not profiles:
            entries_path = project.project_root / "story-entries.json"
            entries_path.write_text("[]", encoding="utf-8")
            tracker = TranslationProgressTracker.initialize(project, [])
            print(json.dumps(_import_payload(project, [], [], tracker), ensure_ascii=False, indent=2))
            return 0
        imported = DirectScriptImporter().import_scripts(project, profiles[0])
        entries = _parse_story_entries(imported)
        entries_path = project.project_root / "story-entries.json"
        entries_path.write_text(
            json.dumps([_entry_payload(entry) for entry in entries], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tracker = TranslationProgressTracker.initialize(project, entries)
        print(json.dumps(_import_payload(project, imported, entries, tracker), ensure_ascii=False, indent=2))
        return 0
    if args.command == "import-artemis-ast":
        project = TranslationProjectManager(Path(args.workspace)).create_project(Path(args.path))
        payload = _import_artemis_ast_payload(project)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    if args.command == "progress":
        state_path = Path(args.project_root) / "translation-state.json"
        if not state_path.is_file():
            return _print_error(
                "translation_state_missing",
                f"translation state not found: {state_path}",
                ["Run import, capture-log, or append-log before checking progress."],
            )
        tracker = TranslationProgressTracker(state_path)
        print(json.dumps(_summary_payload(tracker.summary()), ensure_ascii=False, indent=2))
        return 0
    if args.command == "retry-failed":
        state_path = Path(args.project_root) / "translation-state.json"
        if not state_path.is_file():
            return _print_error(
                "translation_state_missing",
                f"translation state not found: {state_path}",
                ["Run import or capture-log before retry-failed."],
            )
        tracker = TranslationProgressTracker(state_path)
        retry_summary = tracker.reset_failed_summary()
        print(
            json.dumps(
                {
                    **retry_summary.to_payload(),
                    "progress": _summary_payload(tracker.summary()),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    if args.command == "clear-lock":
        payload, return_code = _clear_translation_lock_payload(Path(args.project_root), force=args.force)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return return_code
    if args.command == "project-info":
        print(json.dumps(_project_info_payload(Path(args.project_root)), ensure_ascii=False, indent=2))
        return 0
    if args.command == "session-info":
        try:
            payload = _session_info_payload(Path(args.session_report))
        except FileNotFoundError as error:
            return _print_error(
                "session_report_missing",
                str(error),
                ["Pass a sessionReportPath returned by play-session or live-session."],
            )
        except (OSError, json.JSONDecodeError, TypeError) as error:
            return _print_error(
                "session_report_invalid",
                str(error),
                ["Use a valid JSON file written by play-session --session-report or live-session.ps1."],
            )
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    if args.command == "source-log-status":
        payload = _source_log_status_payload(
            project_root=Path(args.project_root),
            source_log=Path(args.source_log),
            session_report=Path(args.session_report) if args.session_report else None,
            source_name=args.source_name,
            encoding=args.encoding,
            game_processes=args.game_process,
            hook_processes=args.hook_process,
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0 if payload["status"] != "project_missing" else 1
    if args.command == "luna-hook-bridge":
        config = LunaHookBridgeConfig(
            luna_root=Path(args.luna_root),
            game_pid=args.game_pid,
            source_log=Path(args.source_log),
            hook_codes=args.hook_code,
            duration_seconds=args.duration,
            max_events=args.max_events,
            idle_timeout_seconds=args.idle_timeout,
            append=not args.overwrite_log,
            include_non_japanese=args.include_non_japanese,
            status_log=Path(args.status_log) if args.status_log else None,
        )
        bridge = LunaHookBridge(config)
        try:
            payload = bridge.dry_run_payload() if args.dry_run else bridge.run()
        except (OSError, RuntimeError, FileNotFoundError) as error:
            return _print_error(
                "lunahook_bridge_failed",
                str(error),
                [
                    "Verify the game process is still running and --luna-root points to a LunaTranslator portable install.",
                    "Keep this as an external Hook/source-log path; do not use in-game text rewrite for the MVP.",
                ],
            )
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    if args.command == "resume-session":
        try:
            payload, return_code = _resume_session_payload(
                Path(args.session_report),
                dry_run=args.dry_run,
                open_subtitle=args.open_subtitle,
                start_miss_watcher=args.start_miss_watcher,
                start_session_log_watcher=args.start_session_log_watcher,
                subtitle_foreground=args.subtitle_foreground,
                retry_failed=args.retry_failed,
            )
        except FileNotFoundError as error:
            return _print_error(
                "session_report_missing",
                str(error),
                ["Pass a sessionReportPath returned by play-session or live-session."],
            )
        except (OSError, json.JSONDecodeError, TypeError) as error:
            return _print_error(
                "session_report_invalid",
                str(error),
                ["Use a valid JSON file written by play-session --session-report or live-session.ps1."],
            )
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return return_code
    if args.command == "batch":
        state_path = Path(args.project_root) / "translation-state.json"
        if not state_path.is_file():
            return _print_error(
                "translation_state_missing",
                f"translation state not found: {state_path}",
                ["Run import or capture-log before requesting a translation batch."],
            )
        translator = CodexBatchTranslator(state_path)
        print(translator.build_prompt(translator.next_batch(args.size)))
        return 0
    if args.command == "prepare-codex":
        project_root = Path(args.project_root)
        state_path = project_root / "translation-state.json"
        if not state_path.is_file():
            return _print_error(
                "translation_state_missing",
                f"translation state not found: {state_path}",
                ["Run import or capture-log before prepare-codex."],
            )
        prepared = _prepare_codex_batch(project_root, args.size, args.model, args.out_dir)
        print(json.dumps(prepared, ensure_ascii=False, indent=2))
        return 0
    if args.command == "run-codex":
        project_root = Path(args.project_root)
        state_path = project_root / "translation-state.json"
        if not state_path.is_file():
            return _print_error(
                "translation_state_missing",
                f"translation state not found: {state_path}",
                ["Run import or capture-log before run-codex."],
            )
        prepared = _prepare_codex_batch(project_root, args.size, args.model, args.out_dir)
        if args.dry_run or prepared["batchSize"] == 0:
            print(json.dumps({**prepared, "status": "prepared"}, ensure_ascii=False, indent=2))
            return 0

        payload = _execute_prepared_codex(prepared, args.timeout)
        return_code = payload["returnCode"]
        if return_code == 0 and args.apply:
            apply_summary, error = _apply_prepared_codex_result(project_root, prepared)
            if error is not None:
                payload["status"] = "result_invalid"
                payload["returnCode"] = 1
                payload["error"] = error
                print(json.dumps(payload, ensure_ascii=False, indent=2))
                return 1
            payload["applyResult"] = apply_summary.to_payload()
            payload["progress"] = _project_progress_payload(project_root)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0 if return_code == 0 else 1
    if args.command == "translate-all":
        project_root = Path(args.project_root)
        state_path = project_root / "translation-state.json"
        if not state_path.is_file():
            return _print_error(
                "translation_state_missing",
                f"translation state not found: {state_path}",
                ["Run import or capture-log before translate-all."],
            )
        payload, return_code = _translate_all_payload(
            project_root=project_root,
            batch_size=args.size,
            model=args.model,
            max_batches=args.max_batches,
            timeout=args.timeout,
            dry_run=args.dry_run,
            retry_failed=args.retry_failed,
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return return_code
    if args.command == "apply-result":
        state_path = Path(args.project_root) / "translation-state.json"
        if not state_path.is_file():
            return _print_error(
                "translation_state_missing",
                f"translation state not found: {state_path}",
                ["Run import or capture-log before apply-result."],
            )
        translator = CodexBatchTranslator(state_path)
        result_path = Path(args.result_json)
        try:
            result = json.loads(result_path.read_text(encoding="utf-8-sig"))
        except OSError as error:
            print(
                json.dumps(
                    _error_payload(
                        "result_file_unreadable",
                        str(error),
                        ["Check the result JSON path and rerun apply-result."],
                    ),
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 1
        except json.JSONDecodeError as error:
            print(
                json.dumps(
                    _error_payload(
                        "result_json_invalid",
                        str(error),
                        ["Review the Codex output JSON or rerun run-codex for this batch."],
                    ),
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 1
        expected_ids, batch_error = _expected_ids_for_result(result_path)
        if batch_error is not None:
            print(json.dumps(batch_error, ensure_ascii=False, indent=2))
            return 1
        with _project_translation_lock(Path(args.project_root)) as lock_payload:
            if lock_payload is not None:
                print(json.dumps(lock_payload, ensure_ascii=False, indent=2))
                return 1
            apply_summary = translator.apply_result(result, expected_ids=expected_ids)
        print(
            json.dumps(
                {
                    **_summary_payload(translator.tracker.summary()),
                    "applyResult": apply_summary.to_payload(),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    if args.command == "lookup":
        state_path = Path(args.project_root) / "translation-state.json"
        if not state_path.is_file():
            return _print_error(
                "translation_state_missing",
                f"translation state not found: {state_path}",
                ["Run import/capture-log and apply-result before lookup."],
            )
        records = _translation_records_from_state(state_path)
        display = RuntimeSubtitleService(MatchIndex(records)).display_for(args.text)
        print(
            json.dumps(
                {
                    "text": display.text,
                    "matchType": display.match_type,
                    "showSource": display.show_source,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    if args.command == "replay-log":
        state_path = Path(args.project_root) / "translation-state.json"
        if not state_path.is_file():
            return _print_error(
                "translation_state_missing",
                f"translation state not found: {state_path}",
                ["Run import/capture-log and apply-result before replay-log."],
            )
        try:
            capture = ClipboardLogImporter().import_log(
                Path(args.log_file),
                source_name=args.source_name,
                encoding=args.encoding,
            )
        except (OSError, UnicodeError) as error:
            return _print_error(
                "capture_log_unreadable",
                str(error),
                ["Check the Textractor/clipboard log path and encoding, then rerun replay-log."],
            )
        records = _translation_records_from_state(state_path)
        runtime = RuntimeSubtitleService(MatchIndex(records))
        payload = _replay_log_payload(runtime, capture.entries, args.limit, args.include_source)
        payload["captureStats"] = _capture_stats_payload(capture)
        if args.event_log is not None:
            _write_runtime_events_jsonl(Path(args.event_log), payload["events"])
            payload["eventLogPath"] = str(Path(args.event_log))
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    if args.command == "archive-list":
        diagnostics = _archive_diagnostics_for_path(Path(args.path))
        print(
            json.dumps(
                _archive_list_payload(diagnostics, scripts_only=args.scripts_only, limit=args.limit),
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    if args.command == "inspect-log":
        try:
            capture = ClipboardLogImporter().import_log(
                Path(args.log_file),
                source_name=args.source_name,
                encoding=args.encoding,
            )
        except (OSError, UnicodeError) as error:
            return _print_error(
                "capture_log_unreadable",
                str(error),
                ["Check the Textractor/clipboard log path and encoding, then rerun inspect-log."],
            )
        print(
            json.dumps(
                _inspect_log_payload(capture, args.limit, args.include_source),
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    if args.command == "capture-log":
        project = TranslationProjectManager(Path(args.workspace)).create_project(Path(args.path))
        try:
            capture = ClipboardLogImporter().import_log(
                Path(args.log_file),
                source_name=args.source_name,
                encoding=args.encoding,
            )
        except (OSError, UnicodeError) as error:
            return _print_error(
                "capture_log_unreadable",
                str(error),
                ["Check the Textractor/clipboard log path and encoding, then rerun capture-log."],
            )
        payload = _capture_project_payload(project, capture, append=args.append)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    if args.command == "append-log":
        project_root = Path(args.project_root)
        state_path = project_root / "translation-state.json"
        if not state_path.is_file():
            return _print_error(
                "translation_state_missing",
                f"translation state not found: {state_path}",
                ["Run capture-log once before append-log, or check the project root path."],
            )
        try:
            capture = ClipboardLogImporter().import_log(
                Path(args.log_file),
                source_name=args.source_name,
                encoding=args.encoding,
            )
        except (OSError, UnicodeError) as error:
            return _print_error(
                "capture_log_unreadable",
                str(error),
                ["Check the Textractor/clipboard log path and encoding, then rerun append-log."],
            )
        payload = _append_log_payload(project_root, capture)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    if args.command == "translate-log":
        project_root = Path(args.project_root)
        state_path = project_root / "translation-state.json"
        if args.watch:
            return _watch_translate_log(args)
        if not state_path.is_file():
            return _print_error(
                "translation_state_missing",
                f"translation state not found: {state_path}",
                ["Run capture-log once before translate-log, or check the project root path."],
            )
        try:
            payload, return_code = _translate_log_payload(args)
        except (OSError, UnicodeError) as error:
            return _print_error(
                "capture_log_unreadable",
                str(error),
                ["Check the text log path and encoding, then rerun translate-log."],
            )
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return return_code
    if args.command == "workflow-fallback":
        workspace = Path(args.workspace)
        doctor = _doctor_payload(workspace)
        report = GameScanner().scan(Path(args.path))
        candidates = EngineDetector().detect(report)
        project = TranslationProjectManager(workspace).create_project(Path(args.path))
        try:
            capture = ClipboardLogImporter().import_log(
                Path(args.log_file),
                source_name=args.source_name,
                encoding=args.encoding,
            )
        except (OSError, UnicodeError) as error:
            return _print_error(
                "capture_log_unreadable",
                str(error),
                ["Check the Textractor/clipboard log path and encoding, then rerun workflow-fallback."],
            )
        capture_payload = _capture_project_payload(project, capture, append=args.append)
        translate_payload = None
        translate_return_code = 0
        prepared = None
        if args.translate_all or args.translate_dry_run:
            translate_payload, translate_return_code = _translate_all_payload(
                project_root=project.project_root,
                batch_size=args.prepare_size,
                model=args.model,
                max_batches=args.translate_max_batches,
                timeout=args.translate_timeout,
                dry_run=args.translate_dry_run,
            )
        else:
            prepared = _prepare_codex_batch(project.project_root, args.prepare_size, args.model, None)

        replay_payload = None
        if args.replay_event_log is not None:
            records = _translation_records_from_state(project.project_root / "translation-state.json")
            runtime = RuntimeSubtitleService(MatchIndex(records))
            replay_payload = _replay_log_payload(runtime, capture.entries, 0, args.replay_include_source)
            _write_runtime_events_jsonl(Path(args.replay_event_log), replay_payload["events"])
            replay_payload["eventLogPath"] = str(Path(args.replay_event_log))

        payload = {
            "doctor": doctor,
            "scan": {
                "gameRoot": str(report.game_root),
                "engineCandidates": [_candidate_payload(candidate) for candidate in candidates],
                "nextActions": _scan_next_actions(report, candidates),
            },
            "capture": capture_payload,
            "preparedCodex": prepared,
            "translateAll": translate_payload,
            "replay": replay_payload,
            "projectInfo": _project_info_payload(project.project_root),
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return translate_return_code
    if args.command == "record-clipboard":
        try:
            provider = WindowsClipboardProvider()
        except RuntimeError as error:
            return _print_error(
                "clipboard_unavailable",
                str(error),
                ["Run record-clipboard on Windows with a clipboard-capable desktop session."],
            )
        payload = _record_clipboard_payload(
            provider=provider,
            log_path=Path(args.log_file),
            interval=args.interval,
            max_events=args.max_events,
            duration=args.duration,
            append=not args.overwrite,
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    if args.command == "play-session":
        try:
            payload, return_code = _play_session_payload(args)
        except (OSError, UnicodeError) as error:
            return _print_error(
                "capture_log_unreadable",
                str(error),
                ["Check the log path/encoding or rerun play-session with --record-clipboard."],
            )
        except RuntimeError as error:
            return _print_error(
                "clipboard_unavailable",
                str(error),
                ["Run play-session clipboard recording on Windows with a clipboard-capable desktop session."],
            )
        if args.session_report is not None:
            report_path = Path(args.session_report)
            payload["sessionReportPath"] = str(report_path)
            payload["resumeCommand"] = _resume_session_command_for_payload(report_path, payload)
            try:
                _write_json_report(report_path, payload)
            except OSError as error:
                return _print_error(
                    "session_report_unwritable",
                    str(error),
                    ["Choose a writable --session-report path, then rerun play-session."],
                )
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return return_code
    if args.command == "live-session":
        try:
            payload, return_code = _live_session_payload(args)
        except (OSError, UnicodeError) as error:
            return _print_error(
                "capture_log_unreadable",
                str(error),
                ["Check the log path/encoding or rerun live-session with --record-clipboard."],
            )
        except RuntimeError as error:
            return _print_error(
                "clipboard_unavailable",
                str(error),
                ["Run live-session clipboard recording on Windows with a clipboard-capable desktop session."],
            )
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return return_code
    if args.command == "watch-clipboard":
        project_root = Path(args.project_root)
        state_path = project_root / "translation-state.json"
        if not state_path.is_file():
            return _print_error(
                "translation_state_missing",
                f"translation state not found: {state_path}",
                ["Run import/capture-log and apply-result before watch-clipboard."],
            )
        runtime = _runtime_for_state(state_path, reload_enabled=not args.no_reload)
        clipboard_input = ClipboardRuntimeInput(WindowsClipboardProvider())
        event_log_path = None
        if not args.no_log:
            event_log_path = Path(args.event_log) if args.event_log else project_root / "logs" / "runtime-events.jsonl"
            event_log_path.parent.mkdir(parents=True, exist_ok=True)
        emitted = 0
        while True:
            event = clipboard_input.poll_once()
            if event is not None:
                display = runtime.display_for(event.raw_text)
                miss_logged = False
                if args.miss_log and not display.text:
                    miss_logged = _append_miss_log_line(Path(args.miss_log), event.raw_text)
                payload = _clipboard_runtime_event_payload(event.raw_text, display, args.include_source, miss_logged=miss_logged)
                line = json.dumps(payload, ensure_ascii=False)
                print(line, flush=True)
                if event_log_path is not None:
                    _append_jsonl_line(event_log_path, line)
                emitted += 1
                if args.max_events and emitted >= args.max_events:
                    break
            if args.once:
                break
            time.sleep(max(0.05, args.interval))
        return 0
    if args.command == "subtitle-window":
        state_path = Path(args.project_root) / "translation-state.json"
        if not state_path.is_file():
            return _print_error(
                "translation_state_missing",
                f"translation state not found: {state_path}",
                ["Run import/capture-log and apply-result before subtitle-window."],
            )
        records = _translation_records_from_state(state_path)
        runtime = _runtime_for_state(state_path, reload_enabled=not args.no_reload, initial_records=records)
        config_path = Path(args.config) if args.config else None
        loaded_config = None
        if config_path is not None:
            try:
                loaded_config = _load_subtitle_window_config(config_path)
            except (OSError, json.JSONDecodeError, TypeError) as error:
                return _print_error(
                    "subtitle_config_invalid",
                    f"subtitle config could not be loaded: {config_path}: {error}",
                    ["Fix or remove --config, then rerun subtitle-window."],
                )
        config = _subtitle_config_from_args(args, loaded_config)
        saved_config_path = None
        if args.save_config:
            saved_config_path = Path(args.save_config)
            try:
                _write_subtitle_window_config(saved_config_path, config)
            except OSError as error:
                return _print_error(
                    "subtitle_config_write_failed",
                    f"subtitle config could not be written: {saved_config_path}: {error}",
                    ["Check the output path permissions, then rerun subtitle-window --save-config."],
                )
        if args.dry_run:
            event_log_path = None
            if not args.no_log:
                event_log_path = Path(args.event_log) if args.event_log else Path(args.project_root) / "logs" / "runtime-events.jsonl"
            preview = None
            if args.preview_source:
                preview = _clipboard_runtime_event_payload(
                    args.preview_source,
                    runtime.display_for(args.preview_source),
                    include_source=args.include_source,
                    miss_logged=False,
                )
            print(
                json.dumps(
                    {
                        "status": "ready",
                        "projectRoot": str(Path(args.project_root)),
                        "recordCount": len(records),
                        "config": _subtitle_window_config_payload(config),
                        "configPath": str(config_path) if config_path is not None else None,
                        "savedConfigPath": str(saved_config_path) if saved_config_path is not None else None,
                        "input": _subtitle_input_payload(
                            source_log=args.source_log,
                            source_log_encoding=args.source_log_encoding,
                            source_log_name=args.source_log_name,
                            source_log_from_start=args.source_log_from_start,
                        ),
                        "reloadEnabled": not args.no_reload,
                        "eventLogEnabled": not args.no_log,
                        "eventLogPath": str(event_log_path) if event_log_path is not None else None,
                        "missLogPath": str(Path(args.miss_log)) if args.miss_log else None,
                        "preview": preview,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0
        event_logger = None
        if not args.no_log:
            event_log_path = Path(args.event_log) if args.event_log else Path(args.project_root) / "logs" / "runtime-events.jsonl"

            def event_logger(raw_text: str, state: Any) -> None:
                miss_logged = False
                if args.miss_log and not state.text:
                    miss_logged = _append_miss_log_line(Path(args.miss_log), raw_text)
                _append_jsonl_line(
                    event_log_path,
                    json.dumps(
                        _subtitle_runtime_event_payload(raw_text, state, args.include_source, miss_logged=miss_logged),
                        ensure_ascii=False,
                    ),
                )

        elif args.miss_log:
            def event_logger(raw_text: str, state: Any) -> None:
                if not state.text:
                    _append_miss_log_line(Path(args.miss_log), raw_text)

        runtime_input = _subtitle_runtime_input(
            source_log=args.source_log,
            source_log_encoding=args.source_log_encoding,
            source_log_name=args.source_log_name,
            source_log_from_start=args.source_log_from_start,
        )
        window = SubtitleWindow(
            runtime=runtime,
            clipboard_provider=None if runtime_input is not None else WindowsClipboardProvider(),
            config=config,
            event_logger=event_logger,
            initial_source_text=args.preview_source,
            runtime_input=runtime_input,
        )
        window.run()
        return 0

    parser.error(f"unknown command: {args.command}")
    return 2


def _scan_payload(report: ScanReport, candidates: list[EngineCandidate]) -> dict[str, Any]:
    return {
        "inputPath": str(report.input_path),
        "gameRoot": str(report.game_root),
        "inputWasExe": report.input_was_exe,
        "fileCount": len(report.files),
        "directories": list(report.directories),
        "extensionCounts": {
            extension: len(files) for extension, files in report.files_by_extension.items()
        },
        "archiveDiagnostics": [_archive_payload(diagnostic) for diagnostic in report.archive_diagnostics],
        "engineCandidates": [_candidate_payload(candidate) for candidate in candidates],
        "nextActions": _scan_next_actions(report, candidates),
        "files": [_file_payload(file) for file in report.files],
    }


def _doctor_payload(workspace: Path) -> dict[str, Any]:
    checks = {
        "pythonVersion": sys.version.split()[0],
        "platform": sys.platform,
        "codexOnPath": shutil.which("codex") is not None,
        "tkinterImportable": _can_import_tkinter(),
        "workspaceWritable": _workspace_writable(workspace),
    }
    return {
        "status": "ready" if all(checks.values()) else "partial",
        "checks": checks,
        "workspace": str(workspace),
    }


def _error_payload(code: str, message: str, next_actions: list[str]) -> dict[str, Any]:
    return {
        "status": "error",
        "error": {
            "code": code,
            "message": message,
        },
        "nextActions": next_actions,
    }


def _print_error(code: str, message: str, next_actions: list[str]) -> int:
    print(json.dumps(_error_payload(code, message, next_actions), ensure_ascii=False, indent=2))
    return 1


def _can_import_tkinter() -> bool:
    try:
        import tkinter  # noqa: F401
    except Exception:
        return False
    return True


def _scan_next_actions(report: ScanReport, candidates: list[EngineCandidate]) -> list[str]:
    if not candidates:
        return [
            "Run capture-log with a Textractor/clipboard log, or inspect the game manually and add a local extractor profile."
        ]

    candidate_ids = [candidate.engine_id for candidate in candidates]
    if "direct_script" in candidate_ids:
        return [
            "Run import with this exe/folder and a workspace.",
            "Then run progress, prepare-codex or run-codex, apply-result, and lookup/watch-clipboard.",
        ]
    if "pf8_pfs_ast" in candidate_ids:
        return [
            "Run archive-list --scripts-only to inspect PFS/pf8 script entries.",
            "PFS/pf8 extraction is diagnostic-only for encrypted/non-plaintext payloads; use capture-log with Textractor/clipboard logs for translation.",
        ]
    if report.archive_diagnostics:
        return [
            "Archive diagnostics are available, but no supported importer matched. Use capture-log fallback unless a verified extractor is provided."
        ]
    return ["Use capture-log fallback or add a verified extractor profile."]


def _project_info_payload(project_root: Path) -> dict[str, Any]:
    project_json_path = project_root / "project.json"
    scan_report_path = project_root / "scan-report.json"
    story_entries_path = project_root / "story-entries.json"
    state_path = project_root / "translation-state.json"
    diagnostics: list[dict[str, Any]] = []
    project_payload = _read_json_file(project_json_path, diagnostics=diagnostics, label="project")
    scan_payload = _read_json_file(scan_report_path, diagnostics=diagnostics, label="scanReport")
    story_entries = _read_json_file(story_entries_path, default=[], diagnostics=diagnostics, label="storyEntries")
    summary = None
    if state_path.is_file():
        try:
            summary = _summary_payload(TranslationProgressTracker(state_path).summary())
        except (OSError, json.JSONDecodeError, KeyError, TypeError) as error:
            diagnostics.append(_file_diagnostic("json_invalid", state_path, "translationState", error))

    return {
        "projectRoot": str(project_root),
        "project": project_payload,
        "hasProjectJson": project_json_path.is_file(),
        "hasScanReport": scan_report_path.is_file(),
        "storyEntryCount": len(story_entries) if isinstance(story_entries, list) else 0,
        "progress": summary,
        "runtime": _runtime_info_payload(project_root),
        "translationLock": _translation_lock_info(project_root),
        "failedRetry": _failed_retry_info_payload(project_root),
        "latestCodexBatch": _latest_codex_batch_payload(project_root, diagnostics),
        "diagnostics": diagnostics,
        "nextActions": _project_next_actions(project_root, summary),
    }


def _session_info_payload(report_path: Path) -> dict[str, Any]:
    if not report_path.is_file():
        raise FileNotFoundError(f"session report not found: {report_path}")
    report = json.loads(report_path.read_text(encoding="utf-8-sig"))
    if not isinstance(report, dict):
        raise TypeError("session report must be a JSON object")

    session_payload = report.get("session") if isinstance(report.get("session"), dict) else report
    if not isinstance(session_payload, dict):
        session_payload = {}
    source_log_report = _is_source_log_session_report(report)
    report_type = "source-log-session" if source_log_report else ("live-session" if "session" in report else "play-session")
    if not session_payload.get("sessionSummary"):
        report_type = "unknown"
    if source_log_report:
        report_type = "source-log-session"

    summary = session_payload.get("sessionSummary") if isinstance(session_payload.get("sessionSummary"), dict) else {}
    project_root_text = _session_report_project_root(report, session_payload, summary)
    session_log_text = _session_report_session_log_path(report, session_payload)
    subtitle_payload = session_payload.get("subtitleWindow") if isinstance(session_payload.get("subtitleWindow"), dict) else {}
    session_log_source_name = _session_report_source_name(session_payload, subtitle_payload)
    session_log_encoding = _session_report_log_encoding(subtitle_payload)
    miss_log_text = _session_report_miss_log_path(summary, subtitle_payload)
    if source_log_report:
        subtitle_payload = report.get("subtitleWindow") if isinstance(report.get("subtitleWindow"), dict) else subtitle_payload
        session_log_text = str(report.get("sourceLog")) if isinstance(report.get("sourceLog"), str) and report.get("sourceLog") else session_log_text
        session_log_source_name = str(report.get("sourceName")) if isinstance(report.get("sourceName"), str) and report.get("sourceName") else session_log_source_name
        miss_log_text = str(report.get("missLog")) if isinstance(report.get("missLog"), str) and report.get("missLog") else miss_log_text
    subtitle_command = summary.get("subtitleCommand") or subtitle_payload.get("command")
    if not subtitle_command:
        subtitle_command = _default_resume_subtitle_window_command(
            project_root_text,
            session_log_text,
            session_log_source_name,
            session_log_encoding,
        )
    project_info = _project_info_payload(Path(project_root_text)) if project_root_text and Path(project_root_text).exists() else None
    translate_options = _session_resume_translation_options_from_summary(summary)
    translate_miss_command = summary.get("translateMissLogCommand") or _translate_miss_log_command(
        project_root_text,
        miss_log_text,
        batch_size=translate_options["batch_size"],
        model=translate_options["model"],
        timeout=translate_options["timeout"],
        max_batches=translate_options["max_batches"],
    )
    report_miss_watcher_command = _watcher_command_from_report(report.get("missWatcher"))
    source_log_watcher_saved = report.get("watcher") if source_log_report else None
    report_session_log_watcher_command = _watcher_command_from_report(source_log_watcher_saved) or _watcher_command_from_report(report.get("sessionLogWatcher"))
    watch_miss_command = report_miss_watcher_command or summary.get("watchMissLogCommand") or _watch_miss_log_command(
        project_root_text,
        miss_log_text,
        batch_size=translate_options["batch_size"],
        model=translate_options["model"],
        timeout=translate_options["timeout"],
        max_batches=translate_options["max_batches"],
    )
    translate_session_log_command = summary.get("translateSessionLogCommand") or _translate_log_command(
        project_root_text,
        session_log_text,
        source_name=session_log_source_name,
        batch_size=translate_options["batch_size"],
        model=translate_options["model"],
        timeout=translate_options["timeout"],
        max_batches=translate_options["max_batches"],
    )
    watch_session_log_command = report_session_log_watcher_command or summary.get("watchSessionLogCommand") or _watch_log_command(
        project_root_text,
        session_log_text,
        source_name=session_log_source_name,
        batch_size=translate_options["batch_size"],
        model=translate_options["model"],
        timeout=translate_options["timeout"],
        max_batches=translate_options["max_batches"],
    )
    commands = {
        "projectInfoCommand": [sys.executable, "-m", "gal_translator", "project-info", project_root_text] if project_root_text else None,
        "resumeSessionCommand": _resume_session_command(
            report_path,
            summary,
            subtitle_command=subtitle_command,
            watch_miss_log_command=watch_miss_command,
            watch_session_log_command=watch_session_log_command,
        ),
        "translateAllCommand": _translate_all_command(Path(project_root_text), translate_options) if project_root_text else None,
        "retryFailedCommand": [sys.executable, "-m", "gal_translator", "retry-failed", project_root_text] if project_root_text else None,
        "clearLockCommand": [sys.executable, "-m", "gal_translator", "clear-lock", project_root_text] if project_root_text else None,
        "inspectLogCommand": _inspect_log_command(session_log_text, session_log_source_name, session_log_encoding),
        "appendSessionLogCommand": _append_session_log_command(project_root_text, session_log_text, session_log_source_name, session_log_encoding),
        "subtitleWindowCommand": subtitle_command,
        "translateMissLogCommand": translate_miss_command,
        "watchMissLogCommand": watch_miss_command,
        "translateSessionLogCommand": translate_session_log_command,
        "watchSessionLogCommand": watch_session_log_command,
    }
    if source_log_report and isinstance(report.get("restartCommand"), list):
        commands["sourceLogSessionRestartCommand"] = [str(part) for part in report["restartCommand"]]
        commands["sourceLogSessionCommand"] = _source_log_session_command_from_report(report)
    if source_log_report and isinstance(report.get("clipboardBridge"), dict):
        bridge_command = _watcher_command_from_report(report.get("clipboardBridge"))
        if bridge_command:
            commands["clipboardBridgeCommand"] = bridge_command
    if source_log_report and isinstance(report.get("lunaHookBridge"), dict):
        luna_hook_bridge_command = _watcher_command_from_report(report.get("lunaHookBridge"))
        if luna_hook_bridge_command:
            commands["lunaHookBridgeCommand"] = luna_hook_bridge_command
    miss_watcher = _session_miss_watcher_payload(report.get("missWatcher"))
    session_log_watcher = _session_miss_watcher_payload(source_log_watcher_saved) or _session_miss_watcher_payload(report.get("sessionLogWatcher"))
    payload = {
        "reportPath": str(report_path),
        "reportType": report_type,
        "reportSessionReportPath": report.get("sessionReportPath") or session_payload.get("sessionReportPath"),
        "sessionSummary": summary,
        "projectRoot": project_root_text,
        "projectExists": bool(project_root_text and Path(project_root_text).exists()),
        "sessionLogPath": session_log_text,
        "sessionLogExists": bool(session_log_text and Path(session_log_text).is_file()),
        "sessionLogInspection": _session_log_inspection_payload(session_log_text, session_log_source_name, session_log_encoding),
        "subtitleWindow": _session_process_payload(subtitle_payload) if subtitle_payload else None,
        "clipboardBridge": _session_process_payload(report.get("clipboardBridge")) if source_log_report else None,
        "lunaHookBridge": _session_process_payload(report.get("lunaHookBridge")) if source_log_report else None,
        "missWatcher": miss_watcher,
        "sessionLogWatcher": session_log_watcher,
        "currentProjectInfo": project_info,
        "commands": commands,
    }
    if source_log_report and isinstance(payload.get("subtitleWindow"), dict) and report.get("eventLog"):
        event_log_path = Path(str(report["eventLog"]))
        payload["subtitleWindow"]["eventLog"] = _session_log_file_payload(event_log_path, parse_jsonl=True)
    payload["nextActions"] = _session_info_next_actions(payload)
    return payload


def _source_log_status_payload(
    project_root: Path,
    source_log: Path,
    session_report: Path | None,
    source_name: str,
    encoding: str,
    game_processes: list[str],
    hook_processes: list[str],
) -> dict[str, Any]:
    project_info = _project_info_payload(project_root) if project_root.exists() else None
    session_info = None
    session_error = None
    if session_report is not None:
        try:
            session_info = _session_info_payload(session_report)
        except (FileNotFoundError, OSError, json.JSONDecodeError, TypeError) as error:
            session_error = str(error)

    default_hook_processes = [
        "LunaTranslator.exe",
        "LunaTranslator_admin.exe",
        "Textractor.exe",
        "TextractorCLI.exe",
    ]
    hook_names = hook_processes or default_hook_processes
    process_checks = {
        "game": _process_name_checks(game_processes),
        "hook": _process_name_checks(hook_names),
    }
    inspection = _session_log_inspection_payload(str(source_log), source_name, encoding)
    watcher = _source_log_status_watcher(session_info)
    subtitle = _source_log_status_subtitle(session_info)
    clipboard_bridge = _source_log_status_clipboard_bridge(session_info)
    luna_hook_bridge = _source_log_status_luna_hook_bridge(session_info)
    progress = project_info.get("progress") if isinstance(project_info, dict) else None
    payload: dict[str, Any] = {
        "status": _source_log_status_label(project_root, project_info, inspection, watcher, subtitle),
        "mode": "paused_full_archive_scoped_source_log",
        "pausedFullArchive": True,
        "projectRoot": str(project_root),
        "projectExists": project_root.exists(),
        "sourceLog": str(source_log),
        "sourceName": source_name,
        "encoding": encoding,
        "progress": progress,
        "translationLock": project_info.get("translationLock") if isinstance(project_info, dict) else None,
        "sourceLogInspection": inspection,
        "processChecks": process_checks,
        "sessionReport": str(session_report) if session_report is not None else None,
        "sessionReportError": session_error,
        "sourceLogWatcher": watcher,
        "subtitleWindow": subtitle,
        "clipboardBridge": clipboard_bridge,
        "lunaHookBridge": luna_hook_bridge,
    }
    payload["closedLoopProof"] = _source_log_closed_loop_proof(payload)
    payload["nextActions"] = _source_log_status_next_actions(payload)
    return payload


def _source_log_status_watcher(session_info: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(session_info, dict):
        return None
    watcher = session_info.get("sessionLogWatcher")
    if not isinstance(watcher, dict):
        return None
    return {
        "currentProcessActive": watcher.get("currentProcessActive"),
        "started": watcher.get("started"),
        "pid": watcher.get("pid"),
        "statusSummary": watcher.get("statusSummary"),
    }


def _source_log_status_subtitle(session_info: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(session_info, dict):
        return None
    subtitle = session_info.get("subtitleWindow")
    if not isinstance(subtitle, dict):
        return None
    return {
        "currentProcessActive": subtitle.get("currentProcessActive"),
        "started": subtitle.get("started"),
        "pid": subtitle.get("pid"),
        "eventLog": subtitle.get("eventLog") if isinstance(subtitle.get("eventLog"), dict) else None,
    }


def _source_log_status_clipboard_bridge(session_info: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(session_info, dict):
        return None
    bridge = session_info.get("clipboardBridge")
    if not isinstance(bridge, dict):
        return None
    return {
        "currentProcessActive": bridge.get("currentProcessActive"),
        "started": bridge.get("started"),
        "enabled": bridge.get("enabled"),
        "pid": bridge.get("pid"),
    }


def _source_log_status_luna_hook_bridge(session_info: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(session_info, dict):
        return None
    bridge = session_info.get("lunaHookBridge")
    if not isinstance(bridge, dict):
        return None
    status_log = bridge.get("statusLog") if isinstance(bridge.get("statusLog"), dict) else None
    game_pid = bridge.get("gamePid")
    game_process_active = _process_is_running(game_pid) if isinstance(game_pid, int) else None
    return {
        "currentProcessActive": bridge.get("currentProcessActive"),
        "started": bridge.get("started"),
        "enabled": bridge.get("enabled"),
        "pid": bridge.get("pid"),
        "gamePid": game_pid,
        "gameProcessActive": game_process_active,
        "statusLog": status_log,
    }


def _source_log_closed_loop_proof(payload: dict[str, Any]) -> dict[str, Any]:
    inspection = payload.get("sourceLogInspection") if isinstance(payload.get("sourceLogInspection"), dict) else {}
    watcher = payload.get("sourceLogWatcher") if isinstance(payload.get("sourceLogWatcher"), dict) else {}
    watcher_summary = watcher.get("statusSummary") if isinstance(watcher.get("statusSummary"), dict) else {}
    subtitle = payload.get("subtitleWindow") if isinstance(payload.get("subtitleWindow"), dict) else {}
    subtitle_event_log = subtitle.get("eventLog") if isinstance(subtitle.get("eventLog"), dict) else {}
    subtitle_event = subtitle_event_log.get("lastEvent") if isinstance(subtitle_event_log.get("lastEvent"), dict) else {}
    luna_hook = payload.get("lunaHookBridge") if isinstance(payload.get("lunaHookBridge"), dict) else {}
    luna_status_log = luna_hook.get("statusLog") if isinstance(luna_hook.get("statusLog"), dict) else {}
    hook_event = luna_status_log.get("lastEvent") if isinstance(luna_status_log.get("lastEvent"), dict) else {}

    latest_source = inspection.get("lastImportedSource") if isinstance(inspection.get("lastImportedSource"), str) else None
    latest_hook_text = hook_event.get("text") if isinstance(hook_event.get("text"), str) else None
    subtitle_text = subtitle_event.get("text") if isinstance(subtitle_event.get("text"), str) else None
    subtitle_match_type = subtitle_event.get("matchType") if isinstance(subtitle_event.get("matchType"), str) else None
    subtitle_visible = subtitle_event.get("visible") if isinstance(subtitle_event.get("visible"), bool) else None
    subtitle_miss_logged = subtitle_event.get("missLogged") if isinstance(subtitle_event.get("missLogged"), bool) else None

    proof_status = "not_ready"
    if watcher.get("currentProcessActive") is not True:
        proof_status = "watcher_inactive"
    elif luna_hook.get("enabled") and luna_hook.get("gameProcessActive") is False:
        proof_status = "hook_game_inactive"
    elif subtitle.get("currentProcessActive") is not True:
        proof_status = "subtitle_inactive"
    elif not latest_source:
        proof_status = "waiting_for_source"
    elif latest_hook_text and latest_hook_text != latest_source:
        proof_status = "source_log_behind_hook"
    elif subtitle_visible is True and subtitle_match_type == "exact":
        proof_status = "closed_loop_displayed"
    elif subtitle_miss_logged is True:
        proof_status = "subtitle_miss_logged"
    elif subtitle_event:
        proof_status = "subtitle_event_seen"
    else:
        proof_status = "waiting_for_subtitle_event"

    return {
        "status": proof_status,
        "latestSourceText": latest_source,
        "latestSourceEntryId": inspection.get("lastImportedEntryId"),
        "latestHookText": latest_hook_text,
        "sourceLogContainsLatestHook": (latest_hook_text == latest_source) if latest_hook_text and latest_source else None,
        "latestMatchedEntryIds": watcher_summary.get("lastProcessedLogEntryIds"),
        "lastProcessedCycle": watcher_summary.get("lastProcessedCycle"),
        "lastProcessedSessionStatus": watcher_summary.get("lastProcessedSessionStatus"),
        "subtitleText": subtitle_text,
        "subtitleMatchType": subtitle_match_type,
        "subtitleVisible": subtitle_visible,
        "subtitleMissLogged": subtitle_miss_logged,
        "watcherActive": watcher.get("currentProcessActive"),
        "subtitleActive": subtitle.get("currentProcessActive"),
        "lunaHookBridgeActive": luna_hook.get("currentProcessActive"),
        "lunaHookGameProcessActive": luna_hook.get("gameProcessActive"),
    }


def _source_log_status_label(
    project_root: Path,
    project_info: dict[str, Any] | None,
    inspection: dict[str, Any] | None,
    watcher: dict[str, Any] | None,
    subtitle: dict[str, Any] | None,
) -> str:
    if not project_root.exists() or project_info is None:
        return "project_missing"
    lock = project_info.get("translationLock") if isinstance(project_info.get("translationLock"), dict) else {}
    if lock.get("exists"):
        return "translation_locked"
    watcher_active = isinstance(watcher, dict) and watcher.get("currentProcessActive") is True
    subtitle_active = isinstance(subtitle, dict) and subtitle.get("currentProcessActive") is True
    has_source = isinstance(inspection, dict) and inspection.get("status") == "has_source"
    if watcher_active and subtitle_active:
        return "watching_source_log"
    if watcher_active:
        return "watcher_active"
    if has_source:
        return "source_log_ready"
    return "waiting_for_source_log"


def _source_log_status_next_actions(payload: dict[str, Any]) -> list[str]:
    actions: list[str] = []
    if payload.get("status") == "project_missing":
        return ["Restore or recreate the project, then rerun source-log-status."]

    progress = payload.get("progress") if isinstance(payload.get("progress"), dict) else {}
    pending = progress.get("pending")
    translated = progress.get("translated")
    total = progress.get("total")
    if isinstance(total, int) and isinstance(translated, int) and isinstance(pending, int):
        actions.append(
            f"Full archive translation remains paused at {translated}/{total} translated with {pending} pending; continue scoped source-log translation only."
        )

    game_checks = payload.get("processChecks", {}).get("game") if isinstance(payload.get("processChecks"), dict) else []
    if isinstance(game_checks, list) and game_checks and not any(
        check.get("running") for check in game_checks if isinstance(check, dict)
    ):
        names = ", ".join(str(check.get("name")) for check in game_checks if isinstance(check, dict) and check.get("name"))
        actions.append(f"Game process is not running ({names}); start the game before expecting new Hook captures.")

    lock = payload.get("translationLock") if isinstance(payload.get("translationLock"), dict) else {}
    if lock.get("exists"):
        actions.append("A translation lock is present; wait for the active scoped batch or clear only a confirmed stale lock.")

    inspection = payload.get("sourceLogInspection") if isinstance(payload.get("sourceLogInspection"), dict) else {}
    if inspection.get("status") == "has_source":
        stats = inspection.get("captureStats") if isinstance(inspection.get("captureStats"), dict) else {}
        actions.append(f"Source log currently has {stats.get('importedEntryCount', 0)} importable line(s).")
    elif inspection.get("status") == "missing":
        actions.append("Create or configure the source-log file so LunaHook/Textractor can append captured Japanese lines.")
    else:
        actions.append("Keep the Hook/Textractor output focused on Japanese story text; this source log has no importable story line yet.")

    watcher = payload.get("sourceLogWatcher") if isinstance(payload.get("sourceLogWatcher"), dict) else {}
    if watcher.get("currentProcessActive") is True:
        actions.append("The scoped source-log watcher is active; appended lines will be translated with --only-new-log-entries.")
    elif payload.get("sessionReport"):
        actions.append("Restart source-log-session.ps1 or watchSessionLogCommand from session-info to restore scoped background translation.")
    else:
        actions.append("Start source-log-session.ps1 with --only-new-log-entries semantics before playing.")

    subtitle = payload.get("subtitleWindow") if isinstance(payload.get("subtitleWindow"), dict) else {}
    if subtitle.get("currentProcessActive") is True:
        actions.append("The source-log subtitle window is active.")
    else:
        actions.append("Open subtitle-window against this same source log so matched translations display while playing.")

    bridge = payload.get("clipboardBridge") if isinstance(payload.get("clipboardBridge"), dict) else {}
    if bridge.get("currentProcessActive") is True:
        actions.append("The clipboard bridge is active; Hook/Textractor clipboard copies will be appended to the source log.")
    elif bridge.get("enabled"):
        actions.append("The saved clipboard bridge is not running; restart source-log-session with -StartClipboardBridge if Hook output is clipboard-only.")

    luna_hook_bridge = payload.get("lunaHookBridge") if isinstance(payload.get("lunaHookBridge"), dict) else {}
    if luna_hook_bridge.get("currentProcessActive") is True and luna_hook_bridge.get("gameProcessActive") is False:
        actions.append("The LunaHook bridge process is still running, but its target game pid is no longer active; restart the game and source-log session with -StartLunaHookBridge.")
    elif luna_hook_bridge.get("currentProcessActive") is True:
        actions.append("The LunaHook bridge is active; hooked game text will be appended to the source log.")
    elif luna_hook_bridge.get("enabled"):
        actions.append("The saved LunaHook bridge is not running; restart source-log-session with -StartLunaHookBridge after starting the game.")

    hook_checks = payload.get("processChecks", {}).get("hook") if isinstance(payload.get("processChecks"), dict) else []
    if (
        isinstance(hook_checks, list)
        and not any(check.get("running") for check in hook_checks if isinstance(check, dict))
        and not (isinstance(luna_hook_bridge, dict) and luna_hook_bridge.get("currentProcessActive") is True)
    ):
        actions.append("No known Hook/Textractor process is running; start LunaTranslator or Textractor and attach it to the game.")

    actions.append("Do not run translate-all for this paused full-archive project unless you intentionally want to spend tokens on all remaining entries.")
    return actions


def _process_name_checks(names: list[str]) -> list[dict[str, Any]]:
    return [{"name": name, **_process_name_check(name)} for name in names]


def _process_name_check(name: str) -> dict[str, Any]:
    matches = _processes_by_image_name(name)
    return {
        "running": bool(matches),
        "pids": [match["pid"] for match in matches],
    }


def _processes_by_image_name(name: str) -> list[dict[str, Any]]:
    normalized = name.casefold()
    if not normalized:
        return []
    if sys.platform == "win32":
        try:
            result = subprocess.run(
                ["tasklist", "/FO", "CSV", "/NH"],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except OSError:
            return []
        matches: list[dict[str, Any]] = []
        for row in csv.reader(io.StringIO(result.stdout)):
            if len(row) < 2 or row[0].casefold() != normalized:
                continue
            try:
                pid = int(row[1])
            except ValueError:
                continue
            matches.append({"pid": pid, "imageName": row[0]})
        return matches
    try:
        result = subprocess.run(
            ["ps", "-axo", "pid=,comm="],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError:
        return []
    matches = []
    for line in result.stdout.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        pid_text, _, command = stripped.partition(" ")
        image_name = Path(command.strip()).name
        if image_name.casefold() != normalized:
            continue
        try:
            pid = int(pid_text)
        except ValueError:
            continue
        matches.append({"pid": pid, "imageName": image_name})
    return matches


def _is_source_log_session_report(report: dict[str, Any]) -> bool:
    return (
        isinstance(report.get("sourceLog"), str)
        and isinstance(report.get("watcher"), dict)
        and isinstance(report.get("subtitleWindow"), dict)
    )


def _source_log_session_command_from_report(report: dict[str, Any]) -> list[str] | None:
    command = report.get("restartCommand")
    if not isinstance(command, list) or not command:
        return None
    stripped_switches = {"-DryRun", "-NoWatcher", "-NoSubtitle"}
    return [str(part) for part in command if str(part) not in stripped_switches]


def _resume_session_payload(
    report_path: Path,
    dry_run: bool,
    open_subtitle: bool,
    start_miss_watcher: bool,
    start_session_log_watcher: bool,
    subtitle_foreground: bool,
    retry_failed: bool,
) -> tuple[dict[str, Any], int]:
    info = _session_info_payload(report_path)
    payload: dict[str, Any] = {
        "reportPath": str(report_path),
        "dryRun": dry_run,
        "openSubtitle": open_subtitle,
        "startMissWatcher": start_miss_watcher,
        "startSessionLogWatcher": start_session_log_watcher,
        "subtitleForeground": subtitle_foreground,
        "retryFailedRequested": retry_failed,
        "sessionInfo": info,
        "action": None,
        "status": "needs_attention",
        "retryFailed": None,
        "translateAll": None,
        "subtitleWindow": None,
        "missWatcher": None,
        "sessionLogWatcher": None,
        "appendLog": None,
    }
    project_root_text = info.get("projectRoot")
    project_root = Path(project_root_text) if isinstance(project_root_text, str) and project_root_text else None
    project_info = info.get("currentProjectInfo") if isinstance(info.get("currentProjectInfo"), dict) else None
    if project_root is None or not info.get("projectExists") or project_info is None:
        payload["nextActions"] = info.get("nextActions", [])
        return payload, 1

    lock = project_info.get("translationLock") if isinstance(project_info.get("translationLock"), dict) else {}
    if lock.get("exists"):
        payload["status"] = "translation_locked"
        payload["nextActions"] = info.get("nextActions", [])
        return payload, 1

    progress = project_info.get("progress") if isinstance(project_info.get("progress"), dict) else None
    if progress is None:
        payload["status"] = "project_needs_repair"
        payload["nextActions"] = info.get("nextActions", [])
        return payload, 1
    if progress.get("total", 0) == 0:
        inspection = info.get("sessionLogInspection") if isinstance(info.get("sessionLogInspection"), dict) else {}
        commands = info.get("commands") if isinstance(info.get("commands"), dict) else {}
        append_command = commands.get("appendSessionLogCommand")
        if inspection.get("status") == "has_source" and append_command:
            payload["action"] = "append-log"
            payload["command"] = append_command
            if dry_run:
                payload["status"] = "append_log_planned"
                payload["nextActions"] = ["Rerun resume-session without --dry-run to append the saved session log, then translate pending entries."]
                return payload, 0
            append_payload, append_error = _resume_append_session_log_payload(info, project_root)
            if append_error is not None:
                payload["status"] = "append_log_failed"
                payload["appendLog"] = append_payload
                payload["nextActions"] = append_error
                return payload, 1
            payload["appendLog"] = append_payload
            refreshed_info = _session_info_payload(report_path)
            payload["sessionInfo"] = refreshed_info
            info = refreshed_info
            project_info = info.get("currentProjectInfo") if isinstance(info.get("currentProjectInfo"), dict) else None
            progress = project_info.get("progress") if isinstance(project_info, dict) and isinstance(project_info.get("progress"), dict) else None
            if progress is None:
                payload["status"] = "project_needs_repair"
                payload["nextActions"] = info.get("nextActions", [])
                return payload, 1
            if progress.get("total", 0) == 0:
                payload["status"] = "no_source_text"
                payload["nextActions"] = info.get("nextActions", [])
                return payload, 0
        else:
            payload["status"] = "no_source_text"
            payload["nextActions"] = info.get("nextActions", [])
            return payload, 0
    if progress.get("failed", 0) > 0:
        commands = info.get("commands") if isinstance(info.get("commands"), dict) else {}
        retry_command = commands.get("retryFailedCommand") or [sys.executable, "-m", "gal_translator", "retry-failed", str(project_root)]
        payload["action"] = "retry-failed"
        payload["command"] = retry_command
        if not retry_failed:
            payload["status"] = "failed_entries"
            payload["nextActions"] = [
                "Review failed entries and latestCodexBatch diagnostics, then rerun resume-session with --retry-failed to reset them before translating again."
            ] + list(info.get("nextActions", []))
            return payload, 1
        if dry_run:
            retry_summary = TranslationProgressTracker(project_root / "translation-state.json").preview_reset_failed()
            payload["status"] = "retry_failed_planned"
            payload["retryFailedPreview"] = retry_summary.to_payload()
            payload["nextActions"] = retry_summary.next_actions or [
                "Rerun resume-session --retry-failed without --dry-run to reset failed entries and continue translation."
            ]
            return payload, 0
        tracker = TranslationProgressTracker(project_root / "translation-state.json")
        retry_summary = tracker.reset_failed_summary()
        payload["retryFailed"] = {
            "projectRoot": str(project_root),
            **retry_summary.to_payload(),
            "progress": _project_progress_payload(project_root),
            "command": retry_command,
        }
        refreshed_info = _session_info_payload(report_path)
        payload["sessionInfo"] = refreshed_info
        info = refreshed_info
        project_info = info.get("currentProjectInfo") if isinstance(info.get("currentProjectInfo"), dict) else None
        progress = project_info.get("progress") if isinstance(project_info, dict) and isinstance(project_info.get("progress"), dict) else None
        if progress is None:
            payload["status"] = "project_needs_repair"
            payload["nextActions"] = info.get("nextActions", [])
            return payload, 1
        if progress.get("failed", 0) > 0:
            payload["status"] = "failed_entries"
            payload["nextActions"] = info.get("nextActions", [])
            return payload, 1
    if progress.get("pending", 0) > 0:
        options = _session_resume_translation_options(info)
        command = _translate_all_command(project_root, options)
        payload["action"] = "translate-all"
        payload["command"] = command
        if dry_run:
            payload["status"] = "translation_planned"
            payload["nextActions"] = ["Rerun resume-session without --dry-run to translate pending entries."]
            return payload, 0
        translate_payload, return_code = _translate_all_payload(
            project_root=project_root,
            batch_size=options["batch_size"],
            model=options["model"],
            max_batches=options["max_batches"],
            timeout=options["timeout"],
            dry_run=False,
            retry_failed=bool(options.get("retry_failed")),
        )
        payload["translateAll"] = translate_payload
        refreshed_info = _session_info_payload(report_path)
        payload["sessionInfo"] = refreshed_info
        refreshed_project = refreshed_info.get("currentProjectInfo") if isinstance(refreshed_info.get("currentProjectInfo"), dict) else {}
        refreshed_progress = refreshed_project.get("progress") if isinstance(refreshed_project.get("progress"), dict) else {}
        if return_code != 0 or refreshed_progress.get("pending", 0) > 0 or refreshed_progress.get("failed", 0) > 0:
            payload["status"] = "translation_needs_attention"
            payload["nextActions"] = translate_payload.get("nextActions") or refreshed_info.get("nextActions", [])
            return payload, return_code or 1
        info = refreshed_info

    commands = info.get("commands") if isinstance(info.get("commands"), dict) else {}
    subtitle_command = commands.get("subtitleWindowCommand")
    watcher_payload, watcher_actions, watcher_return_code = _resume_session_miss_watcher_payload(
        info,
        project_root,
        dry_run=dry_run,
        start_miss_watcher=start_miss_watcher,
    )
    payload["missWatcher"] = watcher_payload
    session_log_watcher_payload, session_log_watcher_actions, session_log_watcher_return_code = _resume_session_log_watcher_payload(
        info,
        project_root,
        dry_run=dry_run,
        start_session_log_watcher=start_session_log_watcher,
    )
    payload["sessionLogWatcher"] = session_log_watcher_payload
    watcher_actions = watcher_actions + session_log_watcher_actions
    watcher_return_code = watcher_return_code or session_log_watcher_return_code
    if not open_subtitle:
        payload["status"] = "subtitle_ready" if subtitle_command else "translation_ready"
        if payload.get("action") is None:
            payload["action"] = "subtitle-window" if subtitle_command else None
            payload["command"] = subtitle_command
        next_actions = [
            "Rerun resume-session with --open-subtitle to start the saved subtitle window."
        ] if subtitle_command else ["Run subtitle-window for this project, or rerun play-session/live-session with subtitle options."]
        payload["nextActions"] = next_actions + watcher_actions
        if watcher_return_code != 0:
            payload["status"] = "watcher_failed"
            return payload, watcher_return_code
        return payload, 0
    if not subtitle_command:
        payload["status"] = "subtitle_command_missing"
        payload["nextActions"] = ["Run subtitle-window for this project, or rerun play-session/live-session with subtitle options."] + watcher_actions
        return payload, watcher_return_code or 1

    payload["action"] = "subtitle-window"
    payload["command"] = subtitle_command
    if dry_run:
        payload["status"] = "subtitle_planned"
        payload["nextActions"] = ["Rerun resume-session --open-subtitle without --dry-run to start the subtitle window."] + watcher_actions
        return payload, 0
    if subtitle_foreground:
        completed = subprocess.run([str(part) for part in subtitle_command], check=False)
        payload["subtitleWindow"] = {
            "started": completed.returncode == 0,
            "detached": False,
            "returnCode": completed.returncode,
            "command": subtitle_command,
        }
        payload["status"] = "subtitle_exited" if completed.returncode != 0 else "subtitle_finished"
        payload["nextActions"] = ["Review subtitle-window output and rerun resume-session if needed."] + watcher_actions
        return payload, completed.returncode or watcher_return_code

    detached = _start_detached_subtitle_window(
        [str(part) for part in subtitle_command],
        cwd=Path.cwd(),
        log_dir=project_root / "logs" / "subtitle-window",
    )
    payload["subtitleWindow"] = {**detached, "command": subtitle_command, "started": True, "detached": True}
    if detached.get("detachedRunning", True):
        payload["status"] = "subtitle_started"
        payload["nextActions"] = ["Keep playing with the detached subtitle window open."] + watcher_actions
        return payload, watcher_return_code
    payload["status"] = "subtitle_exited"
    payload["nextActions"] = ["Detached subtitle-window exited immediately; review detached stdout/stderr logs in subtitleWindow."] + watcher_actions
    return payload, 1


def _resume_session_miss_watcher_payload(
    info: dict[str, Any],
    project_root: Path,
    dry_run: bool,
    start_miss_watcher: bool,
) -> tuple[dict[str, Any] | None, list[str], int]:
    commands = info.get("commands") if isinstance(info.get("commands"), dict) else {}
    watch_command = commands.get("watchMissLogCommand")
    if not start_miss_watcher:
        if watch_command:
            return None, ["Add --start-miss-watcher to resume the saved miss-log translation loop."], 0
        return None, [], 0
    if not watch_command:
        return (
            {
                "started": False,
                "dryRun": dry_run,
                "reason": "watchMissLogCommand missing",
                "command": None,
            },
            ["No saved watchMissLogCommand is available; rerun play-session/live-session with --subtitle-miss-log."],
            1,
        )
    payload: dict[str, Any] = {
        "started": False,
        "dryRun": dry_run,
        "command": watch_command,
    }
    if dry_run:
        return payload, ["Rerun resume-session with --start-miss-watcher without --dry-run to start miss-log translation."], 0
    detached = _start_detached_subtitle_window(
        [str(part) for part in watch_command],
        cwd=Path.cwd(),
        log_dir=project_root / "logs" / "miss-watcher",
    )
    payload.update(detached)
    payload["started"] = True
    if detached.get("detachedRunning", True):
        return payload, ["Miss-log watcher started; runtime misses will be translated in the background."], 0
    return payload, ["Miss-log watcher exited immediately; review missWatcher detached stdout/stderr logs."], 1


def _resume_session_log_watcher_payload(
    info: dict[str, Any],
    project_root: Path,
    dry_run: bool,
    start_session_log_watcher: bool,
) -> tuple[dict[str, Any] | None, list[str], int]:
    commands = info.get("commands") if isinstance(info.get("commands"), dict) else {}
    watch_command = commands.get("watchSessionLogCommand")
    if not start_session_log_watcher:
        if watch_command:
            return None, ["Add --start-session-log-watcher to resume translation of newly appended session-log lines."], 0
        return None, [], 0
    if not watch_command:
        return (
            {
                "started": False,
                "dryRun": dry_run,
                "reason": "watchSessionLogCommand missing",
                "command": None,
            },
            ["No saved watchSessionLogCommand is available; rerun play-session/live-session with --subtitle-source-log."],
            1,
        )
    payload: dict[str, Any] = {
        "started": False,
        "dryRun": dry_run,
        "command": watch_command,
    }
    if dry_run:
        return payload, ["Rerun resume-session with --start-session-log-watcher without --dry-run to start session-log translation."], 0
    detached = _start_detached_subtitle_window(
        [str(part) for part in watch_command],
        cwd=Path.cwd(),
        log_dir=project_root / "logs" / "session-log-watcher",
    )
    payload.update(detached)
    payload["started"] = True
    if detached.get("detachedRunning", True):
        return payload, ["Session-log watcher started; appended source-log lines will be translated in the background."], 0
    return payload, ["Session-log watcher exited immediately; review sessionLogWatcher detached stdout/stderr logs."], 1


def _session_resume_translation_options(info: dict[str, Any]) -> dict[str, Any]:
    summary = info.get("sessionSummary") if isinstance(info.get("sessionSummary"), dict) else {}
    return _session_resume_translation_options_from_summary(summary)


def _session_resume_translation_options_from_summary(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "batch_size": max(1, int(summary.get("batchSize", 40) or 40)),
        "model": str(summary.get("model", "gpt-5.5") or "gpt-5.5"),
        "timeout": max(0, int(summary.get("translateTimeout", 0) or 0)),
        "max_batches": max(0, int(summary.get("translateMaxBatches", 0) or 0)),
        "retry_failed": bool(summary.get("translateRetryFailed")),
    }


def _translate_all_command(project_root: Path, options: dict[str, Any]) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "gal_translator",
        "translate-all",
        str(project_root),
        "--size",
        str(options["batch_size"]),
        "--model",
        str(options["model"]),
        "--timeout",
        str(options["timeout"]),
        "--max-batches",
        str(options["max_batches"]),
    ]
    if options.get("retry_failed"):
        command.append("--retry-failed")
    return command


def _inspect_log_command(log_path: str | None, source_name: str, encoding: str) -> list[str] | None:
    if not log_path:
        return None
    return [
        sys.executable,
        "-m",
        "gal_translator",
        "inspect-log",
        log_path,
        "--source-name",
        source_name,
        "--encoding",
        encoding,
    ]


def _append_session_log_command(
    project_root: str | None,
    log_path: str | None,
    source_name: str,
    encoding: str,
) -> list[str] | None:
    if not project_root or not log_path:
        return None
    return [
        sys.executable,
        "-m",
        "gal_translator",
        "append-log",
        project_root,
        log_path,
        "--source-name",
        source_name,
        "--encoding",
        encoding,
    ]


def _default_resume_subtitle_window_command(
    project_root: str | None,
    log_path: str | None,
    source_name: str,
    encoding: str,
) -> list[str] | None:
    if not project_root:
        return None
    source_log = log_path if log_path and Path(log_path).is_file() else None
    return _subtitle_window_command(
        Path(project_root),
        SubtitleWindowConfig(),
        no_log=False,
        event_log_arg=None,
        include_source=False,
        miss_log_arg=None,
        reload_enabled=True,
        source_log=source_log,
        source_log_encoding=encoding,
        source_log_name=source_name if source_log else None,
    )


def _resume_append_session_log_payload(
    info: dict[str, Any],
    project_root: Path,
) -> tuple[dict[str, Any] | None, list[str] | None]:
    log_path_text = info.get("sessionLogPath")
    inspection = info.get("sessionLogInspection") if isinstance(info.get("sessionLogInspection"), dict) else {}
    if not isinstance(log_path_text, str) or not log_path_text:
        return None, ["The saved session report does not include a session log path; rerun play-session/live-session after recording source text."]
    source_name = str(inspection.get("sourceName") or "textractor")
    encoding = str(inspection.get("encoding") or "utf-8")
    try:
        capture = ClipboardLogImporter().import_log(Path(log_path_text), source_name=source_name, encoding=encoding)
    except (OSError, UnicodeError) as error:
        return {
            "projectRoot": str(project_root),
            "logPath": log_path_text,
            "sourceName": source_name,
            "encoding": encoding,
            "error": str(error),
        }, ["The saved session log could not be imported; check appendLog.error and the log encoding."]
    return _append_log_payload(project_root, capture), None


def _resume_session_command(
    report_path: Path,
    session_summary: dict[str, Any],
    subtitle_command: list[str] | None = None,
    watch_miss_log_command: list[str] | None = None,
    watch_session_log_command: list[str] | None = None,
) -> list[str]:
    command = [sys.executable, "-m", "gal_translator", "resume-session", str(report_path)]
    if subtitle_command or session_summary.get("subtitleCommand"):
        command.append("--open-subtitle")
    if watch_miss_log_command or session_summary.get("watchMissLogCommand"):
        command.append("--start-miss-watcher")
    if watch_session_log_command or session_summary.get("watchSessionLogCommand"):
        command.append("--start-session-log-watcher")
    if session_summary.get("translateRetryFailed"):
        command.append("--retry-failed")
    return command


def _resume_session_command_for_payload(report_path: Path, session_payload: dict[str, Any]) -> list[str]:
    summary = session_payload.get("sessionSummary") if isinstance(session_payload.get("sessionSummary"), dict) else {}
    subtitle_payload = session_payload.get("subtitleWindow") if isinstance(session_payload.get("subtitleWindow"), dict) else {}
    project_root_text = _session_report_project_root({}, session_payload, summary)
    session_log_text = _session_report_session_log_path({}, session_payload)
    session_log_source_name = _session_report_source_name(session_payload, subtitle_payload)
    session_log_encoding = _session_report_log_encoding(subtitle_payload)
    miss_log_text = _session_report_miss_log_path(summary, subtitle_payload)
    translate_options = _session_resume_translation_options_from_summary(summary)
    subtitle_command = summary.get("subtitleCommand") or subtitle_payload.get("command")
    if not subtitle_command:
        subtitle_command = _default_resume_subtitle_window_command(
            project_root_text,
            session_log_text,
            session_log_source_name,
            session_log_encoding,
        )
    watch_miss_command = summary.get("watchMissLogCommand") or _watch_miss_log_command(
        project_root_text,
        miss_log_text,
        batch_size=translate_options["batch_size"],
        model=translate_options["model"],
        timeout=translate_options["timeout"],
        max_batches=translate_options["max_batches"],
    )
    watch_session_log_command = summary.get("watchSessionLogCommand") or _watch_log_command(
        project_root_text,
        session_log_text,
        source_name=session_log_source_name,
        batch_size=translate_options["batch_size"],
        model=translate_options["model"],
        timeout=translate_options["timeout"],
        max_batches=translate_options["max_batches"],
    )
    return _resume_session_command(
        report_path,
        session_summary=summary,
        subtitle_command=subtitle_command,
        watch_miss_log_command=watch_miss_command,
        watch_session_log_command=watch_session_log_command,
    )


def _session_report_project_root(
    report: dict[str, Any],
    session_payload: dict[str, Any],
    summary: dict[str, Any],
) -> str | None:
    project_info = session_payload.get("projectInfo") if isinstance(session_payload.get("projectInfo"), dict) else {}
    translate_payload = session_payload.get("translateAll") if isinstance(session_payload.get("translateAll"), dict) else {}
    for value in (
        report.get("projectRoot"),
        summary.get("projectRoot"),
        project_info.get("projectRoot"),
        translate_payload.get("projectRoot"),
    ):
        if isinstance(value, str) and value:
            return value
    return None


def _session_report_session_log_path(report: dict[str, Any], session_payload: dict[str, Any]) -> str | None:
    for value in (report.get("sessionLogPath"), session_payload.get("sessionLogPath")):
        if isinstance(value, str) and value:
            return value
    return None


def _session_report_miss_log_path(summary: dict[str, Any], subtitle_payload: dict[str, Any]) -> str | None:
    for value in (summary.get("missLogPath"), subtitle_payload.get("missLogPath")):
        if isinstance(value, str) and value:
            return value
    return None


def _session_report_source_name(session_payload: dict[str, Any], subtitle_payload: dict[str, Any]) -> str:
    capture_payload = session_payload.get("capture") if isinstance(session_payload.get("capture"), dict) else {}
    subtitle_input = subtitle_payload.get("input") if isinstance(subtitle_payload.get("input"), dict) else {}
    for value in (capture_payload.get("captureSource"), subtitle_input.get("sourceLogName")):
        if isinstance(value, str) and value:
            return value
    return "textractor"


def _session_report_log_encoding(subtitle_payload: dict[str, Any]) -> str:
    subtitle_input = subtitle_payload.get("input") if isinstance(subtitle_payload.get("input"), dict) else {}
    value = subtitle_input.get("sourceLogEncoding")
    return value if isinstance(value, str) and value else "utf-8"


def _session_log_inspection_payload(log_path: str | None, source_name: str, encoding: str) -> dict[str, Any] | None:
    if not log_path:
        return None
    path = Path(log_path)
    payload: dict[str, Any] = {
        "path": str(path),
        "exists": path.is_file(),
        "sourceName": source_name,
        "encoding": encoding,
        "captureStats": None,
        "status": "missing",
    }
    if not path.is_file():
        return payload
    try:
        capture = ClipboardLogImporter().import_log(path, source_name=source_name, encoding=encoding)
    except (OSError, UnicodeError) as error:
        payload["status"] = "unreadable"
        payload["error"] = str(error)
        return payload
    payload["captureStats"] = _capture_stats_payload(capture)
    payload["status"] = "has_source" if capture.imported_entry_count > 0 else "no_source_text"
    if capture.entries:
        last_entry = capture.entries[-1]
        payload["lastImportedEntryId"] = last_entry.id
        payload["lastImportedSource"] = last_entry.source
    return payload


def _session_miss_watcher_payload(saved: Any) -> dict[str, Any] | None:
    if not isinstance(saved, dict):
        return None
    payload = dict(saved)
    pid = payload.get("pid")
    payload["currentProcessActive"] = _process_is_running(pid) if isinstance(pid, int) else None
    stdout_path = Path(str(payload["stdoutPath"])) if payload.get("stdoutPath") else None
    stderr_path = Path(str(payload["stderrPath"])) if payload.get("stderrPath") else None
    payload["stdout"] = _session_log_file_payload(stdout_path, parse_jsonl=True)
    payload["stderr"] = _session_log_file_payload(stderr_path, parse_jsonl=False)
    payload["statusSummary"] = _watcher_status_summary(payload)
    return payload


def _session_process_payload(saved: Any) -> dict[str, Any] | None:
    if not isinstance(saved, dict):
        return None
    payload = dict(saved)
    pid = payload.get("pid")
    if not isinstance(pid, int):
        pid = payload.get("detachedPid")
    payload["currentProcessActive"] = _process_is_running(pid) if isinstance(pid, int) else None
    stdout_path = Path(str(payload["stdoutPath"])) if payload.get("stdoutPath") else None
    stderr_path = Path(str(payload["stderrPath"])) if payload.get("stderrPath") else None
    if stdout_path is None and payload.get("detachedStdoutPath"):
        stdout_path = Path(str(payload["detachedStdoutPath"]))
    if stderr_path is None and payload.get("detachedStderrPath"):
        stderr_path = Path(str(payload["detachedStderrPath"]))
    payload["stdout"] = _session_log_file_payload(stdout_path, parse_jsonl=False)
    payload["stderr"] = _session_log_file_payload(stderr_path, parse_jsonl=False)
    status_log_path = Path(str(payload["statusLogPath"])) if payload.get("statusLogPath") else None
    payload["statusLog"] = _session_log_file_payload(status_log_path, parse_jsonl=True)
    return payload


def _watcher_command_from_report(saved: Any) -> list[str] | None:
    if not isinstance(saved, dict):
        return None
    command = saved.get("command")
    if not isinstance(command, list) or not command:
        return None
    return [str(part) for part in command]


def _session_log_file_payload(path: Path | None, parse_jsonl: bool) -> dict[str, Any] | None:
    if path is None:
        return None
    exists = path.is_file()
    payload: dict[str, Any] = {
        "path": str(path),
        "exists": exists,
        "size": path.stat().st_size if exists else 0,
        "lastLine": None,
        "tailLines": [],
    }
    if not exists:
        return payload
    tail_lines = _tail_nonempty_lines(path)
    last_line = tail_lines[-1] if tail_lines else None
    payload["tailLines"] = tail_lines
    payload["lastLine"] = last_line
    if parse_jsonl and last_line:
        try:
            payload["lastEvent"] = json.loads(last_line)
        except json.JSONDecodeError:
            payload["lastEvent"] = None
        payload["lastProcessedEvent"] = _last_jsonl_event(path, status="processed")
    return payload


def _last_jsonl_event(path: Path, *, status: str | None = None) -> dict[str, Any] | None:
    try:
        lines = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    except OSError:
        return None
    for line in reversed(lines):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            event = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        if status is not None and event.get("status") != status:
            continue
        return event
    return None


def _last_nonempty_line(path: Path) -> str | None:
    lines = _tail_nonempty_lines(path, limit=1)
    return lines[-1] if lines else None


def _tail_nonempty_lines(path: Path, limit: int = 5) -> list[str]:
    if limit <= 0:
        return []
    try:
        lines = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    except OSError:
        return []
    tail: list[str] = []
    for line in reversed(lines):
        stripped = line.strip()
        if not stripped:
            continue
        tail.append(stripped)
        if len(tail) >= limit:
            break
    return list(reversed(tail))


def _watcher_status_summary(watcher_payload: dict[str, Any]) -> dict[str, Any]:
    stdout = watcher_payload.get("stdout") if isinstance(watcher_payload.get("stdout"), dict) else {}
    last_event = stdout.get("lastEvent") if isinstance(stdout.get("lastEvent"), dict) else {}
    last_processed_event = stdout.get("lastProcessedEvent") if isinstance(stdout.get("lastProcessedEvent"), dict) else {}
    result = last_event.get("result") if isinstance(last_event.get("result"), dict) else {}
    session_summary = result.get("sessionSummary") if isinstance(result.get("sessionSummary"), dict) else {}
    append_payload = result.get("append") if isinstance(result.get("append"), dict) else {}
    progress = append_payload.get("progress") if isinstance(append_payload.get("progress"), dict) else {}
    processed_result = (
        last_processed_event.get("result") if isinstance(last_processed_event.get("result"), dict) else {}
    )
    processed_summary = (
        processed_result.get("sessionSummary") if isinstance(processed_result.get("sessionSummary"), dict) else {}
    )
    processed_append = (
        processed_result.get("append") if isinstance(processed_result.get("append"), dict) else {}
    )
    return {
        "processActive": watcher_payload.get("currentProcessActive"),
        "reportedRunning": bool(watcher_payload.get("running")),
        "lastStatus": last_event.get("status"),
        "lastReason": last_event.get("reason"),
        "lastCycle": last_event.get("cycle"),
        "lastIdleCount": last_event.get("idleCount"),
        "lastSessionStatus": session_summary.get("status"),
        "lastAddedEntryCount": session_summary.get("addedEntryCount"),
        "lastPendingCount": session_summary.get("pendingCount") if session_summary else progress.get("pending"),
        "lastFailedCount": session_summary.get("failedCount") if session_summary else progress.get("failed"),
        "lastTranslatedCount": session_summary.get("translatedCount") if session_summary else progress.get("translated"),
        "lastProcessedStatus": last_processed_event.get("status"),
        "lastProcessedCycle": last_processed_event.get("cycle"),
        "lastProcessedSessionStatus": processed_summary.get("status"),
        "lastProcessedAddedEntryCount": processed_summary.get("addedEntryCount"),
        "lastProcessedScopedTranslatedCount": processed_summary.get("scopedTranslatedCount"),
        "lastProcessedLogEntryIds": processed_append.get("logEntryIds") if processed_append else None,
        "stdoutExists": stdout.get("exists"),
    }


def _session_info_next_actions(payload: dict[str, Any]) -> list[str]:
    if payload.get("reportType") == "source-log-session":
        return _source_log_session_info_next_actions(payload)
    commands = payload.get("commands") if isinstance(payload.get("commands"), dict) else {}
    project_info = payload.get("currentProjectInfo") if isinstance(payload.get("currentProjectInfo"), dict) else None
    if not payload.get("projectRoot"):
        return ["This report does not include a project path; rerun play-session or live-session and save a fresh report."]
    if not payload.get("projectExists"):
        return ["The reported project directory is missing; rerun play-session or live-session to recreate it."]
    if project_info is None:
        return ["Run the returned projectInfoCommand to inspect the project, then resume translation or subtitle display."]

    lock = project_info.get("translationLock") if isinstance(project_info.get("translationLock"), dict) else {}
    if lock.get("exists"):
        if lock.get("processActive") is True:
            return ["A translation run still appears active; wait for it to finish, then rerun session-info."]
        return ["Run the returned clearLockCommand if no Gal Translator translation process is still running, then rerun session-info."]

    progress = project_info.get("progress") if isinstance(project_info.get("progress"), dict) else None
    if progress is None:
        return list(project_info.get("nextActions") or ["Repair the project state, then rerun session-info."])
    if progress.get("total", 0) == 0:
        actions = ["Inspect the saved session log with inspectLogCommand; rerun play-session or live-session after it contains Japanese story lines."]
        if not payload.get("sessionLogExists"):
            actions.insert(0, "The saved session log path is missing; record clipboard/Textractor output before importing again.")
        else:
            inspection = payload.get("sessionLogInspection") if isinstance(payload.get("sessionLogInspection"), dict) else {}
            if inspection.get("status") == "no_source_text":
                actions.insert(0, "The saved session log currently has no imported Japanese source lines; check Textractor hook quality before rerunning translation.")
            elif inspection.get("status") == "has_source":
                stats = inspection.get("captureStats") if isinstance(inspection.get("captureStats"), dict) else {}
                actions.insert(0, f"The saved session log has {stats.get('importedEntryCount', 0)} importable source line(s); run resumeSessionCommand to append it and continue translation.")
            elif inspection.get("status") == "unreadable":
                actions.insert(0, "The saved session log exists but could not be read; check sessionLogInspection.error and the log encoding.")
        return actions
    if progress.get("failed", 0) > 0:
        return ["Run retryFailedCommand after reviewing errors, then run translateAllCommand to finish translation."]
    if progress.get("pending", 0) > 0:
        return ["Run translateAllCommand to translate and apply all pending entries, then rerun session-info."]

    if commands.get("subtitleWindowCommand"):
        actions = ["Run subtitleWindowCommand to open the live bilingual subtitle window."]
    else:
        actions = ["Run project-info or subtitle-window for this project to open runtime display."]
    miss_watcher = payload.get("missWatcher") if isinstance(payload.get("missWatcher"), dict) else {}
    miss_summary = miss_watcher.get("statusSummary") if isinstance(miss_watcher.get("statusSummary"), dict) else {}
    if miss_watcher.get("currentProcessActive") is True:
        actions.append(_active_watcher_action("miss watcher", "missWatcher", miss_summary, "new lines"))
    elif miss_watcher.get("running") and miss_watcher.get("currentProcessActive") is False:
        actions.append("The saved miss watcher process is no longer running; run watchMissLogCommand to restore background miss translation.")
    elif miss_watcher.get("running"):
        actions.append("The saved live-session report says the miss watcher should still be running; check missWatcher.stdout if new lines do not translate.")
    elif commands.get("watchMissLogCommand"):
        actions.append("Run watchMissLogCommand in the background so runtime misses are translated while playing.")
    elif commands.get("translateMissLogCommand"):
        actions.append("Run translateMissLogCommand after playing to translate newly captured misses.")
    session_log_watcher = payload.get("sessionLogWatcher") if isinstance(payload.get("sessionLogWatcher"), dict) else {}
    session_log_summary = session_log_watcher.get("statusSummary") if isinstance(session_log_watcher.get("statusSummary"), dict) else {}
    if session_log_watcher.get("currentProcessActive") is True:
        actions.append(_active_watcher_action("session-log watcher", "sessionLogWatcher", session_log_summary, "appended source-log lines"))
    elif session_log_watcher.get("running") and session_log_watcher.get("currentProcessActive") is False:
        actions.append("The saved session-log watcher process is no longer running; run watchSessionLogCommand to restore source-log background translation.")
    elif session_log_watcher.get("running"):
        actions.append("The saved live-session report says the session-log watcher should still be running; check sessionLogWatcher.stdout if appended source-log lines do not translate.")
    elif commands.get("watchSessionLogCommand"):
        actions.append("Run watchSessionLogCommand to translate newly appended session-log lines while subtitle-window follows --source-log.")
    return actions


def _source_log_session_info_next_actions(payload: dict[str, Any]) -> list[str]:
    commands = payload.get("commands") if isinstance(payload.get("commands"), dict) else {}
    project_info = payload.get("currentProjectInfo") if isinstance(payload.get("currentProjectInfo"), dict) else None
    if not payload.get("projectRoot"):
        return ["This source-log session report does not include a project path; rerun source-log-session.ps1 with -ProjectRoot."]
    if not payload.get("projectExists"):
        return ["The reported project directory is missing; rerun import-artemis-ast or source-log-session.ps1 after restoring the project."]
    if project_info is None:
        return ["Run the returned projectInfoCommand to inspect the project before restarting the source-log session."]

    lock = project_info.get("translationLock") if isinstance(project_info.get("translationLock"), dict) else {}
    if lock.get("exists"):
        if lock.get("processActive") is True:
            return ["A scoped translation run still appears active; wait for it to finish, then rerun session-info."]
        return ["Run the returned clearLockCommand if no Gal Translator translation process is still running, then rerun session-info."]

    actions: list[str] = []
    if not payload.get("sessionLogExists"):
        actions.append("The source log does not exist yet; start source-log-session.ps1 or configure LunaHook/Textractor to append to sessionLogPath.")
    else:
        inspection = payload.get("sessionLogInspection") if isinstance(payload.get("sessionLogInspection"), dict) else {}
        if inspection.get("status") == "has_source":
            stats = inspection.get("captureStats") if isinstance(inspection.get("captureStats"), dict) else {}
            actions.append(f"The source log has {stats.get('importedEntryCount', 0)} importable source line(s); keep using scoped source-log translation instead of full translate-all.")
        elif inspection.get("status") == "no_source_text":
            actions.append("The source log exists but has no imported Japanese source lines yet; keep LunaHook/Textractor appending runtime text to it.")

    session_log_watcher = payload.get("sessionLogWatcher") if isinstance(payload.get("sessionLogWatcher"), dict) else {}
    session_log_summary = session_log_watcher.get("statusSummary") if isinstance(session_log_watcher.get("statusSummary"), dict) else {}
    if session_log_watcher.get("currentProcessActive") is True:
        actions.append(_active_watcher_action("source-log watcher", "sessionLogWatcher", session_log_summary, "appended source-log lines"))
    elif session_log_watcher.get("started") and session_log_watcher.get("currentProcessActive") is False:
        actions.append("The saved source-log watcher process is no longer running; run sourceLogSessionCommand or watchSessionLogCommand to restore scoped background translation.")
    elif commands.get("sourceLogSessionCommand"):
        actions.append("Run sourceLogSessionCommand to restart the scoped watcher and subtitle window for this source log.")
    elif commands.get("watchSessionLogCommand"):
        actions.append("Run watchSessionLogCommand to restore scoped source-log background translation.")

    subtitle_payload = payload.get("subtitleWindow") if isinstance(payload.get("subtitleWindow"), dict) else {}
    if subtitle_payload.get("currentProcessActive") is True:
        actions.append("The saved subtitle window process is still running; keep playing and monitor subtitleWindow logs if display stalls.")
    elif subtitle_payload.get("started") and subtitle_payload.get("currentProcessActive") is False:
        actions.append("The saved subtitle window process is no longer running; run sourceLogSessionCommand or subtitleWindowCommand to reopen it.")
    elif commands.get("subtitleWindowCommand"):
        actions.append("Run subtitleWindowCommand or sourceLogSessionCommand to open the source-log subtitle window.")

    clipboard_bridge = payload.get("clipboardBridge") if isinstance(payload.get("clipboardBridge"), dict) else {}
    if clipboard_bridge.get("currentProcessActive") is True:
        actions.append("The saved clipboard bridge is running; clipboard-only Hook output will be appended to the source log.")
    elif clipboard_bridge.get("enabled"):
        actions.append("The saved clipboard bridge is not running; rerun sourceLogSessionCommand with -StartClipboardBridge if LunaHook/Textractor only copies text.")

    luna_hook_bridge = payload.get("lunaHookBridge") if isinstance(payload.get("lunaHookBridge"), dict) else {}
    if luna_hook_bridge.get("currentProcessActive") is True:
        actions.append("The saved LunaHook bridge is running; hooked game text will be appended to the source log.")
    elif luna_hook_bridge.get("enabled"):
        actions.append("The saved LunaHook bridge is not running; rerun sourceLogSessionCommand with -StartLunaHookBridge after starting the game.")

    actions.append("Do not run translateAllCommand for this paused full-archive project unless you intentionally want global pending translation.")
    return actions


def _active_watcher_action(label: str, payload_key: str, summary: dict[str, Any], subject: str) -> str:
    reason = summary.get("lastReason")
    status = summary.get("lastStatus")
    if reason == "translation_not_ready":
        return f"The saved {label} is running and waiting for the primary project translation to become ready."
    if reason == "translation_state_missing":
        return f"The saved {label} is running and waiting for translation-state.json to be created."
    if reason == "translation_locked":
        return f"The saved {label} is running and waiting for the active translation lock to clear."
    if reason == "log_missing":
        return f"The saved {label} is running, but its watched log is missing; check {payload_key}.stdout.lastEvent."
    if status == "processed":
        added_count = summary.get("lastAddedEntryCount")
        if isinstance(added_count, int):
            return f"The saved {label} is running; the last cycle processed {added_count} new captured entr{'y' if added_count == 1 else 'ies'}."
    return f"The saved {label} process is currently running; check {payload_key}.statusSummary if {subject} do not translate."


def _project_next_actions(project_root: Path, summary: dict[str, Any] | None) -> list[str]:
    lock = _translation_lock_info(project_root)
    if lock["exists"]:
        if lock["processActive"] is True:
            return ["A translation run appears active. Wait for it to finish, then rerun project-info."]
        return ["Run clear-lock for this project if no Gal Translator translation process is running."]
    if not (project_root / "translation-state.json").is_file():
        return ["Run import for direct scripts, or capture-log for Textractor/clipboard logs."]
    if summary is None:
        return ["Repair or regenerate translation-state.json before continuing this project."]
    if summary["total"] == 0:
        return ["No source entries are available. Use capture-log --append with a Textractor/clipboard log."]
    if summary["pending"] > 0:
        return ["Run translate-all to execute and apply all pending Codex batches, or prepare-codex for manual review."]
    if summary["failed"] > 0:
        retry_info = _failed_retry_info_payload(project_root)
        if retry_info and retry_info.get("skippedCount", 0) > 0:
            return [
                "Some failed entries already reached the 3-retry limit; review them, but it is usually safe to abandon isolated lines and continue.",
                "Retry only manually selected entries if the missing line is important.",
            ]
        return ["Run retry-failed after reviewing errors, then rerun translate-all."]
    return ["Run lookup, watch-clipboard, or subtitle-window for runtime display."]


def _failed_retry_info_payload(project_root: Path) -> dict[str, Any] | None:
    state_path = project_root / "translation-state.json"
    if not state_path.is_file():
        return None
    try:
        return TranslationProgressTracker(state_path).preview_reset_failed().to_payload()
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None


def _runtime_info_payload(project_root: Path) -> dict[str, Any]:
    event_log_path = project_root / "logs" / "runtime-events.jsonl"
    return {
        "runtimeEventLogPath": str(event_log_path),
        "runtimeEventLogExists": event_log_path.is_file(),
        "runtimeEventLogSize": event_log_path.stat().st_size if event_log_path.is_file() else 0,
    }


def _translation_lock_info(project_root: Path) -> dict[str, Any]:
    lock_path = project_root / "logs" / "translation.lock"
    payload: dict[str, Any] = {
        "lockPath": str(lock_path),
        "exists": lock_path.is_file(),
        "pid": None,
        "createdAt": None,
        "processActive": None,
        "valid": None,
    }
    if not lock_path.is_file():
        return payload
    try:
        lock_json = json.loads(lock_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        payload["valid"] = False
        return payload
    payload["valid"] = isinstance(lock_json, dict)
    if not isinstance(lock_json, dict):
        return payload
    pid = lock_json.get("pid")
    payload["pid"] = pid if isinstance(pid, int) else None
    created_at = lock_json.get("createdAt")
    payload["createdAt"] = created_at if isinstance(created_at, str) else None
    payload["processActive"] = _process_is_running(pid) if isinstance(pid, int) else None
    return payload


def _clear_translation_lock_payload(project_root: Path, force: bool) -> tuple[dict[str, Any], int]:
    info = _translation_lock_info(project_root)
    lock_path = Path(info["lockPath"])
    if not info["exists"]:
        return (
            {
                "status": "not_found",
                "projectRoot": str(project_root),
                "translationLock": info,
                "nextActions": ["No translation lock is present."],
            },
            0,
        )
    if info["processActive"] is True and not force:
        return (
            {
                "status": "active",
                "projectRoot": str(project_root),
                "translationLock": info,
                "nextActions": ["Wait for the active translation process to finish, or rerun clear-lock with --force only if you are certain it is stale."],
            },
            1,
        )
    try:
        lock_path.unlink()
    except OSError as error:
        return (
            _error_payload(
                "lock_clear_failed",
                str(error),
                ["Check file permissions and rerun clear-lock."],
            ),
            1,
        )
    return (
        {
            "status": "cleared",
            "projectRoot": str(project_root),
            "translationLock": info,
            "nextActions": ["Rerun project-info, then resume translate-all or live-session."],
        },
        0,
    )


def _process_is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel32.GetExitCodeProcess.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL

        process_query_limited_information = 0x1000
        process_query_information = 0x0400
        handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
        if not handle:
            handle = kernel32.OpenProcess(process_query_information, False, pid)
        if not handle:
            return False
        try:
            exit_code = wintypes.DWORD()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                return True
            return exit_code.value == 259
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _latest_codex_batch_payload(project_root: Path, diagnostics: list[dict[str, Any]] | None = None) -> dict[str, Any] | None:
    batch_root = project_root / "logs" / "codex-batches"
    if not batch_root.is_dir():
        legacy_batch = project_root / "logs" / "codex-batch"
        if not legacy_batch.is_dir():
            return None
        return _codex_batch_payload(legacy_batch, diagnostics)
    batch_dirs = [path for path in batch_root.iterdir() if path.is_dir()]
    if not batch_dirs:
        return None
    latest = max(batch_dirs, key=lambda path: path.name)
    return _codex_batch_payload(latest, diagnostics)


def _codex_batch_payload(batch_dir: Path, diagnostics: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    issue_count = len(diagnostics) if diagnostics is not None else 0
    batch_json_path = batch_dir / "batch.json"
    command_json_path = batch_dir / "command.json"
    result_json_path = batch_dir / "result.json"
    stdout_path = batch_dir / "stdout.txt"
    stderr_path = batch_dir / "stderr.txt"
    batch_json = _read_json_file(
        batch_json_path,
        default={},
        diagnostics=diagnostics,
        label="latestCodexBatch",
    )
    batch_json_valid = diagnostics is None or len(diagnostics) == issue_count
    entry_ids = batch_json.get("entryIds", []) if isinstance(batch_json, dict) else []
    return {
        "directory": str(batch_dir),
        "batchPath": str(batch_json_path),
        "hasBatchJson": batch_json_path.is_file(),
        "batchJsonValid": batch_json_valid,
        "promptPath": str(batch_dir / "prompt.txt"),
        "commandPath": str(command_json_path),
        "resultPath": str(result_json_path),
        "entryCount": len(entry_ids) if isinstance(entry_ids, list) else 0,
        "hasResult": result_json_path.is_file(),
        "hasStdout": stdout_path.is_file(),
        "hasStderr": stderr_path.is_file(),
        "stdout": _session_log_file_payload(stdout_path, parse_jsonl=False),
        "stderr": _session_log_file_payload(stderr_path, parse_jsonl=False),
        "result": _json_file_summary_payload(result_json_path),
        "command": _json_file_summary_payload(command_json_path),
    }


def _json_file_summary_payload(path: Path) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "path": str(path),
        "exists": path.is_file(),
        "valid": None,
        "keys": None,
        "itemCount": None,
        "error": None,
    }
    if not path.is_file():
        return payload
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as error:
        payload["valid"] = False
        payload["error"] = str(error)
        return payload
    payload["valid"] = True
    if isinstance(data, dict):
        payload["keys"] = sorted(str(key) for key in data.keys())
        items = data.get("items")
        if isinstance(items, list):
            payload["itemCount"] = len(items)
    elif isinstance(data, list):
        payload["itemCount"] = len(data)
    return payload


def _read_json_file(
    path: Path,
    default: Any | None = None,
    diagnostics: list[dict[str, Any]] | None = None,
    label: str | None = None,
) -> Any:
    if not path.is_file():
        return {} if default is None else default
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as error:
        if diagnostics is None:
            raise
        diagnostics.append(_file_diagnostic("json_invalid", path, label or path.name, error))
        return {} if default is None else default


def _write_json_report(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _file_diagnostic(code: str, path: Path, label: str, error: BaseException) -> dict[str, Any]:
    return {
        "code": code,
        "label": label,
        "path": str(path),
        "message": str(error),
    }


def _workspace_writable(workspace: Path) -> bool:
    try:
        workspace.mkdir(parents=True, exist_ok=True)
        probe = workspace / ".write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError:
        return False
    return True


def _candidate_payload(candidate: EngineCandidate) -> dict[str, Any]:
    return {
        "engineId": candidate.engine_id,
        "label": candidate.label,
        "confidence": candidate.confidence,
        "reasons": list(candidate.reasons),
    }


def _file_payload(file: ScannedFile) -> dict[str, Any]:
    return {
        "relativePath": file.relative_path,
        "extension": file.extension,
        "size": file.size,
    }


def _archive_payload(diagnostic: Any) -> dict[str, Any]:
    return {
        "relativePath": diagnostic.relative_path,
        "formatId": diagnostic.format_id,
        "label": diagnostic.label,
        "magic": diagnostic.magic,
        "size": diagnostic.size,
        "sampledBytes": diagnostic.sampled_bytes,
        "structuredEntryCount": diagnostic.structured_entry_count,
        "visibleExtensionCounts": diagnostic.visible_extension_counts,
        "visibleScriptPaths": list(diagnostic.visible_script_paths),
        "notes": list(diagnostic.notes),
    }


def _archive_diagnostics_for_path(path: Path) -> list[Any]:
    resolved = path.resolve()
    inspector = ArchiveInspector()
    if resolved.is_file() and resolved.suffix.lower() != ".exe":
        diagnostic = inspector.inspect_file(resolved, resolved.name)
        return [diagnostic] if diagnostic is not None else []
    report = GameScanner().scan(resolved)
    return list(report.archive_diagnostics)


def _archive_list_payload(diagnostics: list[Any], scripts_only: bool, limit: int) -> dict[str, Any]:
    safe_limit = max(0, limit)
    return {
        "archives": [
            {
                "relativePath": diagnostic.relative_path,
                "formatId": diagnostic.format_id,
                "structuredEntryCount": diagnostic.structured_entry_count,
                "returnedEntryCount": len(_limited_archive_entries(diagnostic, scripts_only, safe_limit)),
                "entries": [
                    {
                        "path": entry.path,
                        "offset": entry.offset,
                        "size": entry.size,
                    }
                    for entry in _limited_archive_entries(diagnostic, scripts_only, safe_limit)
                ],
            }
            for diagnostic in diagnostics
        ]
    }


def _limited_archive_entries(diagnostic: Any, scripts_only: bool, limit: int) -> list[Any]:
    entries = list(diagnostic.entries)
    if scripts_only:
        entries = [entry for entry in entries if is_script_entry(entry)]
    return entries[:limit]


def _translate_all_payload(
    project_root: Path,
    batch_size: int,
    model: str,
    max_batches: int,
    timeout: int,
    dry_run: bool,
    retry_failed: bool = False,
    allowed_entry_ids: list[str] | tuple[str, ...] | None = None,
) -> tuple[dict[str, Any], int]:
    with _project_translation_lock(project_root) as lock_payload:
        if lock_payload is not None:
            return lock_payload, 1
        return _translate_all_payload_unlocked(
            project_root=project_root,
            batch_size=batch_size,
            model=model,
            max_batches=max_batches,
            timeout=timeout,
            dry_run=dry_run,
            retry_failed=retry_failed,
            allowed_entry_ids=allowed_entry_ids,
        )


def _translate_all_payload_unlocked(
    project_root: Path,
    batch_size: int,
    model: str,
    max_batches: int,
    timeout: int,
    dry_run: bool,
    retry_failed: bool = False,
    allowed_entry_ids: list[str] | tuple[str, ...] | None = None,
) -> tuple[dict[str, Any], int]:
    safe_batch_size = max(1, batch_size)
    scoped_entry_ids = _ordered_unique_strings(allowed_entry_ids)
    initial_progress = _project_progress_payload(project_root)
    initial_scope_progress = (
        _scoped_progress_payload(project_root, scoped_entry_ids)
        if scoped_entry_ids is not None
        else initial_progress
    )
    progress_for_planning = initial_progress
    scope_progress_for_planning = initial_scope_progress
    reset_count = 0
    retry_summary_payload: dict[str, Any] | None = None
    if retry_failed and initial_progress["failed"] > 0:
        tracker = TranslationProgressTracker(project_root / "translation-state.json")
        if dry_run:
            retry_summary = tracker.preview_reset_failed()
            retry_summary_payload = retry_summary.to_payload()
            progress_for_planning = {
                **initial_progress,
                "pending": initial_progress["pending"] + retry_summary.reset_count,
                "failed": retry_summary.skipped_count,
                "status": "pending" if initial_progress["translated"] == 0 else "partial",
            }
        else:
            retry_summary = tracker.reset_failed_summary()
            retry_summary_payload = retry_summary.to_payload()
            reset_count = retry_summary.reset_count
            progress_for_planning = _project_progress_payload(project_root)
            if scoped_entry_ids is not None:
                scope_progress_for_planning = _scoped_progress_payload(project_root, scoped_entry_ids)
    pending_count = initial_scope_progress["pending"]
    planned_pending_count = scope_progress_for_planning["pending"]
    planned_batch_count = _planned_batch_count(planned_pending_count, safe_batch_size, max_batches)
    payload: dict[str, Any] = {
        "projectRoot": str(project_root),
        "model": model,
        "batchSize": safe_batch_size,
        "maxBatches": max(0, max_batches),
        "translateScope": "entry_ids" if scoped_entry_ids is not None else "all_pending",
        "scopeEntryIds": list(scoped_entry_ids) if scoped_entry_ids is not None else None,
        "plannedBatchCount": planned_batch_count,
        "executedBatchCount": 0,
        "initialProgress": initial_progress,
        "initialScopeProgress": initial_scope_progress if scoped_entry_ids is not None else None,
        "progressAfterRetryFailed": progress_for_planning if retry_failed else None,
        "retryFailed": {
            "requested": retry_failed,
            "dryRun": dry_run,
            "plannedResetCount": retry_summary_payload["resetCount"] if retry_summary_payload else (initial_progress["failed"] if retry_failed else 0),
            "resetCount": reset_count,
            "skippedCount": retry_summary_payload["skippedCount"] if retry_summary_payload else 0,
            "retryLimit": retry_summary_payload["retryLimit"] if retry_summary_payload else 3,
            "skippedIds": retry_summary_payload["skippedIds"] if retry_summary_payload else [],
            "nextActions": retry_summary_payload["nextActions"] if retry_summary_payload else [],
        },
        "finalProgress": progress_for_planning,
        "finalScopeProgress": scope_progress_for_planning if scoped_entry_ids is not None else None,
        "batches": [],
    }
    if dry_run:
        first_prepared = None
        if scope_progress_for_planning["pending"] > 0 and (not retry_failed or pending_count > 0):
            first_prepared = _prepare_codex_batch(project_root, safe_batch_size, model, None, scoped_entry_ids)
        payload.update(
            {
                "status": "dry_run",
                "firstBatch": first_prepared,
                "nextActions": _translate_all_next_actions("dry_run", progress_for_planning),
            }
        )
        return payload, 0

    status = "ready" if scope_progress_for_planning["pending"] == 0 and scope_progress_for_planning["failed"] == 0 else "started"
    return_code = 0
    while True:
        current_scope_progress = (
            _scoped_progress_payload(project_root, scoped_entry_ids)
            if scoped_entry_ids is not None
            else _project_progress_payload(project_root)
        )
        if current_scope_progress["pending"] <= 0:
            status = "ready" if current_scope_progress["failed"] == 0 else "completed_with_failed_items"
            return_code = 0 if current_scope_progress["failed"] == 0 else 1
            break
        if max_batches > 0 and payload["executedBatchCount"] >= max_batches:
            status = "max_batches_reached"
            return_code = 0
            break

        prepared = _prepare_codex_batch(project_root, safe_batch_size, model, None, scoped_entry_ids)
        batch_payload = {
            "batchIndex": payload["executedBatchCount"] + 1,
            **_execute_prepared_codex(prepared, timeout),
        }
        payload["executedBatchCount"] += 1
        if batch_payload["returnCode"] != 0:
            if batch_payload["status"] == "timeout":
                apply_summary, error = _apply_prepared_codex_result(project_root, prepared)
                if error is None:
                    batch_payload["executionStatus"] = batch_payload["status"]
                    batch_payload["executionReturnCode"] = batch_payload["returnCode"]
                    batch_payload["status"] = "timeout_result_applied"
                    batch_payload["returnCode"] = 0
                    batch_payload["applyResult"] = apply_summary.to_payload()
                    batch_payload["progress"] = _project_progress_payload(project_root)
                    if scoped_entry_ids is not None:
                        batch_payload["scopeProgress"] = _scoped_progress_payload(project_root, scoped_entry_ids)
                    payload["batches"].append(batch_payload)
                    continue
                batch_payload["error"] = error
            status = batch_payload["status"]
            return_code = 1
            payload["batches"].append(batch_payload)
            break

        apply_summary, error = _apply_prepared_codex_result(project_root, prepared)
        if error is not None:
            batch_payload["status"] = "result_invalid"
            batch_payload["returnCode"] = 1
            batch_payload["error"] = error
            status = "result_invalid"
            return_code = 1
            payload["batches"].append(batch_payload)
            break

        batch_payload["applyResult"] = apply_summary.to_payload()
        batch_payload["progress"] = _project_progress_payload(project_root)
        if scoped_entry_ids is not None:
            batch_payload["scopeProgress"] = _scoped_progress_payload(project_root, scoped_entry_ids)
        payload["batches"].append(batch_payload)

    final_progress = _project_progress_payload(project_root)
    final_scope_progress = (
        _scoped_progress_payload(project_root, scoped_entry_ids)
        if scoped_entry_ids is not None
        else None
    )
    payload["status"] = status
    payload["finalProgress"] = final_progress
    payload["finalScopeProgress"] = final_scope_progress
    payload["nextActions"] = _translate_all_next_actions(status, final_progress)
    return payload, return_code


@contextmanager
def _project_translation_lock(project_root: Path) -> Any:
    lock_path = project_root / "logs" / "translation.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        yield _translation_lock_payload(project_root, lock_path)
        return
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {
                        "pid": os.getpid(),
                        "createdAt": datetime.now(timezone.utc).isoformat(),
                    },
                    ensure_ascii=False,
                )
            )
        yield None
    finally:
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass


def _translation_lock_payload(project_root: Path, lock_path: Path) -> dict[str, Any]:
    return {
        "projectRoot": str(project_root),
        "status": "translation_locked",
        "lockPath": str(lock_path),
        "nextActions": [
            "Another translation run is active for this project; wait for it to finish, then retry.",
            "If no Gal Translator process is running, remove the stale lock file and rerun the command.",
        ],
    }


def _record_clipboard_payload(
    provider: Any,
    log_path: Path,
    interval: float,
    max_events: int,
    duration: float,
    append: bool,
) -> dict[str, Any]:
    recorder = ClipboardTextRecorder(provider)
    safe_interval = max(0.05, interval)
    stop_at = time.monotonic() + duration if duration > 0 else None
    captured_count = 0
    poll_count = 0
    interrupted = False
    try:
        while True:
            summary = recorder.record(log_path, max_events=1, append=append or captured_count > 0, max_polls=1)
            captured_count += summary.captured_count
            poll_count += summary.poll_count
            if max_events > 0 and captured_count >= max_events:
                break
            if stop_at is not None and time.monotonic() >= stop_at:
                break
            time.sleep(safe_interval)
    except KeyboardInterrupt:
        interrupted = True
    return {
        "logPath": str(log_path),
        "status": "interrupted" if interrupted else "completed",
        "capturedCount": captured_count,
        "pollCount": poll_count,
        "append": append,
        "intervalSeconds": safe_interval,
        "durationSeconds": duration,
        "maxEvents": max_events,
        "nextActions": [
            "Run inspect-log on this file, then capture-log or workflow-fallback to import it for translation."
        ],
    }


def _smoke_test_payload(args: Any) -> tuple[dict[str, Any], int]:
    run_id = _run_id()
    workspace = Path(args.workspace) if args.workspace else _default_smoke_workspace(run_id)
    smoke_root = workspace / "smoke-session"
    game_dir = smoke_root / "Game"
    game_dir.mkdir(parents=True, exist_ok=True)
    game_path = game_dir / "game.exe"
    game_path.write_bytes(b"MZ")
    live_game_dir = smoke_root / "LiveGame"
    live_game_dir.mkdir(parents=True, exist_ok=True)
    live_game_path = live_game_dir / "live-game.exe"
    live_game_path.write_bytes(b"MZ")
    retry_game_dir = smoke_root / "RetryGame"
    retry_game_dir.mkdir(parents=True, exist_ok=True)
    retry_game_path = retry_game_dir / "retry-game.exe"
    retry_game_path.write_bytes(b"MZ")
    log_path = smoke_root / "textractor-log.txt"
    log_path.write_text("\n".join(_SMOKE_CAPTURE_LINES), encoding="utf-8")
    live_log_path = smoke_root / "live-textractor-log.txt"
    live_log_path.write_text(_SMOKE_LIVE_SESSION_LINE + "\n", encoding="utf-8")
    replay_log_path = smoke_root / "replay-events.jsonl"
    runtime_log_path = smoke_root / "runtime-events.jsonl"
    miss_log_path = smoke_root / "misses.txt"
    report_path = smoke_root / "play-session-report.json"
    live_report_path = smoke_root / "live-session-report.json"
    retry_report_path = smoke_root / "retry-failed-report.json"
    source_log_feedback_replay_path = smoke_root / "source-log-feedback-replay.jsonl"
    source_log_feedback_runtime_path = smoke_root / "source-log-feedback-runtime.jsonl"
    source_log_live_refresh_runtime_path = smoke_root / "source-log-live-refresh-runtime.jsonl"
    fake_bin = smoke_root / "fake-bin"
    fake_bin.mkdir(parents=True, exist_ok=True)
    fake_codex_path = _write_smoke_fake_codex(fake_bin)

    old_path = os.environ.get("PATH", "")
    os.environ["PATH"] = str(fake_bin) + os.pathsep + old_path
    try:
        play_args = argparse.Namespace(
            path=str(game_path),
            log_file=str(log_path),
            workspace=str(workspace),
            encoding="utf-8",
            source_name="textractor",
            append=False,
            launch_game=False,
            record_clipboard=False,
            record_interval=0.25,
            record_max_events=0,
            record_duration=60.0,
            record_until_interrupted=False,
            overwrite_log=False,
            batch_size=2,
            model=args.model,
            translate_dry_run=False,
            translate_timeout=30,
            translate_max_batches=0,
            replay_event_log=str(replay_log_path),
            replay_include_source=False,
            no_subtitle=False,
            subtitle_dry_run=not args.open_subtitle,
            subtitle_detach=args.open_subtitle,
            subtitle_preview_source=None,
            subtitle_preview_first_match=True,
            subtitle_source_log=True,
            subtitle_source_log_from_start=False,
            interval=0.25,
            font_size=30,
            opacity=0.82,
            width=1200,
            height=120,
            x=120,
            y=760,
            font_family="Microsoft YaHei UI",
            background="#050505",
            foreground="#f5f5f5",
            clear_after=4.0,
            subtitle_exit_after=args.subtitle_exit_after,
            not_topmost=False,
            subtitle_event_log=str(runtime_log_path),
            subtitle_no_log=False,
            subtitle_include_source=False,
            subtitle_miss_log=str(miss_log_path),
            subtitle_no_reload=False,
        )
        inspect_capture = ClipboardLogImporter().import_log(log_path, source_name="textractor", encoding="utf-8")
        inspect_payload = _inspect_log_payload(inspect_capture, limit=5, include_source=False)
        play_payload, play_return_code = _play_session_payload(play_args)
        play_payload["sessionReportPath"] = str(report_path)
        play_payload["resumeCommand"] = _resume_session_command_for_payload(report_path, play_payload)
        _write_json_report(report_path, play_payload)
        session_info_payload = _session_info_payload(report_path)
        resume_payload, resume_return_code = _resume_session_payload(
            report_path,
            dry_run=True,
            open_subtitle=True,
            start_miss_watcher=True,
            start_session_log_watcher=True,
            subtitle_foreground=False,
            retry_failed=False,
        )
        resume_command_payload, resume_command_return_code = _run_resume_command_dry_run(play_payload.get("resumeCommand"))
        resume_subtitle_payload, resume_subtitle_return_code = _run_resume_subtitle_window_smoke(
            report_path,
            enabled=bool(args.open_subtitle and args.subtitle_exit_after > 0),
        )
        subtitle_auto_close_payload = _smoke_subtitle_auto_close_payload(
            play_payload,
            resume_subtitle_payload,
            exit_after=args.subtitle_exit_after,
            enabled=bool(args.open_subtitle and args.subtitle_exit_after > 0),
        )
        source_log_feedback_payload, source_log_feedback_return_code = _run_source_log_feedback_smoke(
            play_payload,
            log_path=log_path,
            source_line=_SMOKE_LIVE_APPEND_LINE,
            replay_event_log_path=source_log_feedback_replay_path,
            model=args.model,
        )
        source_log_subtitle_payload, source_log_subtitle_return_code = _run_source_log_subtitle_window_smoke(
            play_payload,
            log_path=log_path,
            event_log_path=source_log_feedback_runtime_path,
            expected_text=_SMOKE_LIVE_APPEND_TRANSLATION,
            exit_after=args.subtitle_exit_after,
            enabled=bool(args.open_subtitle and args.subtitle_exit_after > 0),
        )
        source_log_live_refresh_payload, source_log_live_refresh_return_code = _run_live_source_log_refresh_smoke(
            play_payload,
            log_path=log_path,
            event_log_path=source_log_live_refresh_runtime_path,
            source_line=_SMOKE_LIVE_REFRESH_LINE,
            expected_text=_SMOKE_LIVE_REFRESH_TRANSLATION,
            model=args.model,
            exit_after=args.subtitle_exit_after,
            enabled=bool(args.open_subtitle and args.subtitle_exit_after > 0),
        )
        live_session_payload, live_session_return_code = _run_live_session_smoke(
            game_path=live_game_path,
            log_path=live_log_path,
            workspace=workspace,
            report_path=live_report_path,
            model=args.model,
        )
        retry_failed_payload, retry_failed_return_code = _run_retry_failed_resume_smoke(
            game_path=retry_game_path,
            workspace=workspace,
            report_path=retry_report_path,
            model=args.model,
        )
    finally:
        os.environ["PATH"] = old_path
        if not args.keep_fake_codex:
            try:
                fake_codex_path.unlink()
            except OSError:
                pass

    checks = {
        "capturedEntries": play_payload.get("capture", {}).get("captureStats", {}).get("importedEntryCount", 0) > 0,
        "translationReady": play_payload.get("translateAll", {}).get("status") == "ready",
        "replayMatched": play_payload.get("replay", {}).get("matched", 0) > 0,
        "subtitleReady": play_payload.get("sessionSummary", {}).get("status") in {"subtitle_ready", "subtitle_started"},
        "subtitlePreviewMatched": play_payload.get("subtitleWindow", {}).get("preview", {}).get("matchType") == "exact",
        "subtitleWindowStarted": (not args.open_subtitle)
        or _detached_subtitle_started(play_payload.get("subtitleWindow", {})),
        "reportWritten": report_path.is_file(),
        "resumePlanned": resume_payload.get("status") == "subtitle_planned",
        "sessionInfoResumeCommand": _smoke_session_info_has_resume_command(session_info_payload, report_path),
        "savedResumeCommandExecutable": resume_command_payload.get("status") == "subtitle_planned",
        "savedResumeCommandMatchesSessionInfo": _smoke_saved_resume_command_matches_session_info(play_payload, session_info_payload),
        "savedResumeCommandPlansWatchers": _smoke_resume_command_plans_watchers(resume_command_payload),
        "resumeSubtitleWindowStarted": (not (args.open_subtitle and args.subtitle_exit_after > 0))
        or _smoke_resume_subtitle_window_started(resume_subtitle_payload),
        "subtitleWindowAutoClosed": (not (args.open_subtitle and args.subtitle_exit_after > 0))
        or _smoke_auto_close_ok(subtitle_auto_close_payload, "playSession"),
        "resumeSubtitleWindowAutoClosed": (not (args.open_subtitle and args.subtitle_exit_after > 0))
        or _smoke_auto_close_ok(subtitle_auto_close_payload, "resumeSession"),
        "sourceLogFeedbackTranslated": _smoke_source_log_feedback_translated(source_log_feedback_payload),
        "sourceLogSubtitleWindowDisplayed": (not (args.open_subtitle and args.subtitle_exit_after > 0))
        or _smoke_source_log_subtitle_displayed(source_log_subtitle_payload),
        "sourceLogLiveRefreshDisplayed": (not (args.open_subtitle and args.subtitle_exit_after > 0))
        or _smoke_live_source_log_refresh_displayed(source_log_live_refresh_payload),
        "liveSessionCompleted": _smoke_live_session_completed(live_session_payload),
        "liveSessionReportRecoverable": _smoke_live_session_report_recoverable(live_session_payload),
        "liveSessionResumeExecutable": _smoke_live_session_resume_executable(live_session_payload),
        "retryFailedResumeRecovered": _smoke_retry_failed_resume_recovered(retry_failed_payload),
    }
    status = (
        "passed"
        if all(checks.values())
        and play_return_code == 0
        and resume_return_code == 0
        and resume_command_return_code == 0
        and resume_subtitle_return_code == 0
        and source_log_feedback_return_code == 0
        and source_log_subtitle_return_code == 0
        and source_log_live_refresh_return_code == 0
        and live_session_return_code == 0
        and retry_failed_return_code == 0
        else "failed"
    )
    payload = {
        "status": status,
        "workspace": str(workspace),
        "smokeRoot": str(smoke_root),
        "fakeCodexPath": str(fake_codex_path),
        "fakeCodexKept": bool(args.keep_fake_codex and fake_codex_path.exists()),
        "openSubtitle": bool(args.open_subtitle),
        "gamePath": str(game_path),
        "logPath": str(log_path),
        "replayEventLogPath": str(replay_log_path),
        "runtimeEventLogPath": str(runtime_log_path),
        "missLogPath": str(miss_log_path),
        "sessionReportPath": str(report_path),
        "checks": checks,
        "inspectLog": inspect_payload,
        "playSession": play_payload,
        "sessionInfo": session_info_payload,
        "resumeSession": resume_payload,
        "savedResumeCommand": resume_command_payload,
        "resumeSubtitleWindow": resume_subtitle_payload,
        "subtitleAutoClose": subtitle_auto_close_payload,
        "sourceLogFeedback": source_log_feedback_payload,
        "sourceLogSubtitleWindow": source_log_subtitle_payload,
        "sourceLogLiveRefresh": source_log_live_refresh_payload,
        "liveSession": live_session_payload,
        "retryFailedResume": retry_failed_payload,
        "nextActions": _smoke_test_next_actions(status, report_path),
    }
    return payload, 0 if status == "passed" else 1


def _run_resume_command_dry_run(command: Any) -> tuple[dict[str, Any], int]:
    if not isinstance(command, list) or not command:
        return {
            "status": "missing_command",
            "command": command,
            "nextActions": ["Fix play-session resumeCommand generation, then rerun smoke-test."],
        }, 1
    result = subprocess.run(
        [str(part) for part in command + ["--dry-run"]],
        check=False,
        capture_output=True,
    )
    stdout = result.stdout.decode("utf-8", errors="replace")
    stderr = result.stderr.decode("utf-8", errors="replace")
    try:
        payload = json.loads(stdout) if stdout.strip() else {}
    except json.JSONDecodeError:
        payload = {
            "status": "invalid_json",
            "stdout": stdout,
            "stderr": stderr,
            "nextActions": ["Review saved resumeCommand output, then rerun smoke-test."],
        }
    if isinstance(payload, dict):
        payload.setdefault("commandExecuted", command + ["--dry-run"])
        if stderr:
            payload.setdefault("stderr", stderr)
    return payload if isinstance(payload, dict) else {"status": "invalid_payload", "payload": payload}, result.returncode


def _run_resume_subtitle_window_smoke(report_path: Path, enabled: bool) -> tuple[dict[str, Any], int]:
    if not enabled:
        return {"status": "skipped", "reason": "requires --open-subtitle and --subtitle-exit-after"}, 0
    command = [sys.executable, "-m", "gal_translator", "resume-session", str(report_path), "--open-subtitle"]
    result = subprocess.run(
        command,
        check=False,
        capture_output=True,
    )
    stdout = result.stdout.decode("utf-8", errors="replace")
    stderr = result.stderr.decode("utf-8", errors="replace")
    try:
        payload = json.loads(stdout) if stdout.strip() else {}
    except json.JSONDecodeError:
        payload = {
            "status": "invalid_json",
            "stdout": stdout,
            "stderr": stderr,
            "nextActions": ["Review resume-session subtitle startup output, then rerun smoke-test."],
        }
    if isinstance(payload, dict):
        payload.setdefault("commandExecuted", command)
        if stderr:
            payload.setdefault("stderr", stderr)
    return payload if isinstance(payload, dict) else {"status": "invalid_payload", "payload": payload}, result.returncode


def _smoke_saved_resume_command_matches_session_info(play_payload: dict[str, Any], session_info_payload: dict[str, Any]) -> bool:
    commands = session_info_payload.get("commands") if isinstance(session_info_payload.get("commands"), dict) else {}
    return play_payload.get("resumeCommand") == commands.get("resumeSessionCommand")


def _smoke_resume_command_plans_watchers(resume_payload: dict[str, Any]) -> bool:
    miss_watcher = resume_payload.get("missWatcher") if isinstance(resume_payload.get("missWatcher"), dict) else {}
    session_log_watcher = resume_payload.get("sessionLogWatcher") if isinstance(resume_payload.get("sessionLogWatcher"), dict) else {}
    return (
        resume_payload.get("status") == "subtitle_planned"
        and miss_watcher.get("dryRun") is True
        and isinstance(miss_watcher.get("command"), list)
        and session_log_watcher.get("dryRun") is True
        and isinstance(session_log_watcher.get("command"), list)
    )


def _smoke_resume_subtitle_window_started(resume_payload: dict[str, Any]) -> bool:
    if resume_payload.get("status") != "subtitle_started":
        return False
    subtitle_payload = resume_payload.get("subtitleWindow") if isinstance(resume_payload.get("subtitleWindow"), dict) else {}
    return _detached_subtitle_started(subtitle_payload)


def _smoke_subtitle_auto_close_payload(
    play_payload: dict[str, Any],
    resume_payload: dict[str, Any],
    *,
    exit_after: float,
    enabled: bool,
) -> dict[str, Any]:
    if not enabled:
        return {"status": "skipped", "reason": "requires --open-subtitle and --subtitle-exit-after"}
    timeout = max(1.0, float(exit_after)) + 3.0
    resume_subtitle = resume_payload.get("subtitleWindow") if isinstance(resume_payload.get("subtitleWindow"), dict) else {}
    checks = {
        "playSession": _wait_for_detached_process_exit(
            play_payload.get("subtitleWindow"),
            timeout_seconds=timeout,
        ),
        "resumeSession": _wait_for_detached_process_exit(
            resume_subtitle,
            timeout_seconds=timeout,
        ),
    }
    return {
        "status": "passed" if all(item.get("exited") for item in checks.values()) else "failed",
        "exitAfterSeconds": exit_after,
        "timeoutSeconds": timeout,
        "checks": checks,
    }


def _smoke_auto_close_ok(payload: dict[str, Any], key: str) -> bool:
    checks = payload.get("checks") if isinstance(payload.get("checks"), dict) else {}
    check = checks.get(key) if isinstance(checks.get(key), dict) else {}
    return check.get("exited") is True


def _wait_for_detached_process_exit(payload: Any, *, timeout_seconds: float) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {"exited": False, "reason": "missing_payload"}
    pid = payload.get("detachedPid")
    if not isinstance(pid, int) or pid <= 0:
        return {"exited": False, "reason": "missing_detached_pid"}
    deadline = time.monotonic() + max(0.1, timeout_seconds)
    while time.monotonic() < deadline:
        if not _process_is_running(pid):
            return {"pid": pid, "exited": True}
        time.sleep(0.1)
    return {"pid": pid, "exited": not _process_is_running(pid), "reason": "timeout"}


def _run_source_log_feedback_smoke(
    play_payload: dict[str, Any],
    *,
    log_path: Path,
    source_line: str,
    replay_event_log_path: Path,
    model: str,
) -> tuple[dict[str, Any], int]:
    project_root = play_payload.get("sessionSummary", {}).get("projectRoot")
    if not isinstance(project_root, str) or not project_root:
        return {"status": "missing_project_root"}, 1
    try:
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write("\n" + source_line + "\n")
    except OSError as error:
        return {"status": "append_failed", "error": str(error)}, 1
    command = [
        sys.executable,
        "-m",
        "gal_translator",
        "translate-log",
        project_root,
        str(log_path),
        "--source-name",
        "textractor",
        "--size",
        "2",
        "--model",
        model,
        "--timeout",
        "30",
        "--watch",
        "--watch-max-cycles",
        "1",
        "--watch-require-ready",
        "--replay-event-log",
        str(replay_event_log_path),
    ]
    watch_payload, watch_return_code = _run_jsonl_command(command)
    lookup_command = [
        sys.executable,
        "-m",
        "gal_translator",
        "lookup",
        project_root,
        source_line,
    ]
    lookup_payload, lookup_return_code = _run_json_command(lookup_command)
    status = "passed" if (
        watch_return_code == 0
        and lookup_return_code == 0
        and _smoke_source_log_feedback_event_processed(watch_payload)
        and lookup_payload.get("text")
        and lookup_payload.get("showSource") is False
    ) else "failed"
    return {
        "status": status,
        "appendedSourceLine": source_line,
        "replayEventLogPath": str(replay_event_log_path),
        "watch": watch_payload,
        "lookup": lookup_payload,
    }, 0 if status == "passed" else 1


def _run_jsonl_command(command: list[str]) -> tuple[dict[str, Any], int]:
    result = subprocess.run(command, check=False, capture_output=True)
    stdout = result.stdout.decode("utf-8", errors="replace")
    stderr = result.stderr.decode("utf-8", errors="replace")
    parsed: list[dict[str, Any]] = []
    invalid_lines: list[str] = []
    for line in stdout.splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            invalid_lines.append(line)
            continue
        if isinstance(item, dict):
            parsed.append(item)
    payload: dict[str, Any] = {
        "commandExecuted": command,
        "events": parsed,
        "lastEvent": parsed[-1] if parsed else None,
    }
    if invalid_lines:
        payload["invalidLines"] = invalid_lines
    if stderr:
        payload["stderr"] = stderr
    return payload, result.returncode


def _run_json_command(command: list[str]) -> tuple[dict[str, Any], int]:
    result = subprocess.run(command, check=False, capture_output=True)
    stdout = result.stdout.decode("utf-8", errors="replace")
    stderr = result.stderr.decode("utf-8", errors="replace")
    try:
        payload = json.loads(stdout) if stdout.strip() else {}
    except json.JSONDecodeError:
        payload = {"status": "invalid_json", "stdout": stdout}
    if isinstance(payload, dict):
        payload.setdefault("commandExecuted", command)
        if stderr:
            payload.setdefault("stderr", stderr)
    return payload if isinstance(payload, dict) else {"status": "invalid_payload", "payload": payload}, result.returncode


def _smoke_source_log_feedback_event_processed(payload: dict[str, Any]) -> bool:
    event = payload.get("lastEvent") if isinstance(payload.get("lastEvent"), dict) else {}
    result = event.get("result") if isinstance(event.get("result"), dict) else {}
    append = result.get("append") if isinstance(result.get("append"), dict) else {}
    translate_all = result.get("translateAll") if isinstance(result.get("translateAll"), dict) else {}
    replay = result.get("replay") if isinstance(result.get("replay"), dict) else {}
    return (
        event.get("status") == "processed"
        and append.get("addedEntryCount") == 1
        and translate_all.get("status") == "ready"
        and replay.get("matched", 0) >= 1
    )


def _smoke_source_log_feedback_translated(payload: dict[str, Any]) -> bool:
    watch_payload = payload.get("watch") if isinstance(payload.get("watch"), dict) else {}
    return payload.get("status") == "passed" and _smoke_source_log_feedback_event_processed(watch_payload)


def _run_source_log_subtitle_window_smoke(
    play_payload: dict[str, Any],
    *,
    log_path: Path,
    event_log_path: Path,
    expected_text: str,
    exit_after: float,
    enabled: bool,
) -> tuple[dict[str, Any], int]:
    if not enabled:
        return {"status": "skipped", "reason": "requires --open-subtitle and --subtitle-exit-after"}, 0
    project_root = play_payload.get("sessionSummary", {}).get("projectRoot")
    if not isinstance(project_root, str) or not project_root:
        return {"status": "missing_project_root"}, 1
    if event_log_path.exists():
        try:
            event_log_path.unlink()
        except OSError as error:
            return {"status": "event_log_cleanup_failed", "error": str(error)}, 1
    command = [
        sys.executable,
        "-m",
        "gal_translator",
        "subtitle-window",
        project_root,
        "--source-log",
        str(log_path),
        "--source-log-name",
        "textractor",
        "--source-log-from-start",
        "--event-log",
        str(event_log_path),
        "--exit-after",
        str(max(0.2, float(exit_after))),
        "--interval",
        "0.05",
        "--not-topmost",
    ]
    result = subprocess.run(command, check=False, capture_output=True)
    events = _read_jsonl_events(event_log_path)
    displayed = any(
        event.get("text") == expected_text
        and event.get("visible") is True
        and event.get("matchType") == "exact"
        for event in events
        if isinstance(event, dict)
    )
    stdout = result.stdout.decode("utf-8", errors="replace")
    stderr = result.stderr.decode("utf-8", errors="replace")
    payload: dict[str, Any] = {
        "status": "passed" if result.returncode == 0 and displayed else "failed",
        "commandExecuted": command,
        "returnCode": result.returncode,
        "eventLogPath": str(event_log_path),
        "eventCount": len(events),
        "expectedTextDisplayed": displayed,
        "expectedText": expected_text,
        "events": events,
    }
    if stdout:
        payload["stdout"] = stdout
    if stderr:
        payload["stderr"] = stderr
    return payload, 0 if payload["status"] == "passed" else 1


def _read_jsonl_events(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            events.append(item)
    return events


def _smoke_source_log_subtitle_displayed(payload: dict[str, Any]) -> bool:
    return payload.get("status") == "passed" and payload.get("expectedTextDisplayed") is True


def _run_live_source_log_refresh_smoke(
    play_payload: dict[str, Any],
    *,
    log_path: Path,
    event_log_path: Path,
    source_line: str,
    expected_text: str,
    model: str,
    exit_after: float,
    enabled: bool,
) -> tuple[dict[str, Any], int]:
    if not enabled:
        return {"status": "skipped", "reason": "requires --open-subtitle and --subtitle-exit-after"}, 0
    project_root = play_payload.get("sessionSummary", {}).get("projectRoot")
    if not isinstance(project_root, str) or not project_root:
        return {"status": "missing_project_root"}, 1
    if event_log_path.exists():
        try:
            event_log_path.unlink()
        except OSError as error:
            return {"status": "event_log_cleanup_failed", "error": str(error)}, 1
    exit_seconds = max(3.0, float(exit_after) + 2.0)
    command = [
        sys.executable,
        "-m",
        "gal_translator",
        "subtitle-window",
        project_root,
        "--source-log",
        str(log_path),
        "--source-log-name",
        "textractor",
        "--event-log",
        str(event_log_path),
        "--include-source",
        "--exit-after",
        str(exit_seconds),
        "--interval",
        "0.05",
        "--not-topmost",
    ]
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        time.sleep(0.3)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(source_line + "\n")
        unmatched_event = _wait_for_jsonl_event(
            event_log_path,
            lambda event: event.get("rawText") == source_line and event.get("matchType") == "unmatched",
            timeout_seconds=1.5,
        )
        watch_command = [
            sys.executable,
            "-m",
            "gal_translator",
            "translate-log",
            project_root,
            str(log_path),
            "--source-name",
            "textractor",
            "--size",
            "2",
            "--model",
            model,
            "--timeout",
            "30",
            "--watch",
            "--watch-max-cycles",
            "1",
            "--watch-require-ready",
        ]
        watch_payload, watch_return_code = _run_jsonl_command(watch_command)
        refreshed_event = _wait_for_jsonl_event(
            event_log_path,
            lambda event: (
                event.get("rawText") == source_line
                and event.get("text") == expected_text
                and event.get("visible") is True
                and event.get("matchType") == "exact"
            ),
            timeout_seconds=max(0.5, exit_seconds - 0.5),
        )
        try:
            stdout_bytes, stderr_bytes = process.communicate(timeout=exit_seconds + 2.0)
        except subprocess.TimeoutExpired:
            process.terminate()
            stdout_bytes, stderr_bytes = process.communicate(timeout=2.0)
    except OSError as error:
        process.terminate()
        stdout_bytes, stderr_bytes = process.communicate(timeout=2.0)
        return {
            "status": "failed",
            "commandExecuted": command,
            "error": str(error),
            "stdout": stdout_bytes.decode("utf-8", errors="replace"),
            "stderr": stderr_bytes.decode("utf-8", errors="replace"),
        }, 1
    events = _read_jsonl_events(event_log_path)
    passed = (
        process.returncode == 0
        and watch_return_code == 0
        and unmatched_event is not None
        and refreshed_event is not None
        and _smoke_watch_translated_new_entry(watch_payload)
    )
    return {
        "status": "passed" if passed else "failed",
        "commandExecuted": command,
        "returnCode": process.returncode,
        "eventLogPath": str(event_log_path),
        "eventCount": len(events),
        "unmatchedBeforeTranslation": unmatched_event is not None,
        "refreshedAfterTranslation": refreshed_event is not None,
        "expectedText": expected_text,
        "watch": watch_payload,
        "events": events,
        "stdout": stdout_bytes.decode("utf-8", errors="replace"),
        "stderr": stderr_bytes.decode("utf-8", errors="replace"),
    }, 0 if passed else 1


def _wait_for_jsonl_event(
    path: Path,
    predicate: Any,
    *,
    timeout_seconds: float,
) -> dict[str, Any] | None:
    deadline = time.monotonic() + max(0.1, timeout_seconds)
    while time.monotonic() < deadline:
        for event in _read_jsonl_events(path):
            if predicate(event):
                return event
        time.sleep(0.05)
    for event in _read_jsonl_events(path):
        if predicate(event):
            return event
    return None


def _smoke_live_source_log_refresh_displayed(payload: dict[str, Any]) -> bool:
    return (
        payload.get("status") == "passed"
        and payload.get("unmatchedBeforeTranslation") is True
        and payload.get("refreshedAfterTranslation") is True
    )


def _run_live_session_smoke(
    *,
    game_path: Path,
    log_path: Path,
    workspace: Path,
    report_path: Path,
    model: str,
) -> tuple[dict[str, Any], int]:
    command = [
        sys.executable,
        "-m",
        "gal_translator",
        "live-session",
        str(game_path),
        str(log_path),
        "--workspace",
        str(workspace),
        "--model",
        model,
        "--translate-dry-run",
        "--no-subtitle",
        "--subtitle-source-log",
        "--watch-max-cycles",
        "1",
        "--watch-interval",
        "0.1",
        "--session-report",
        str(report_path),
    ]
    live_payload, live_return_code = _run_json_command(command)
    session_info_payload, session_info_return_code = _run_json_command(
        [sys.executable, "-m", "gal_translator", "session-info", str(report_path)]
    )
    resume_payload, resume_return_code = _run_resume_command_dry_run(live_payload.get("resumeCommand"))
    payload = {
        "status": "passed" if (
            live_return_code == 0
            and session_info_return_code == 0
            and resume_return_code == 0
            and live_payload.get("status") == "completed"
            and session_info_payload.get("reportType") == "live-session"
            and resume_payload.get("status") == "translation_planned"
        ) else "failed",
        "commandExecuted": command,
        "reportPath": str(report_path),
        "liveSession": live_payload,
        "sessionInfo": session_info_payload,
        "resumeSession": resume_payload,
        "returnCodes": {
            "liveSession": live_return_code,
            "sessionInfo": session_info_return_code,
            "resumeSession": resume_return_code,
        },
    }
    return payload, 0 if payload["status"] == "passed" else 1


def _smoke_live_session_completed(payload: dict[str, Any]) -> bool:
    live_payload = payload.get("liveSession") if isinstance(payload.get("liveSession"), dict) else {}
    return (
        payload.get("status") == "passed"
        and live_payload.get("status") == "completed"
        and live_payload.get("session", {}).get("sessionSummary", {}).get("status") == "translation_planned"
    )


def _smoke_live_session_report_recoverable(payload: dict[str, Any]) -> bool:
    session_info = payload.get("sessionInfo") if isinstance(payload.get("sessionInfo"), dict) else {}
    commands = session_info.get("commands") if isinstance(session_info.get("commands"), dict) else {}
    return (
        session_info.get("reportType") == "live-session"
        and isinstance(commands.get("watchMissLogCommand"), list)
        and isinstance(commands.get("watchSessionLogCommand"), list)
        and "--start-session-log-watcher" in (commands.get("resumeSessionCommand") or [])
    )


def _smoke_live_session_resume_executable(payload: dict[str, Any]) -> bool:
    resume_payload = payload.get("resumeSession") if isinstance(payload.get("resumeSession"), dict) else {}
    return resume_payload.get("status") == "translation_planned"


def _run_retry_failed_resume_smoke(
    *,
    game_path: Path,
    workspace: Path,
    report_path: Path,
    model: str,
) -> tuple[dict[str, Any], int]:
    project = TranslationProjectManager(workspace).create_project(game_path)
    tracker = TranslationProgressTracker.initialize(
        project,
        [ScriptEntry("retry:1", _SMOKE_RETRY_FAILED_LINE, None, "retry", 1, "clipboard_capture")],
    )
    tracker.mark_failed("retry:1", "synthetic retry failure")
    report_payload = {
        "sessionSummary": {
            "status": "translation_needs_attention",
            "projectRoot": str(project.project_root),
            "batchSize": 1,
            "model": model,
            "translateTimeout": 30,
            "translateMaxBatches": 0,
        },
        "projectInfo": {"projectRoot": str(project.project_root)},
        "sessionReportPath": str(report_path),
    }
    _write_json_report(report_path, report_payload)
    dry_run_payload, dry_run_return_code = _run_json_command(
        [
            sys.executable,
            "-m",
            "gal_translator",
            "resume-session",
            str(report_path),
            "--retry-failed",
            "--dry-run",
        ]
    )
    resume_payload, resume_return_code = _run_json_command(
        [
            sys.executable,
            "-m",
            "gal_translator",
            "resume-session",
            str(report_path),
            "--retry-failed",
        ]
    )
    project_info_payload, project_info_return_code = _run_json_command(
        [sys.executable, "-m", "gal_translator", "project-info", str(project.project_root)]
    )
    passed = (
        dry_run_return_code == 0
        and resume_return_code == 0
        and project_info_return_code == 0
        and dry_run_payload.get("status") == "retry_failed_planned"
        and resume_payload.get("status") == "subtitle_ready"
        and resume_payload.get("retryFailed", {}).get("resetCount") == 1
        and resume_payload.get("translateAll", {}).get("status") == "ready"
        and project_info_payload.get("progress", {}).get("status") == "ready"
    )
    return {
        "status": "passed" if passed else "failed",
        "reportPath": str(report_path),
        "projectRoot": str(project.project_root),
        "dryRun": dry_run_payload,
        "resumeSession": resume_payload,
        "projectInfo": project_info_payload,
        "returnCodes": {
            "dryRun": dry_run_return_code,
            "resumeSession": resume_return_code,
            "projectInfo": project_info_return_code,
        },
    }, 0 if passed else 1


def _smoke_retry_failed_resume_recovered(payload: dict[str, Any]) -> bool:
    resume_payload = payload.get("resumeSession") if isinstance(payload.get("resumeSession"), dict) else {}
    project_info = payload.get("projectInfo") if isinstance(payload.get("projectInfo"), dict) else {}
    return (
        payload.get("status") == "passed"
        and payload.get("dryRun", {}).get("status") == "retry_failed_planned"
        and resume_payload.get("retryFailed", {}).get("resetCount") == 1
        and resume_payload.get("translateAll", {}).get("status") == "ready"
        and project_info.get("progress", {}).get("status") == "ready"
    )


def _smoke_watch_translated_new_entry(payload: dict[str, Any]) -> bool:
    event = payload.get("lastEvent") if isinstance(payload.get("lastEvent"), dict) else {}
    result = event.get("result") if isinstance(event.get("result"), dict) else {}
    append = result.get("append") if isinstance(result.get("append"), dict) else {}
    translate_all = result.get("translateAll") if isinstance(result.get("translateAll"), dict) else {}
    return (
        event.get("status") == "processed"
        and append.get("addedEntryCount") == 1
        and translate_all.get("status") == "ready"
    )


_SMOKE_LIVE_APPEND_LINE = "これは追加テストです。"
_SMOKE_LIVE_APPEND_TRANSLATION = "追加テストの翻訳"
_SMOKE_LIVE_REFRESH_LINE = "\u3053\u308c\u306f\u30e9\u30a4\u30d6\u66f4\u65b0\u30c6\u30b9\u30c8\u3067\u3059\u3002"
_SMOKE_LIVE_REFRESH_TRANSLATION = "\u5b9e\u65f6\u66f4\u65b0\u6d4b\u8bd5\u7ffb\u8bd1"
_SMOKE_LIVE_SESSION_LINE = "\u3053\u308c\u306f\u30e9\u30a4\u30d6\u30bb\u30c3\u30b7\u30e7\u30f3\u30c6\u30b9\u30c8\u3067\u3059\u3002"
_SMOKE_RETRY_FAILED_LINE = "\u3053\u308c\u306f\u30ea\u30c8\u30e9\u30a4\u30c6\u30b9\u30c8\u3067\u3059\u3002"
_SMOKE_CAPTURE_LINES = [
    "邵ｺ鄙ｫ繝ｻ郢ｧ蛹ｻ竕ｧ",
    "邵ｺ・ｾ邵ｺ貅倥・",
]


def _default_smoke_workspace(run_id: str) -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    return base / "GalTranslator" / "smoke-tests" / run_id


def _write_smoke_fake_codex(fake_bin: Path) -> Path:
    helper_path = fake_bin / "codex_fake.py"
    translations = {
        "textractor:1": "辜滄崟豬玖ｯ慕ｬｬ荳蜿･",
        "textractor:2": "辜滄崟豬玖ｯ慕ｬｬ莠悟唱",
        "textractor:3": "追加テストの翻訳",
        "textractor:4": _SMOKE_LIVE_REFRESH_TRANSLATION,
    }
    helper_path.write_text(
        "\n".join(
            [
                "import json",
                "import re",
                "import sys",
                f"translations = json.loads({json.dumps(json.dumps(translations, ensure_ascii=False))})",
                "out = ''",
                "args = sys.argv[1:]",
                "for index, arg in enumerate(args):",
                "    if arg == '-o' and index + 1 < len(args):",
                "        out = args[index + 1]",
                "prompt = sys.stdin.read()",
                "ids = []",
                "for match in re.finditer(r'\"id\"\\s*:\\s*\"([^\"]+)\"', prompt):",
                "    entry_id = match.group(1)",
                "    if entry_id not in ids:",
                "        ids.append(entry_id)",
                "items = [",
                "    {'id': entry_id, 'translation': translations.get(entry_id, '翻译-' + entry_id), 'notes': None}",
                "    for entry_id in ids",
                "]",
                "payload = json.dumps({'items': items}, ensure_ascii=False)",
                "if out:",
                "    open(out, 'w', encoding='utf-8').write(payload)",
                "else:",
                "    print(payload)",
            ]
        ),
        encoding="utf-8",
    )
    if sys.platform == "win32":
        path = fake_bin / "codex.cmd"
        path.write_text(
            "\r\n".join(
                [
                    "@echo off",
                    f"\"{sys.executable}\" \"%~dp0codex_fake.py\" %*",
                ]
            ),
            encoding="utf-8",
        )
        return path
    path = fake_bin / "codex"
    path.write_text(
        "\n".join(
            [
                "#!/usr/bin/env sh",
                f"exec \"{sys.executable}\" \"$(dirname \"$0\")/codex_fake.py\" \"$@\"",
            ]
        ),
        encoding="utf-8",
    )
    path.chmod(0o755)
    return path

    result = {
        "items": [
            {"id": "textractor:1", "translation": "烟雾测试第一句", "notes": None},
            {"id": "textractor:2", "translation": "烟雾测试第二句", "notes": None},
        ]
    }
    if sys.platform == "win32":
        path = fake_bin / "codex.cmd"
        payload = json.dumps(result, ensure_ascii=True).replace('"', '^"')
        path.write_text(
            "\r\n".join(
                [
                    "@echo off",
                    "set \"out=\"",
                    ":loop",
                    "if \"%~1\"==\"\" goto done",
                    "if \"%~1\"==\"-o\" (",
                    "  set \"out=%~2\"",
                    "  shift",
                    ")",
                    "shift",
                    "goto loop",
                    ":done",
                    f"> \"%out%\" echo {payload}",
                    "exit /b 0",
                ]
            ),
            encoding="utf-8",
        )
        return path
    path = fake_bin / "codex"
    path.write_text(
        "\n".join(
            [
                "#!/usr/bin/env sh",
                "out=\"\"",
                "while [ \"$#\" -gt 0 ]; do",
                "  if [ \"$1\" = \"-o\" ]; then out=\"$2\"; shift; fi",
                "  shift",
                "done",
                f"printf '%s\\n' '{json.dumps(result, ensure_ascii=False)}' > \"$out\"",
            ]
        ),
        encoding="utf-8",
    )
    path.chmod(0o755)
    return path


def _smoke_test_next_actions(status: str, report_path: Path) -> list[str]:
    if status == "passed":
        return [
            "Local synthetic workflow passed. Run the returned resumeCommand, or move on to a real Textractor/clipboard log.",
            f"Inspect the saved report with session-info: {report_path}",
        ]
    return [
        "Review the nested playSession, sessionInfo, and resumeSession payloads, then rerun smoke-test after fixing the reported issue."
    ]


def _smoke_session_info_has_resume_command(session_info_payload: dict[str, Any], report_path: Path) -> bool:
    commands = session_info_payload.get("commands") if isinstance(session_info_payload.get("commands"), dict) else {}
    command = commands.get("resumeSessionCommand")
    if not (isinstance(command, list) and "resume-session" in command and str(report_path) in command):
        return False
    subtitle_command = commands.get("subtitleWindowCommand")
    if isinstance(subtitle_command, list) and subtitle_command:
        return "--open-subtitle" in command
    return True


def _detached_subtitle_started(subtitle_payload: Any) -> bool:
    if not isinstance(subtitle_payload, dict):
        return False
    if subtitle_payload.get("started") is not True:
        return False
    if subtitle_payload.get("detachedRunning") is True:
        return True
    return subtitle_payload.get("detachedReturnCode") == 0


def _play_session_payload(args: Any) -> tuple[dict[str, Any], int]:
    game_path = Path(args.path)
    workspace = Path(args.workspace)
    log_path = Path(args.log_file) if args.log_file else _default_session_log_path(game_path, workspace)
    launch_payload = None
    if args.launch_game:
        launch_payload = _launch_game_payload(game_path)

    record_payload = None
    if args.record_clipboard:
        record_payload = _record_clipboard_payload(
            provider=WindowsClipboardProvider(),
            log_path=log_path,
            interval=args.record_interval,
            max_events=args.record_max_events,
            duration=_play_session_record_duration(args),
            append=not args.overwrite_log,
        )

    doctor = _doctor_payload(workspace)
    report = GameScanner().scan(game_path)
    candidates = EngineDetector().detect(report)
    project = TranslationProjectManager(workspace).create_project(game_path)
    existing_state_before_capture = (project.project_root / "translation-state.json").is_file()
    capture = ClipboardLogImporter().import_log(
        log_path,
        source_name=args.source_name,
        encoding=args.encoding,
    )
    capture_payload = _capture_project_payload(project, capture, append=args.append)

    translate_payload, translate_return_code = _translate_all_payload(
        project_root=project.project_root,
        batch_size=args.batch_size,
        model=args.model,
        max_batches=args.translate_max_batches,
        timeout=args.translate_timeout,
        dry_run=args.translate_dry_run,
        retry_failed=getattr(args, "translate_retry_failed", False),
    )

    replay_payload = None
    if args.replay_event_log is not None:
        records = _translation_records_from_state(project.project_root / "translation-state.json")
        runtime = RuntimeSubtitleService(MatchIndex(records))
        replay_payload = _replay_log_payload(runtime, capture.entries, 0, args.replay_include_source)
        _write_runtime_events_jsonl(Path(args.replay_event_log), replay_payload["events"])
        replay_payload["eventLogPath"] = str(Path(args.replay_event_log))

    subtitle_payload = None
    subtitle_started = False
    has_source_entries = translate_payload.get("finalProgress", {}).get("total", 0) > 0
    if not args.no_subtitle and has_source_entries:
        subtitle_config_path = Path(args.subtitle_config) if getattr(args, "subtitle_config", None) else None
        loaded_config = None
        if subtitle_config_path is not None:
            try:
                loaded_config = _load_subtitle_window_config(subtitle_config_path)
            except (OSError, json.JSONDecodeError, TypeError) as error:
                return _error_payload(
                    "subtitle_config_invalid",
                    f"subtitle config could not be loaded: {subtitle_config_path}: {error}",
                    ["Fix or remove --subtitle-config, then rerun play-session/live-session."],
                ), 1
        config = _subtitle_config_from_args(args, loaded_config)
        saved_subtitle_config_path = Path(args.subtitle_save_config) if getattr(args, "subtitle_save_config", None) else None
        if saved_subtitle_config_path is not None:
            try:
                _write_subtitle_window_config(saved_subtitle_config_path, config)
            except OSError as error:
                return _error_payload(
                    "subtitle_config_write_failed",
                    f"subtitle config could not be written: {saved_subtitle_config_path}: {error}",
                    ["Check the output path permissions, then rerun play-session/live-session --subtitle-save-config."],
                ), 1
        subtitle_dry_run = args.subtitle_dry_run or args.translate_dry_run or translate_return_code != 0
        subtitle_records = _translation_records_from_state(project.project_root / "translation-state.json")
        subtitle_runtime = RuntimeSubtitleService(MatchIndex(subtitle_records))
        subtitle_preview_source = _subtitle_preview_source(
            explicit_source=args.subtitle_preview_source,
            use_first_match=args.subtitle_preview_first_match,
            entries=capture.entries,
            runtime=subtitle_runtime,
        )
        subtitle_source_log = str(log_path) if args.subtitle_source_log else None
        subtitle_payload = {
            "projectRoot": str(project.project_root),
            "recordCount": len(subtitle_records),
            "config": _subtitle_window_config_payload(config),
            "configPath": str(subtitle_config_path) if subtitle_config_path is not None else None,
            "savedConfigPath": str(saved_subtitle_config_path) if saved_subtitle_config_path is not None else None,
            "input": _subtitle_input_payload(
                source_log=subtitle_source_log,
                source_log_encoding=args.encoding,
                source_log_name=args.source_name,
                source_log_from_start=args.subtitle_source_log_from_start,
            ),
            "reloadEnabled": not args.subtitle_no_reload,
            "eventLogEnabled": not args.subtitle_no_log,
            "eventLogPath": _subtitle_event_log_path(project.project_root, args.subtitle_event_log, args.subtitle_no_log),
            "missLogPath": str(Path(args.subtitle_miss_log)) if args.subtitle_miss_log else None,
            "preview": _subtitle_preview_payload(subtitle_runtime, subtitle_preview_source, args.subtitle_include_source),
            "command": _subtitle_window_command(
                project.project_root,
                config,
                no_log=args.subtitle_no_log,
                event_log_arg=args.subtitle_event_log,
                include_source=args.subtitle_include_source,
                miss_log_arg=args.subtitle_miss_log,
                reload_enabled=not args.subtitle_no_reload,
                preview_source=subtitle_preview_source,
                source_log=subtitle_source_log,
                source_log_encoding=args.encoding,
                source_log_name=args.source_name,
                source_log_from_start=args.subtitle_source_log_from_start,
            ),
            "dryRun": subtitle_dry_run,
        }
        if not subtitle_dry_run:
            if args.subtitle_detach:
                detached = _start_detached_subtitle_window(
                    subtitle_payload["command"],
                    cwd=Path.cwd(),
                    log_dir=project.project_root / "logs" / "subtitle-window",
                )
                subtitle_payload.update(detached)
            else:
                _run_subtitle_window_for_project(
                    project.project_root,
                    config,
                    no_log=args.subtitle_no_log,
                    event_log_arg=args.subtitle_event_log,
                    include_source=args.subtitle_include_source,
                    miss_log_arg=args.subtitle_miss_log,
                    reload_enabled=not args.subtitle_no_reload,
                    preview_source=subtitle_preview_source,
                    source_log=subtitle_source_log,
                    source_log_encoding=args.encoding,
                    source_log_name=args.source_name,
                    source_log_from_start=args.subtitle_source_log_from_start,
                )
            subtitle_started = True
        subtitle_payload["detached"] = bool(args.subtitle_detach and subtitle_started)
        subtitle_payload["started"] = subtitle_started

    payload = {
        "sessionSummary": _play_session_summary(
            capture_payload,
            translate_payload,
            replay_payload,
            subtitle_payload,
            append=args.append,
            existing_state_before_capture=existing_state_before_capture,
            batch_size=args.batch_size,
            model=args.model,
            timeout=args.translate_timeout,
            max_batches=args.translate_max_batches,
            translate_retry_failed=getattr(args, "translate_retry_failed", False),
            session_log_path=str(log_path),
            session_log_source_name=args.source_name,
        ),
        "doctor": doctor,
        "launchGame": launch_payload,
        "recordClipboard": record_payload,
        "sessionLogPath": str(log_path),
        "scan": {
            "gameRoot": str(report.game_root),
            "engineCandidates": [_candidate_payload(candidate) for candidate in candidates],
            "nextActions": _scan_next_actions(report, candidates),
        },
        "capture": capture_payload,
        "translateAll": translate_payload,
        "replay": replay_payload,
        "subtitleWindow": subtitle_payload,
        "projectInfo": _project_info_payload(project.project_root),
    }
    payload["nextActions"] = _play_session_next_actions(payload["sessionSummary"], translate_payload, replay_payload, subtitle_payload)
    return payload, translate_return_code


def _live_session_payload(args: Any) -> tuple[dict[str, Any], int]:
    game_path = Path(args.path)
    workspace = Path(args.workspace)
    log_path = Path(args.log_file) if args.log_file else _default_session_log_path(game_path, workspace)
    project = TranslationProjectManager(workspace).create_project(game_path)
    project_root = project.project_root
    project_log_dir = project_root / "logs"
    project_log_dir.mkdir(parents=True, exist_ok=True)
    miss_log_path = Path(args.subtitle_miss_log) if args.subtitle_miss_log else log_path.parent / "misses.txt"
    report_path = Path(args.session_report) if args.session_report else project_log_dir / f"live-session-{_run_id()}.json"
    watcher_payloads: dict[str, Any] = {
        "missWatcher": _watcher_not_started_payload(),
        "sessionLogWatcher": _watcher_not_started_payload(),
    }
    started_watchers: list[subprocess.Popen[Any]] = []
    keep_watchers = bool(args.keep_watchers)
    try:
        if not args.no_miss_watcher:
            command = _watch_miss_log_command(
                str(project_root),
                str(miss_log_path),
                batch_size=args.batch_size,
                model=args.model,
                timeout=args.translate_timeout,
                max_batches=args.translate_max_batches,
            )
            if command is not None:
                command = _watch_command_with_live_options(command, args)
                payload, process = _start_live_watcher(
                    command,
                    stdout_path=project_log_dir / "miss-watch.jsonl",
                    stderr_path=project_log_dir / "miss-watch-stderr.txt",
                )
                watcher_payloads["missWatcher"] = payload
                started_watchers.append(process)
        if args.subtitle_source_log and not args.no_session_log_watcher:
            command = _watch_log_command(
                str(project_root),
                str(log_path),
                source_name=args.source_name,
                batch_size=args.batch_size,
                model=args.model,
                timeout=args.translate_timeout,
                max_batches=args.translate_max_batches,
            )
            if command is not None:
                command = _watch_command_with_live_options(command, args)
                payload, process = _start_live_watcher(
                    command,
                    stdout_path=project_log_dir / "session-log-watch.jsonl",
                    stderr_path=project_log_dir / "session-log-watch-stderr.txt",
                )
                watcher_payloads["sessionLogWatcher"] = payload
                started_watchers.append(process)

        play_args = argparse.Namespace(**vars(args))
        play_args.command = "play-session"
        play_args.log_file = str(log_path)
        play_args.subtitle_miss_log = str(miss_log_path)
        play_args.session_report = None
        session_payload, session_return_code = _play_session_payload(play_args)
        session_payload["sessionReportPath"] = str(report_path)
        session_payload["resumeCommand"] = _resume_session_command_for_payload(report_path, session_payload)
        session_status = session_payload.get("sessionSummary", {}).get("status")
        subtitle_payload = session_payload.get("subtitleWindow") if isinstance(session_payload.get("subtitleWindow"), dict) else {}
        if subtitle_payload.get("detached") and session_status != "subtitle_exited":
            keep_watchers = True
        if args.translate_dry_run:
            _wait_for_live_watchers(started_watchers, timeout_seconds=10.0)
        _refresh_live_watcher_payload(watcher_payloads["missWatcher"], keep_running=keep_watchers)
        _refresh_live_watcher_payload(watcher_payloads["sessionLogWatcher"], keep_running=keep_watchers)
        _attach_live_watcher_diagnostics(watcher_payloads["missWatcher"])
        _attach_live_watcher_diagnostics(watcher_payloads["sessionLogWatcher"])
        payload: dict[str, Any] = {
            "status": "completed" if session_return_code == 0 else "failed",
            "projectRoot": str(project_root),
            "sessionLogPath": str(log_path),
            "sessionReportPath": str(report_path),
            "resumeCommand": _live_resume_command(report_path, args),
            "subtitleMissLog": str(miss_log_path),
            **watcher_payloads,
            "sessionExitCode": session_return_code,
            "session": session_payload,
        }
        payload["nextActions"] = _live_session_next_actions(payload, session_status)
        _write_json_report(report_path, payload)
        return payload, session_return_code
    finally:
        if not keep_watchers:
            for process in started_watchers:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=2.0)
                    except subprocess.TimeoutExpired:
                        process.kill()


def _watch_command_with_live_options(command: list[str], args: Any) -> list[str]:
    extended = list(command)
    extended.extend(["--watch-interval", _format_seconds(max(0.1, args.watch_interval))])
    if args.watch_max_cycles > 0:
        extended.extend(["--watch-max-cycles", str(args.watch_max_cycles)])
    if args.watch_idle_cycles > 0:
        extended.extend(["--watch-idle-cycles", str(args.watch_idle_cycles)])
    if args.translate_dry_run:
        extended.append("--dry-run")
    return extended


def _start_live_watcher(command: list[str], stdout_path: Path, stderr_path: Path) -> tuple[dict[str, Any], subprocess.Popen[Any]]:
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    stderr_path.parent.mkdir(parents=True, exist_ok=True)
    stdout_handle = stdout_path.open("w", encoding="utf-8")
    stderr_handle = stderr_path.open("w", encoding="utf-8")
    try:
        process = subprocess.Popen(
            [str(part) for part in command],
            stdout=stdout_handle,
            stderr=stderr_handle,
            stdin=subprocess.DEVNULL,
        )
    finally:
        stdout_handle.close()
        stderr_handle.close()
    payload = {
        "started": True,
        "pid": process.pid,
        "stdoutPath": str(stdout_path),
        "stderrPath": str(stderr_path),
        "activeAtSummary": process.poll() is None,
        "willStopOnExit": False,
        "running": process.poll() is None,
        "command": command,
    }
    return payload, process


def _watcher_not_started_payload() -> dict[str, Any]:
    return {
        "started": False,
        "pid": None,
        "stdoutPath": None,
        "stderrPath": None,
        "activeAtSummary": False,
        "willStopOnExit": False,
        "running": False,
        "command": None,
    }


def _wait_for_live_watchers(processes: list[subprocess.Popen[Any]], timeout_seconds: float) -> None:
    deadline = time.monotonic() + max(0.1, timeout_seconds)
    for process in processes:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return
        try:
            process.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            return


def _refresh_live_watcher_payload(payload: dict[str, Any], keep_running: bool) -> None:
    pid = payload.get("pid")
    active = _process_is_running(pid) if isinstance(pid, int) else False
    payload["activeAtSummary"] = active
    payload["willStopOnExit"] = active and not keep_running
    payload["running"] = active and keep_running


def _attach_live_watcher_diagnostics(payload: dict[str, Any]) -> None:
    diagnostics = _session_miss_watcher_payload(payload)
    if diagnostics is None:
        return
    payload.update(diagnostics)


def _live_resume_command(report_path: Path, args: Any) -> list[str]:
    command = [sys.executable, "-m", "gal_translator", "resume-session", str(report_path)]
    if not args.no_subtitle:
        command.append("--open-subtitle")
    if not args.no_miss_watcher:
        command.append("--start-miss-watcher")
    if args.subtitle_source_log and not args.no_session_log_watcher:
        command.append("--start-session-log-watcher")
    if getattr(args, "translate_retry_failed", False):
        command.append("--retry-failed")
    return command


def _live_session_next_actions(payload: dict[str, Any], session_status: str | None) -> list[str]:
    actions: list[str] = []
    if payload.get("status") != "completed":
        actions.append("Review the nested session payload and watcher logs, then rerun live-session after fixing the issue.")
    elif session_status == "translation_planned":
        actions.append("Rerun live-session without --translate-dry-run to execute Codex translation batches.")
    elif session_status == "subtitle_started":
        actions.append("Keep playing with the subtitle window open; background watchers translate appended source and miss logs.")
    elif session_status == "subtitle_ready":
        actions.append("Rerun live-session without --subtitle-dry-run, or run resumeCommand to open subtitles and watchers.")
    elif session_status == "no_source_text":
        actions.append("No Japanese source lines were captured; check the Textractor/clipboard log and rerun live-session.")
    else:
        actions.append("Review session.sessionSummary.nextActions for the next step.")
    miss_watcher_action = _live_watcher_next_action(
        payload.get("missWatcher"),
        label="Miss-log watcher",
        payload_key="missWatcher",
        subject="unmatched subtitle lines",
    )
    if miss_watcher_action:
        actions.append(miss_watcher_action)
    session_log_action = _live_watcher_next_action(
        payload.get("sessionLogWatcher"),
        label="Session-log watcher",
        payload_key="sessionLogWatcher",
        subject="appended source-log lines",
    )
    if session_log_action:
        actions.append(session_log_action)
    return actions


def _live_watcher_next_action(payload: Any, *, label: str, payload_key: str, subject: str) -> str | None:
    if not isinstance(payload, dict) or not payload.get("started"):
        return None
    summary = payload.get("statusSummary") if isinstance(payload.get("statusSummary"), dict) else {}
    reason = summary.get("lastReason")
    if reason == "log_missing":
        return f"{label} is waiting because its watched log is missing; keep playing until {subject} are written, then check {payload_key}.stdout.lastEvent."
    if reason == "translation_not_ready":
        return f"{label} is waiting for the main project translation to finish before processing {subject}; run the returned resumeCommand or rerun live-session without --translate-dry-run."
    if reason == "translation_locked":
        return f"{label} is waiting on an active translation lock; run session-info or project-info if it does not clear."
    if reason == "log_unchanged":
        return f"{label} is idle because the watched log has not changed; keep the subtitle window running while new lines arrive."
    status = summary.get("lastStatus")
    if status == "processed":
        return f"{label} processed its watched log; check {payload_key}.statusSummary for added and pending counts."
    return f"Review {payload_key}.stdoutPath if {subject} do not translate automatically."


def _default_session_log_path(game_path: Path, workspace: Path) -> Path:
    raw_name = game_path.stem if game_path.suffix else game_path.name
    safe_name = "".join(char if char.isalnum() or char in ("-", "_", ".") else "_" for char in raw_name).strip("._-")
    if not safe_name:
        safe_name = "session"
    return workspace / "captures" / f"{safe_name}-live-capture.txt"


def _play_session_record_duration(args: Any) -> float:
    if getattr(args, "record_until_interrupted", False):
        return 0.0
    return max(0.0, float(getattr(args, "record_duration", 60.0)))


def _translate_log_payload(args: Any) -> tuple[dict[str, Any], int]:
    project_root = Path(args.project_root)
    capture = ClipboardLogImporter().import_log(
        Path(args.log_file),
        source_name=args.source_name,
        encoding=args.encoding,
    )
    append_payload = _append_log_payload(project_root, capture)
    scoped_entry_ids = append_payload["logEntryIds"] if args.only_new_log_entries else None
    translate_payload, translate_return_code = _translate_all_payload(
        project_root=project_root,
        batch_size=args.size,
        model=args.model,
        max_batches=args.max_batches,
        timeout=args.timeout,
        dry_run=args.dry_run,
        allowed_entry_ids=scoped_entry_ids,
    )
    replay_payload = None
    if args.replay_event_log is not None:
        records = _translation_records_from_state(project_root / "translation-state.json")
        runtime = RuntimeSubtitleService(MatchIndex(records))
        replay_payload = _replay_log_payload(runtime, capture.entries, 0, args.replay_include_source)
        _write_runtime_events_jsonl(Path(args.replay_event_log), replay_payload["events"])
        replay_payload["eventLogPath"] = str(Path(args.replay_event_log))
    summary = _translate_log_summary(append_payload, translate_payload, replay_payload)
    payload = {
        "projectRoot": str(project_root),
        "sessionSummary": summary,
        "append": append_payload,
        "translateAll": translate_payload,
        "translateScope": translate_payload.get("translateScope"),
        "replay": replay_payload,
        "projectInfo": _project_info_payload(project_root),
    }
    payload["nextActions"] = _translate_log_next_actions(summary, translate_payload, replay_payload)
    return (
        payload,
        translate_return_code,
    )


def _watch_translate_log(args: Any) -> int:
    state_path = Path(args.project_root) / "translation-state.json"
    log_path = Path(args.log_file)
    last_signature = None
    idle_count = 0
    cycle = 0
    last_return_code = 0
    safe_interval = max(0.1, args.watch_interval)
    try:
        while True:
            cycle += 1
            signature = _path_signature(log_path)
            if signature is None:
                idle_count += 1
                payload = _translate_log_watch_event(
                    status="idle",
                    cycle=cycle,
                    log_path=log_path,
                    signature=signature,
                    reason="log_missing",
                    idle_count=idle_count,
                    result=None,
                )
            elif not state_path.is_file():
                idle_count += 1
                payload = _translate_log_watch_event(
                    status="idle",
                    cycle=cycle,
                    log_path=log_path,
                    signature=signature,
                    reason="translation_state_missing",
                    idle_count=idle_count,
                    result=None,
                )
            elif args.watch_require_ready and not _project_translation_ready(Path(args.project_root)):
                idle_count += 1
                payload = _translate_log_watch_event(
                    status="idle",
                    cycle=cycle,
                    log_path=log_path,
                    signature=signature,
                    reason="translation_not_ready",
                    idle_count=idle_count,
                    result=None,
                )
            elif signature == last_signature:
                idle_count += 1
                payload = _translate_log_watch_event(
                    status="idle",
                    cycle=cycle,
                    log_path=log_path,
                    signature=signature,
                    reason="log_unchanged",
                    idle_count=idle_count,
                    result=None,
                )
            else:
                previous_idle_count = idle_count
                idle_count = 0
                try:
                    result, last_return_code = _translate_log_payload(args)
                    if result.get("translateAll", {}).get("status") == "translation_locked":
                        idle_count = previous_idle_count + 1
                        payload = _translate_log_watch_event(
                            status="idle",
                            cycle=cycle,
                            log_path=log_path,
                            signature=signature,
                            reason="translation_locked",
                            idle_count=idle_count,
                            result=result,
                        )
                        print(json.dumps(payload, ensure_ascii=False), flush=True)
                        if args.watch_max_cycles > 0 and cycle >= args.watch_max_cycles:
                            return 0
                        if args.watch_idle_cycles > 0 and idle_count >= args.watch_idle_cycles:
                            return 0
                        time.sleep(safe_interval)
                        continue
                    last_signature = signature
                    status = "processed" if last_return_code == 0 else "failed"
                    payload = _translate_log_watch_event(
                        status=status,
                        cycle=cycle,
                        log_path=log_path,
                        signature=signature,
                        reason=None,
                        idle_count=idle_count,
                        result=result,
                    )
                except (OSError, UnicodeError) as error:
                    last_return_code = 1
                    payload = _translate_log_watch_event(
                        status="failed",
                        cycle=cycle,
                        log_path=log_path,
                        signature=signature,
                        reason=str(error),
                        idle_count=idle_count,
                        result=None,
                    )
            print(json.dumps(payload, ensure_ascii=False), flush=True)
            if payload["status"] == "failed":
                return last_return_code or 1
            if args.watch_max_cycles > 0 and cycle >= args.watch_max_cycles:
                return last_return_code
            if args.watch_idle_cycles > 0 and idle_count >= args.watch_idle_cycles:
                return last_return_code
            time.sleep(safe_interval)
    except KeyboardInterrupt:
        print(
            json.dumps(
                {
                    "status": "interrupted",
                    "cycle": cycle,
                    "logPath": str(log_path),
                    "nextActions": ["Restart translate-log --watch to resume miss-log background translation."],
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
        return last_return_code


def _translate_log_watch_event(
    status: str,
    cycle: int,
    log_path: Path,
    signature: tuple[int, int] | None,
    reason: str | None,
    idle_count: int,
    result: dict[str, Any] | None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": status,
        "cycle": cycle,
        "logPath": str(log_path),
        "logSignature": _signature_payload(signature),
        "idleCount": idle_count,
    }
    if reason is not None:
        payload["reason"] = reason
    if result is not None:
        payload["result"] = result
    if status == "idle":
        payload["nextActions"] = ["Keep the subtitle window running with --miss-log, or append new lines to this log."]
    elif status == "processed":
        payload["nextActions"] = ["Keep playing; runtime display will reload translation-state.json automatically."]
    else:
        payload["nextActions"] = ["Review the failure, then rerun translate-log --watch."]
    return payload


def _project_translation_ready(project_root: Path) -> bool:
    try:
        progress = _project_progress_payload(project_root)
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
        return False
    return progress.get("pending", 0) == 0 and progress.get("failed", 0) == 0


def _signature_payload(signature: tuple[int, int] | None) -> dict[str, Any] | None:
    if signature is None:
        return None
    return {
        "modifiedNs": signature[0],
        "size": signature[1],
    }


def _play_session_summary(
    capture_payload: dict[str, Any],
    translate_payload: dict[str, Any],
    replay_payload: dict[str, Any] | None,
    subtitle_payload: dict[str, Any] | None,
    append: bool,
    existing_state_before_capture: bool,
    batch_size: int,
    model: str,
    timeout: int,
    max_batches: int,
    translate_retry_failed: bool,
    session_log_path: str | None = None,
    session_log_source_name: str = "textractor",
) -> dict[str, Any]:
    progress = translate_payload.get("finalProgress", {})
    subtitle_record_count = subtitle_payload.get("recordCount", 0) if subtitle_payload else 0
    status = _session_status(translate_payload, replay_payload, subtitle_payload)
    project_root = translate_payload.get("projectRoot")
    miss_log_path = subtitle_payload.get("missLogPath") if subtitle_payload else None
    return {
        "status": status,
        "projectRoot": project_root,
        "captureMode": "append" if append else "replace",
        "existingStateBeforeCapture": existing_state_before_capture,
        "replacedExistingState": existing_state_before_capture and not append,
        "capturedEntryCount": capture_payload.get("captureStats", {}).get("importedEntryCount", 0),
        "sourceEntryCount": progress.get("total", 0),
        "addedEntryCount": capture_payload.get("addedEntryCount", 0),
        "pendingCount": progress.get("pending", 0),
        "failedCount": progress.get("failed", 0),
        "translatedCount": progress.get("translated", 0),
        "batchSize": batch_size,
        "model": model,
        "translateTimeout": timeout,
        "translateMaxBatches": max_batches,
        "translateRetryFailed": translate_retry_failed,
        "subtitleRecordCount": subtitle_record_count,
        "replayMatched": replay_payload.get("matched") if replay_payload else None,
        "replayUnmatched": replay_payload.get("unmatched") if replay_payload else None,
        "missLogPath": miss_log_path,
        "subtitleCommand": subtitle_payload.get("command") if subtitle_payload else None,
        "translateMissLogCommand": _translate_miss_log_command(
            project_root,
            miss_log_path,
            batch_size=batch_size,
            model=model,
            timeout=timeout,
            max_batches=max_batches,
        ),
        "watchMissLogCommand": _watch_miss_log_command(
            project_root,
            miss_log_path,
            batch_size=batch_size,
            model=model,
            timeout=timeout,
            max_batches=max_batches,
        ),
        "translateSessionLogCommand": _translate_log_command(
            project_root,
            session_log_path,
            source_name=session_log_source_name,
            batch_size=batch_size,
            model=model,
            timeout=timeout,
            max_batches=max_batches,
        ),
        "watchSessionLogCommand": _watch_log_command(
            project_root,
            session_log_path,
            source_name=session_log_source_name,
            batch_size=batch_size,
            model=model,
            timeout=timeout,
            max_batches=max_batches,
        ),
    }


def _translate_log_summary(
    append_payload: dict[str, Any],
    translate_payload: dict[str, Any],
    replay_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    progress = translate_payload.get("finalProgress", {})
    scope_progress = translate_payload.get("finalScopeProgress")
    status_payload = translate_payload
    if scope_progress is not None:
        status_payload = {**translate_payload, "finalProgress": scope_progress}
    status = _session_status(status_payload, replay_payload, None)
    if append_payload.get("addedEntryCount", 0) == 0 and scope_progress is not None and scope_progress.get("total") == 0:
        status = "no_new_log_entries"
    return {
        "status": status,
        "projectRoot": translate_payload.get("projectRoot"),
        "translateScope": translate_payload.get("translateScope", "all_pending"),
        "addedEntryCount": append_payload.get("addedEntryCount", 0),
        "pendingCount": progress.get("pending", 0),
        "failedCount": progress.get("failed", 0),
        "translatedCount": progress.get("translated", 0),
        "scopedPendingCount": scope_progress.get("pending") if scope_progress else None,
        "scopedFailedCount": scope_progress.get("failed") if scope_progress else None,
        "scopedTranslatedCount": scope_progress.get("translated") if scope_progress else None,
        "replayMatched": replay_payload.get("matched") if replay_payload else None,
        "replayUnmatched": replay_payload.get("unmatched") if replay_payload else None,
    }


def _session_status(
    translate_payload: dict[str, Any],
    replay_payload: dict[str, Any] | None,
    subtitle_payload: dict[str, Any] | None,
) -> str:
    translate_status = translate_payload.get("status")
    progress = translate_payload.get("finalProgress", {})
    if progress.get("total") == 0:
        return "no_source_text"
    if translate_status == "dry_run":
        return "translation_planned"
    if translate_status != "ready" or progress.get("pending", 0) > 0 or progress.get("failed", 0) > 0:
        return "translation_needs_attention"
    if replay_payload is not None and replay_payload.get("unmatched", 0) > 0:
        return "replay_has_misses"
    if subtitle_payload is None:
        return "translation_ready"
    if subtitle_payload.get("detached") and not subtitle_payload.get("detachedRunning", True):
        return "subtitle_exited"
    if subtitle_payload.get("started"):
        return "subtitle_started"
    if subtitle_payload.get("dryRun"):
        return "subtitle_ready"
    return "translation_ready"


def _play_session_next_actions(
    summary: dict[str, Any],
    translate_payload: dict[str, Any],
    replay_payload: dict[str, Any] | None,
    subtitle_payload: dict[str, Any] | None,
) -> list[str]:
    status = summary.get("status")
    if summary.get("sourceEntryCount") == 0:
        actions = ["Record or provide a Textractor/clipboard log with Japanese lines, then rerun play-session."]
        return _with_capture_mode_warning(summary, actions)
    if status == "translation_planned":
        actions = ["Rerun play-session without --translate-dry-run to translate every pending entry."]
        return _with_capture_mode_warning(summary, actions)
    if status == "translation_needs_attention":
        actions = list(translate_payload.get("nextActions") or ["Review translateAll and rerun play-session after fixing translation issues."])
        return _with_capture_mode_warning(summary, actions)
    if status == "replay_has_misses":
        return _with_capture_mode_warning(summary, _miss_feedback_next_actions(summary, replay_payload))
    if subtitle_payload is None:
        actions = ["Start subtitle-window for this project, or rerun play-session without --no-subtitle."]
        return _with_capture_mode_warning(summary, actions)
    if status == "subtitle_exited":
        actions = [
            "Detached subtitle-window exited immediately; review subtitleWindow.detachedStderrPath and detachedStdoutPath, then rerun play-session or subtitle-window."
        ]
        return _with_capture_mode_warning(summary, actions)
    if subtitle_payload.get("dryRun"):
        actions = ["Rerun play-session without --subtitle-dry-run to open the live subtitle window."]
        return _with_capture_mode_warning(summary, actions)
    if subtitle_payload.get("started"):
        if subtitle_payload.get("detached"):
            actions = ["Keep playing with the detached subtitle window open."]
        else:
            actions = ["Keep playing with the subtitle window open."]
        if summary.get("missLogPath"):
            actions.append("After play, run translate-log with the miss log to translate newly unmatched lines.")
        return _with_capture_mode_warning(summary, actions)
    return _with_capture_mode_warning(summary, ["Run project-info to inspect the project before starting the subtitle window."])


def _translate_log_next_actions(
    summary: dict[str, Any],
    translate_payload: dict[str, Any],
    replay_payload: dict[str, Any] | None,
) -> list[str]:
    if (
        summary.get("addedEntryCount", 0) == 0
        and summary.get("scopedPendingCount") == 0
        and summary.get("scopedTranslatedCount") == 0
        and summary.get("scopedFailedCount") == 0
    ):
        return ["No new log lines were appended; continue playing until the miss log captures new unmatched text."]
    status = summary.get("status")
    if status == "translation_planned":
        return ["Rerun translate-log without --dry-run to translate the log-referenced entries."]
    if status == "translation_needs_attention":
        return list(translate_payload.get("nextActions") or ["Review translateAll and rerun translate-log after fixing translation issues."])
    if status == "replay_has_misses":
        return _miss_feedback_next_actions(summary, replay_payload)
    return ["Return to play-session or subtitle-window; the appended log entries are translated."]


def _miss_feedback_next_actions(summary: dict[str, Any], replay_payload: dict[str, Any] | None) -> list[str]:
    unmatched = replay_payload.get("unmatched", 0) if replay_payload else 0
    miss_log_path = summary.get("missLogPath")
    if miss_log_path:
        return [
            f"Review the {unmatched} unmatched replay line(s), then keep playing so subtitle-window writes misses to {miss_log_path}.",
            "Run translate-log with that miss log, then replay or return to play-session.",
        ]
    return [
        f"Review the {unmatched} unmatched replay line(s). Enable --subtitle-miss-log or run replay-log with --include-source to capture them for translation."
    ]


def _with_capture_mode_warning(summary: dict[str, Any], actions: list[str]) -> list[str]:
    if not summary.get("replacedExistingState"):
        return actions
    return [
        "This play-session replaced an existing project state; use --append on repeated sessions to preserve prior captured lines."
    ] + actions


def _launch_game_payload(game_path: Path) -> dict[str, Any]:
    if not game_path.is_file():
        return {
            "status": "skipped",
            "reason": "path is not a file",
            "path": str(game_path),
        }
    process = subprocess.Popen(
        [str(game_path)],
        cwd=str(game_path.parent),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return {
        "status": "started",
        "path": str(game_path),
        "pid": process.pid,
    }


def _subtitle_config_from_args(args: Any, base_config: SubtitleWindowConfig | None = None) -> SubtitleWindowConfig:
    if base_config is None:
        exit_after = getattr(args, "exit_after", getattr(args, "subtitle_exit_after", 0.0))
        return SubtitleWindowConfig(
            interval_ms=int(max(0.05, args.interval) * 1000),
            font_size=args.font_size,
            opacity=args.opacity,
            width=args.width,
            height=args.height,
            x=args.x,
            y=args.y,
            font_family=args.font_family,
            background=args.background,
            foreground=args.foreground,
            clear_after_ms=int(max(0.0, args.clear_after) * 1000),
            exit_after_ms=int(max(0.0, exit_after) * 1000),
            topmost=not args.not_topmost,
        )
    base = base_config or SubtitleWindowConfig()
    exit_after_attr = "exit_after" if hasattr(args, "exit_after") else "subtitle_exit_after"
    base_exit_after = base.exit_after_ms / 1000
    return SubtitleWindowConfig(
        interval_ms=int(max(0.05, _subtitle_arg_value(args, "interval", base.interval_ms / 1000, "--interval")) * 1000),
        font_size=_subtitle_arg_value(args, "font_size", base.font_size, "--font-size"),
        opacity=_subtitle_arg_value(args, "opacity", base.opacity, "--opacity"),
        width=_subtitle_arg_value(args, "width", base.width, "--width"),
        height=_subtitle_arg_value(args, "height", base.height, "--height"),
        x=_subtitle_arg_value(args, "x", base.x, "--x"),
        y=_subtitle_arg_value(args, "y", base.y, "--y"),
        font_family=_subtitle_arg_value(args, "font_family", base.font_family, "--font-family"),
        background=_subtitle_arg_value(args, "background", base.background, "--background"),
        foreground=_subtitle_arg_value(args, "foreground", base.foreground, "--foreground"),
        clear_after_ms=int(max(0.0, _subtitle_arg_value(args, "clear_after", base.clear_after_ms / 1000, "--clear-after")) * 1000),
        exit_after_ms=int(max(0.0, _subtitle_arg_value(args, exit_after_attr, base_exit_after, "--exit-after", "--subtitle-exit-after")) * 1000),
        topmost=False if getattr(args, "not_topmost", False) else base.topmost,
    )


def _subtitle_arg_value(args: Any, attr: str, base_value: Any, *flags: str) -> Any:
    if _any_cli_flag_present(*flags):
        return getattr(args, attr)
    return base_value


def _any_cli_flag_present(*flags: str) -> bool:
    for token in sys.argv[1:]:
        for flag in flags:
            if token == flag or token.startswith(f"{flag}="):
                return True
    return False


def _load_subtitle_window_config(path: Path) -> SubtitleWindowConfig:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise TypeError("subtitle config must be a JSON object")
    return SubtitleWindowConfig.from_json_dict(payload)


def _write_subtitle_window_config(path: Path, config: SubtitleWindowConfig) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config.to_json_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _subtitle_event_log_path(project_root: Path, event_log_arg: str | None, no_log: bool) -> str | None:
    if no_log:
        return None
    path = Path(event_log_arg) if event_log_arg else project_root / "logs" / "runtime-events.jsonl"
    return str(path)


def _runtime_for_state(
    state_path: Path,
    reload_enabled: bool,
    initial_records: list[TranslationRecord] | None = None,
) -> RuntimeSubtitleService:
    if reload_enabled:
        return ReloadableRuntimeSubtitleService(
            load_records=lambda: _translation_records_from_state(state_path),
            current_signature=lambda: _translation_state_signature(state_path),
        )
    records = initial_records if initial_records is not None else _translation_records_from_state(state_path)
    return RuntimeSubtitleService(MatchIndex(records))


def _subtitle_preview_source(
    explicit_source: str | None,
    use_first_match: bool,
    entries: list[ScriptEntry],
    runtime: RuntimeSubtitleService,
) -> str | None:
    if explicit_source:
        return explicit_source
    if not use_first_match:
        return None
    for entry in entries:
        if runtime.display_for(entry.source).text:
            return entry.source
    return None


def _subtitle_preview_payload(
    runtime: RuntimeSubtitleService,
    source_text: str | None,
    include_source: bool,
) -> dict[str, Any] | None:
    if not source_text:
        return None
    return _clipboard_runtime_event_payload(
        source_text,
        runtime.display_for(source_text),
        include_source=include_source,
        miss_logged=False,
    )


def _translation_state_signature(state_path: Path) -> tuple[int, int] | None:
    return _path_signature(state_path)


def _path_signature(path: Path) -> tuple[int, int] | None:
    try:
        stat = path.stat()
    except OSError:
        return None
    return (stat.st_mtime_ns, stat.st_size)


def _subtitle_window_command(
    project_root: Path,
    config: SubtitleWindowConfig,
    no_log: bool,
    event_log_arg: str | None,
    include_source: bool,
    miss_log_arg: str | None,
    reload_enabled: bool = True,
    preview_source: str | None = None,
    source_log: str | None = None,
    source_log_encoding: str = "utf-8",
    source_log_name: str | None = None,
    source_log_from_start: bool = False,
) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "gal_translator",
        "subtitle-window",
        str(project_root),
        "--interval",
        _format_seconds(config.interval_ms / 1000),
        "--font-size",
        str(config.font_size),
        "--opacity",
        _format_seconds(config.opacity),
        "--width",
        str(config.width),
        "--height",
        str(config.height),
        "--font-family",
        config.font_family,
        "--background",
        config.background,
        "--foreground",
        config.foreground,
        "--clear-after",
        _format_seconds(config.clear_after_ms / 1000),
    ]
    if config.x is not None:
        command.extend(["--x", str(config.x)])
    if config.y is not None:
        command.extend(["--y", str(config.y)])
    if config.exit_after_ms > 0:
        command.extend(["--exit-after", _format_seconds(config.exit_after_ms / 1000)])
    if not config.topmost:
        command.append("--not-topmost")
    if not reload_enabled:
        command.append("--no-reload")
    if no_log:
        command.append("--no-log")
    elif event_log_arg:
        command.extend(["--event-log", str(Path(event_log_arg))])
    if include_source:
        command.append("--include-source")
    if miss_log_arg:
        command.extend(["--miss-log", str(Path(miss_log_arg))])
    if preview_source:
        command.extend(["--preview-source", preview_source])
    if source_log:
        command.extend(["--source-log", str(Path(source_log))])
        command.extend(["--source-log-encoding", source_log_encoding])
        if source_log_name:
            command.extend(["--source-log-name", source_log_name])
        if source_log_from_start:
            command.append("--source-log-from-start")
    return command


def _translate_log_command(
    project_root: str | None,
    log_path: str | None,
    source_name: str,
    batch_size: int,
    model: str,
    timeout: int,
    max_batches: int,
) -> list[str] | None:
    if not project_root or not log_path:
        return None
    return [
        sys.executable,
        "-m",
        "gal_translator",
        "translate-log",
        project_root,
        log_path,
        "--source-name",
        source_name,
        "--size",
        str(max(1, batch_size)),
        "--model",
        model,
        "--timeout",
        str(max(0, timeout)),
        "--max-batches",
        str(max(0, max_batches)),
        "--only-new-log-entries",
    ]


def _translate_miss_log_command(
    project_root: str | None,
    miss_log_path: str | None,
    batch_size: int,
    model: str,
    timeout: int,
    max_batches: int,
) -> list[str] | None:
    return _translate_log_command(
        project_root,
        miss_log_path,
        source_name="misses",
        batch_size=batch_size,
        model=model,
        timeout=timeout,
        max_batches=max_batches,
    )


def _watch_log_command(
    project_root: str | None,
    log_path: str | None,
    source_name: str,
    batch_size: int,
    model: str,
    timeout: int,
    max_batches: int,
) -> list[str] | None:
    command = _translate_log_command(
        project_root,
        log_path,
        source_name=source_name,
        batch_size=batch_size,
        model=model,
        timeout=timeout,
        max_batches=max_batches,
    )
    if command is None:
        return None
    return command + ["--watch", "--watch-require-ready"]


def _watch_miss_log_command(
    project_root: str | None,
    miss_log_path: str | None,
    batch_size: int,
    model: str,
    timeout: int,
    max_batches: int,
) -> list[str] | None:
    command = _translate_miss_log_command(
        project_root,
        miss_log_path,
        batch_size=batch_size,
        model=model,
        timeout=timeout,
        max_batches=max_batches,
    )
    if command is None:
        return None
    return command + ["--watch", "--watch-require-ready"]


def _format_seconds(value: float) -> str:
    return f"{value:.3f}".rstrip("0").rstrip(".")


def _start_detached_subtitle_window(command: list[str], cwd: Path, log_dir: Path | None = None) -> dict[str, Any]:
    if log_dir is None:
        log_dir = cwd
    log_dir.mkdir(parents=True, exist_ok=True)
    stamp = _run_id()
    stdout_path = log_dir / f"{stamp}-stdout.txt"
    stderr_path = log_dir / f"{stamp}-stderr.txt"
    creationflags = 0
    if sys.platform == "win32":
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    stdout_handle = stdout_path.open("w", encoding="utf-8")
    stderr_handle = stderr_path.open("w", encoding="utf-8")
    process = None
    try:
        process = subprocess.Popen(
            command,
            cwd=str(cwd),
            stdin=subprocess.DEVNULL,
            stdout=stdout_handle,
            stderr=stderr_handle,
            close_fds=True,
            creationflags=creationflags,
        )
    finally:
        stdout_handle.close()
        stderr_handle.close()
    if process is None:
        raise RuntimeError("failed to start detached subtitle window")
    _DETACHED_PROCESSES.append(process)
    time.sleep(0.1)
    return_code = process.poll()
    return {
        "detachedPid": process.pid,
        "detachedCommand": list(command),
        "detachedStdoutPath": str(stdout_path),
        "detachedStderrPath": str(stderr_path),
        "detachedRunning": return_code is None,
        "detachedReturnCode": return_code,
    }


def _run_subtitle_window_for_project(
    project_root: Path,
    config: SubtitleWindowConfig,
    no_log: bool,
    event_log_arg: str | None,
    include_source: bool,
    miss_log_arg: str | None = None,
    reload_enabled: bool = True,
    preview_source: str | None = None,
    source_log: str | None = None,
    source_log_encoding: str = "utf-8",
    source_log_name: str | None = None,
    source_log_from_start: bool = False,
) -> None:
    runtime = _runtime_for_state(project_root / "translation-state.json", reload_enabled=reload_enabled)
    event_logger = None
    if not no_log:
        event_log_path = Path(event_log_arg) if event_log_arg else project_root / "logs" / "runtime-events.jsonl"

        def event_logger(raw_text: str, state: Any) -> None:
            miss_logged = False
            if miss_log_arg and not state.text:
                miss_logged = _append_miss_log_line(Path(miss_log_arg), raw_text)
            _append_jsonl_line(
                event_log_path,
                json.dumps(
                    _subtitle_runtime_event_payload(raw_text, state, include_source, miss_logged=miss_logged),
                    ensure_ascii=False,
                ),
            )

    elif miss_log_arg:
        def event_logger(raw_text: str, state: Any) -> None:
            if not state.text:
                _append_miss_log_line(Path(miss_log_arg), raw_text)

    runtime_input = _subtitle_runtime_input(
        source_log=source_log,
        source_log_encoding=source_log_encoding,
        source_log_name=source_log_name,
        source_log_from_start=source_log_from_start,
    )
    window = SubtitleWindow(
        runtime=runtime,
        clipboard_provider=None if runtime_input is not None else WindowsClipboardProvider(),
        config=config,
        event_logger=event_logger,
        initial_source_text=preview_source,
        runtime_input=runtime_input,
    )
    window.run()


def _execute_prepared_codex(prepared: dict[str, Any], timeout: int) -> dict[str, Any]:
    prompt = Path(prepared["promptPath"]).read_text(encoding="utf-8")
    stdout_path = Path(prepared["stdoutPath"])
    stderr_path = Path(prepared["stderrPath"])
    command = list(prepared["command"])
    resolved_command = shutil.which(command[0])
    if resolved_command is not None:
        command[0] = resolved_command
    early_result_ready = False
    timed_out = False
    try:
        with stdout_path.open("w", encoding="utf-8", errors="replace") as stdout_handle, stderr_path.open(
            "w",
            encoding="utf-8",
            errors="replace",
        ) as stderr_handle:
            process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=stdout_handle,
                stderr=stderr_handle,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            assert process.stdin is not None
            process.stdin.write(prompt)
            process.stdin.close()
            deadline = time.monotonic() + timeout if timeout > 0 else None
            while True:
                completed_return_code = process.poll()
                if completed_return_code is not None:
                    return_code = completed_return_code
                    status = "succeeded" if completed_return_code == 0 else "failed"
                    break
                if _prepared_result_complete(prepared):
                    early_result_ready = True
                    _terminate_process_tree(process)
                    return_code = 0
                    status = "result_ready_process_stopped"
                    break
                if deadline is not None and time.monotonic() >= deadline:
                    timed_out = True
                    _terminate_process_tree(process)
                    return_code = 124
                    status = "timeout"
                    break
                time.sleep(1.0)
    except FileNotFoundError as error:
        stdout_path.write_text("", encoding="utf-8")
        stderr_path.write_text(str(error), encoding="utf-8")
        return_code = 127
        status = "command_not_found"
    payload = {
        **prepared,
        "status": status,
        "returnCode": return_code,
        "stdout": _session_log_file_payload(stdout_path, parse_jsonl=False),
        "stderr": _session_log_file_payload(stderr_path, parse_jsonl=False),
        "result": _json_file_summary_payload(Path(prepared["outputPath"])),
    }
    if early_result_ready:
        payload["earlyResultReady"] = True
    if timed_out:
        payload["timedOut"] = True
    return payload


def _terminate_process_tree(process: subprocess.Popen[Any]) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def _prepared_result_complete(prepared: dict[str, Any]) -> bool:
    result_path = Path(prepared["outputPath"])
    if not result_path.is_file():
        return False
    try:
        payload = json.loads(result_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return False
    items = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        return False
    expected_ids = set(prepared.get("entryIds", []))
    if not expected_ids:
        return True
    result_ids = {item.get("id") for item in items if isinstance(item, dict)}
    return expected_ids.issubset(result_ids)


def _apply_prepared_codex_result(
    project_root: Path,
    prepared: dict[str, Any],
) -> tuple[Any | None, str | None]:
    try:
        result = json.loads(Path(prepared["outputPath"]).read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as error:
        return None, str(error)
    apply_summary = CodexBatchTranslator(project_root / "translation-state.json").apply_result(
        result,
        expected_ids=prepared["entryIds"],
    )
    return apply_summary, None


def _project_progress_payload(project_root: Path) -> dict[str, Any]:
    return _summary_payload(TranslationProgressTracker(project_root / "translation-state.json").summary())


def _ordered_unique_strings(values: list[str] | tuple[str, ...] | None) -> tuple[str, ...] | None:
    if values is None:
        return None
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if not isinstance(value, str) or value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return tuple(ordered)


def _scoped_progress_payload(project_root: Path, entry_ids: tuple[str, ...]) -> dict[str, Any]:
    state_path = project_root / "translation-state.json"
    if not state_path.is_file():
        return {
            "total": 0,
            "pending": 0,
            "translated": 0,
            "failed": 0,
            "status": "empty",
            "percent": 0.0,
        }
    wanted = set(entry_ids)
    state = json.loads(state_path.read_text(encoding="utf-8"))
    items = [item for item in state.get("items", []) if item.get("entryId") in wanted]
    total = len(items)
    translated = sum(1 for item in items if item.get("status") == "translated")
    failed = sum(1 for item in items if item.get("status") == "failed")
    pending = total - translated - failed
    percent = 0.0 if total == 0 else round((translated / total) * 100, 2)
    return {
        "total": total,
        "pending": pending,
        "translated": translated,
        "failed": failed,
        "status": _progress_status(total, pending, translated, failed),
        "percent": percent,
    }


def _progress_status(total: int, pending: int, translated: int, failed: int) -> str:
    if total == 0:
        return "empty"
    if translated == total:
        return "ready"
    if translated > 0 or failed > 0:
        return "partial"
    if pending == total:
        return "pending"
    return "partial"


def _planned_batch_count(pending_count: int, batch_size: int, max_batches: int) -> int:
    if pending_count <= 0:
        return 0
    planned = (pending_count + batch_size - 1) // batch_size
    return min(planned, max_batches) if max_batches > 0 else planned


def _translate_all_next_actions(status: str, final_progress: dict[str, Any]) -> list[str]:
    if status == "dry_run":
        return ["Rerun translate-all without --dry-run to execute Codex batches, then use replay-log or subtitle-window."]
    if status == "ready":
        return ["Run replay-log to check match coverage, then start watch-clipboard or subtitle-window."]
    if status == "max_batches_reached":
        return ["Rerun translate-all to continue remaining pending entries."]
    if status == "completed_with_failed_items" or final_progress["failed"] > 0:
        return ["Run retry-failed after reviewing failed items, then rerun translate-all."]
    if status in {"command_not_found", "timeout", "failed", "result_invalid"}:
        return ["Review the latest batch logs under logs/codex-batches, fix the issue, then rerun translate-all."]
    return ["Run project-info to inspect the project state."]


def _prepare_codex_batch(
    project_root: Path,
    batch_size: int,
    model: str,
    out_dir_arg: str | None,
    allowed_entry_ids: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    translator = CodexBatchTranslator(project_root / "translation-state.json")
    batch = translator.next_batch(batch_size, allowed_entry_ids=allowed_entry_ids)
    out_dir = Path(out_dir_arg) if out_dir_arg is not None else project_root / "logs" / "codex-batches" / _run_id()
    out_dir.mkdir(parents=True, exist_ok=True)
    prompt_path = out_dir / "prompt.txt"
    schema_path = out_dir / "schema.json"
    output_path = out_dir / "result.json"
    command_path = out_dir / "command.json"
    batch_path = out_dir / "batch.json"
    stdout_path = out_dir / "stdout.txt"
    stderr_path = out_dir / "stderr.txt"
    prompt_path.write_text(translator.build_prompt(batch), encoding="utf-8")
    invocation = CodexCliInvocation(model=model)
    invocation.write_output_schema(schema_path)
    command = invocation.command(prompt_path, schema_path, output_path)
    command_path.write_text(json.dumps({"command": command}, ensure_ascii=False, indent=2), encoding="utf-8")
    batch_path.write_text(
        json.dumps(
            {
                "createdAt": datetime.now(timezone.utc).isoformat(),
                "entryIds": [item.entry_id for item in batch],
                "items": [
                    {
                        "id": item.entry_id,
                        "speaker": item.speaker,
                        "source": item.source,
                    }
                    for item in batch
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return {
        "batchSize": len(batch),
        "entryIds": [item.entry_id for item in batch],
        "promptPath": str(prompt_path),
        "schemaPath": str(schema_path),
        "outputPath": str(output_path),
        "commandPath": str(command_path),
        "batchPath": str(batch_path),
        "stdoutPath": str(stdout_path),
        "stderrPath": str(stderr_path),
        "command": command,
    }


def _run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def _expected_ids_for_result(result_path: Path) -> tuple[list[str], dict[str, Any] | None]:
    batch_path = result_path.parent / "batch.json"
    if not batch_path.is_file():
        return [], None
    try:
        payload = json.loads(batch_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as error:
        return [], _error_payload(
            "batch_json_invalid",
            str(error),
            ["Review or remove the batch.json next to the result file, then rerun apply-result."],
        )
    entry_ids = payload.get("entryIds", [])
    if not isinstance(entry_ids, list):
        return [], _error_payload(
            "batch_json_invalid",
            f"entryIds must be a list in {batch_path}",
            ["Regenerate this batch with prepare-codex, then rerun apply-result."],
        )
    return [entry_id for entry_id in entry_ids if isinstance(entry_id, str)], None


def _capture_project_payload(
    project: TranslationProject,
    capture: Any,
    append: bool,
) -> dict[str, Any]:
    entries_path = project.project_root / "story-entries.json"
    if append and (project.project_root / "translation-state.json").is_file():
        new_entries = _new_entries_by_id(entries_path, capture.entries)
        all_entries = _read_story_entries(entries_path) + new_entries
        _write_story_entries(entries_path, all_entries)
        tracker = TranslationProgressTracker(project.project_root / "translation-state.json")
        added_count = tracker.append_entries(new_entries)
    else:
        all_entries = _unique_entries_by_source(capture.entries)
        _write_story_entries(entries_path, all_entries)
        tracker = TranslationProgressTracker.initialize(project, all_entries)
        added_count = len(all_entries)
    return {
        **_import_payload(project, [], all_entries, tracker),
        "captureSource": capture.source_name,
        "captureStats": _capture_stats_payload(capture),
        "addedEntryCount": added_count,
    }


def _append_log_payload(project_root: Path, capture: Any) -> dict[str, Any]:
    entries_path = project_root / "story-entries.json"
    new_entries = _new_entries_by_id(entries_path, capture.entries)
    all_entries = _read_story_entries(entries_path) + new_entries
    _write_story_entries(entries_path, all_entries)
    tracker = TranslationProgressTracker(project_root / "translation-state.json")
    existing_state_ids = tracker.entry_ids()
    added_entry_ids = [entry.id for entry in new_entries if entry.id not in existing_state_ids]
    added_count = tracker.append_entries(new_entries)
    state_ids = tracker.entry_ids()
    log_entry_ids = [
        entry_id
        for entry_id in _entry_ids_for_sources(all_entries, [entry.source for entry in capture.entries])
        if entry_id in state_ids
    ]
    added_entry_id_set = set(added_entry_ids)
    existing_log_entry_ids = [entry_id for entry_id in log_entry_ids if entry_id not in added_entry_id_set]
    return {
        "projectRoot": str(project_root),
        "captureSource": capture.source_name,
        "captureStats": _capture_stats_payload(capture),
        "storyEntryCount": len(all_entries),
        "addedEntryCount": added_count,
        "addedEntryIds": added_entry_ids,
        "existingLogEntryIds": existing_log_entry_ids,
        "logEntryIds": log_entry_ids,
        "storyEntriesPath": str(entries_path),
        "translationStatePath": str(project_root / "translation-state.json"),
        "progress": _summary_payload(tracker.summary()),
    }


def _capture_stats_payload(capture: Any) -> dict[str, Any]:
    return {
        "rawLineCount": capture.raw_line_count,
        "candidateLineCount": capture.candidate_line_count,
        "duplicateLineCount": capture.duplicate_line_count,
        "nonJapaneseLineCount": capture.non_japanese_line_count,
        "controlLineCount": getattr(capture, "control_line_count", 0),
        "importedEntryCount": capture.imported_entry_count,
        "uniqueImportedEntryCount": capture.unique_imported_entry_count,
        "repeatedSourceCount": capture.repeated_source_count,
    }


def _inspect_log_payload(capture: Any, limit: int, include_source: bool) -> dict[str, Any]:
    preview_entries = capture.entries[: max(0, limit)]
    preview: list[dict[str, Any]] = []
    for entry in preview_entries:
        item = {
            "id": entry.id,
            "line": entry.line,
            "kind": entry.kind,
        }
        if include_source:
            item["source"] = entry.source
        preview.append(item)
    return {
        "captureSource": capture.source_name,
        "status": _inspect_log_status(capture),
        "captureStats": _capture_stats_payload(capture),
        "previewCount": len(preview),
        "preview": preview,
        "nextActions": _inspect_log_next_actions(capture),
    }


def _inspect_log_status(capture: Any) -> str:
    if capture.raw_line_count == 0:
        return "empty_log"
    if capture.candidate_line_count == 0:
        return "no_candidate_text"
    if capture.imported_entry_count == 0:
        return "no_japanese_text"
    if capture.repeated_source_count > 0:
        return "ready_with_repeated_sources"
    return "ready_to_import"


def _inspect_log_next_actions(capture: Any) -> list[str]:
    status = _inspect_log_status(capture)
    if status == "empty_log":
        return ["Confirm Textractor or clipboard recording is writing to this file, then rerun inspect-log."]
    if status == "no_candidate_text":
        return ["Check that the captured log contains non-empty text lines, then rerun inspect-log."]
    if status == "no_japanese_text":
        return [
            "Check Textractor hook selection and log encoding; rerun inspect-log with --encoding if the file is not UTF-8.",
            "If the hook only captures menus or engine noise, switch hooks before running capture-log.",
        ]
    if status == "ready_with_repeated_sources":
        return [
            "Run capture-log for a new project or append-log for an existing project.",
            "Use uniqueImportedEntryCount as the expected new translation-item count; repeated source lines are kept as one translation entry.",
        ]
    return ["Run capture-log for a new project or append-log for an existing project, then run translate-all."]


def _project_payload(
    project: TranslationProject,
    matched_profiles: list[ExtractorProfile],
) -> dict[str, Any]:
    return {
        "projectId": project.project_id,
        "projectRoot": str(project.project_root),
        "gameRoot": str(project.game_root),
        "sourceLang": project.source_lang,
        "targetLang": project.target_lang,
        "status": project.status,
        "matchedProfiles": [_profile_payload(profile) for profile in matched_profiles],
    }


def _profile_payload(profile: ExtractorProfile) -> dict[str, Any]:
    return {
        "profileId": profile.profile_id,
        "label": profile.label,
        "sourceLang": profile.source_lang,
        "targetLang": profile.target_lang,
        "scriptGlobs": list(profile.script_globs),
        "encoding": profile.encoding,
    }


def _parse_story_entries(imported_scripts: list[ImportedScript]) -> list[ScriptEntry]:
    parser = ScriptParser()
    parsed_entries: list[ScriptEntry] = []
    for script in imported_scripts:
        parsed_entries.extend(parser.parse(script.project_path, script.relative_path))
    return StoryTextFilter().keep_story_entries(parsed_entries)


def _has_artemis_ast_scripts(root: Path) -> bool:
    return any(path.is_file() for path in root.glob("**/*.ast"))


def _import_artemis_ast_payload(project: TranslationProject) -> dict[str, Any]:
    imported = ArtemisAstImporter().import_scripts(project)
    entries = _parse_artemis_ast_entries(imported)
    entries_path = project.project_root / "story-entries.json"
    _write_story_entries(entries_path, entries)
    tracker = TranslationProgressTracker.initialize(project, entries)
    return {
        **_import_payload(project, imported, entries, tracker),
        "importType": "artemis_ast",
    }


def _parse_artemis_ast_entries(imported_scripts: list[ImportedScript]) -> list[ScriptEntry]:
    parser = ArtemisAstParser()
    parsed_entries: list[ScriptEntry] = []
    for script in imported_scripts:
        parsed_entries.extend(parser.parse(script.project_path, script.relative_path))
    return StoryTextFilter().keep_story_entries(parsed_entries)


def _import_payload(
    project: TranslationProject,
    imported_scripts: list[ImportedScript],
    story_entries: list[ScriptEntry],
    tracker: TranslationProgressTracker | None = None,
) -> dict[str, Any]:
    summary = tracker.summary() if tracker is not None else None
    return {
        "projectId": project.project_id,
        "projectRoot": str(project.project_root),
        "sourceLang": project.source_lang,
        "targetLang": project.target_lang,
        "importedScriptCount": len(imported_scripts),
        "storyEntryCount": len(story_entries),
        "storyEntriesPath": str(project.project_root / "story-entries.json"),
        "translationStatePath": str(project.project_root / "translation-state.json"),
        "progress": _summary_payload(summary) if summary is not None else None,
    }


def _entry_payload(entry: ScriptEntry) -> dict[str, Any]:
    return {
        "id": entry.id,
        "source": entry.source,
        "speaker": entry.speaker,
        "file": entry.file,
        "line": entry.line,
        "kind": entry.kind,
    }


def _write_story_entries(path: Path, entries: list[ScriptEntry]) -> None:
    path.write_text(
        json.dumps([_entry_payload(entry) for entry in entries], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _read_story_entries(path: Path) -> list[ScriptEntry]:
    if not path.is_file():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [
        ScriptEntry(
            id=item["id"],
            source=item["source"],
            speaker=item.get("speaker"),
            file=item["file"],
            line=item["line"],
            kind=item["kind"],
        )
        for item in payload
    ]


def _new_entries_by_id(entries_path: Path, entries: list[ScriptEntry]) -> list[ScriptEntry]:
    existing_entries = _read_story_entries(entries_path)
    existing_by_id = {entry.id: entry for entry in existing_entries}
    existing_sources = {entry.source for entry in existing_entries}
    reserved_ids = set(existing_by_id)
    new_entries: list[ScriptEntry] = []
    for entry in entries:
        existing = existing_by_id.get(entry.id)
        if existing is None and entry.id not in reserved_ids:
            if entry.source in existing_sources:
                continue
            new_entries.append(entry)
            reserved_ids.add(entry.id)
            existing_sources.add(entry.source)
            continue
        if existing is not None and existing.source == entry.source:
            continue
        new_entry = _with_collision_safe_id(entry, reserved_ids)
        if new_entry.source in existing_sources:
            continue
        new_entries.append(new_entry)
        reserved_ids.add(new_entry.id)
        existing_sources.add(new_entry.source)
    return new_entries


def _entry_ids_for_sources(entries: list[ScriptEntry], sources: list[str]) -> list[str]:
    first_id_by_source: dict[str, str] = {}
    for entry in entries:
        first_id_by_source.setdefault(entry.source, entry.id)
    seen_ids: set[str] = set()
    entry_ids: list[str] = []
    for source in sources:
        entry_id = first_id_by_source.get(source)
        if entry_id is None or entry_id in seen_ids:
            continue
        seen_ids.add(entry_id)
        entry_ids.append(entry_id)
    return entry_ids


def _unique_entries_by_source(entries: list[ScriptEntry]) -> list[ScriptEntry]:
    seen_sources: set[str] = set()
    unique_entries: list[ScriptEntry] = []
    for entry in entries:
        if entry.source in seen_sources:
            continue
        seen_sources.add(entry.source)
        unique_entries.append(entry)
    return unique_entries


def _with_collision_safe_id(entry: ScriptEntry, reserved_ids: set[str]) -> ScriptEntry:
    digest = hashlib.sha1(entry.source.encode("utf-8")).hexdigest()[:8]
    candidate = f"{entry.id}#{digest}"
    counter = 2
    while candidate in reserved_ids:
        candidate = f"{entry.id}#{digest}-{counter}"
        counter += 1
    return ScriptEntry(
        id=candidate,
        source=entry.source,
        speaker=entry.speaker,
        file=entry.file,
        line=entry.line,
        kind=entry.kind,
    )


def _summary_payload(summary: TranslationSummary) -> dict[str, Any]:
    return {
        "total": summary.total,
        "pending": summary.pending,
        "translated": summary.translated,
        "failed": summary.failed,
        "status": summary.status,
        "percent": summary.percent,
    }


def _subtitle_window_config_payload(config: SubtitleWindowConfig) -> dict[str, Any]:
    return {
        "geometry": config.geometry(),
        "intervalMs": config.poll_interval_ms(),
        "fontSize": config.font_size,
        "opacity": config.normalized_opacity(),
        "width": config.width,
        "height": config.height,
        "x": config.x,
        "y": config.y,
        "fontFamily": config.font_family,
        "background": config.background,
        "foreground": config.foreground,
        "clearAfterMs": config.clear_after_ms,
        "exitAfterMs": config.exit_after_ms,
        "topmost": config.topmost,
    }


def _subtitle_input_payload(
    source_log: str | None,
    source_log_encoding: str = "utf-8",
    source_log_name: str | None = None,
    source_log_from_start: bool = False,
) -> dict[str, Any]:
    if not source_log:
        return {"mode": "clipboard"}
    path = Path(source_log)
    return {
        "mode": "source_log",
        "sourceLogPath": str(path),
        "sourceLogExists": path.is_file(),
        "sourceLogEncoding": source_log_encoding,
        "sourceLogName": source_log_name,
        "sourceLogFromStart": source_log_from_start,
    }


def _subtitle_runtime_input(
    source_log: str | None,
    source_log_encoding: str = "utf-8",
    source_log_name: str | None = None,
    source_log_from_start: bool = False,
) -> TextLogRuntimeInput | None:
    if not source_log:
        return None
    return TextLogRuntimeInput(
        source_log,
        source_name=source_log_name,
        encoding=source_log_encoding,
        from_start=source_log_from_start,
    )


def _subtitle_runtime_event_payload(raw_text: str, state: Any, include_source: bool, miss_logged: bool = False) -> dict[str, Any]:
    payload = {
        "text": state.text,
        "matchType": state.match_type,
        "visible": state.visible,
        "missLogged": miss_logged,
    }
    if include_source:
        payload["rawText"] = raw_text
    return payload


def _clipboard_runtime_event_payload(raw_text: str, display: Any, include_source: bool, miss_logged: bool = False) -> dict[str, Any]:
    payload = {
        "text": display.text,
        "matchType": display.match_type,
        "showSource": display.show_source,
        "missLogged": miss_logged,
    }
    if include_source:
        payload["rawText"] = raw_text
    return payload


def _replay_log_payload(
    runtime: RuntimeSubtitleService,
    entries: list[ScriptEntry],
    limit: int,
    include_source: bool,
) -> dict[str, Any]:
    selected_entries = entries[: max(0, limit)] if limit > 0 else entries
    events: list[dict[str, Any]] = []
    matched = 0
    for entry in selected_entries:
        display = runtime.display_for(entry.source)
        if display.text:
            matched += 1
        event = {
            "entryId": entry.id,
            "line": entry.line,
            "text": display.text,
            "matchType": display.match_type,
            "showSource": display.show_source,
        }
        if include_source:
            event["source"] = entry.source
        events.append(event)
    total = len(selected_entries)
    return {
        "total": total,
        "matched": matched,
        "unmatched": total - matched,
        "matchPercent": round((matched / total) * 100, 2) if total else 0.0,
        "events": events,
    }


def _write_runtime_events_jsonl(path: Path, events: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for event in events:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")


def _append_jsonl_line(path: Path, line: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def _append_miss_log_line(path: Path, raw_text: str) -> bool:
    line = _plain_log_line(raw_text)
    if not line:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        existing = set(path.read_text(encoding="utf-8").splitlines())
        if line in existing:
            return False
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
    return True


def _plain_log_line(text: str) -> str:
    return " ".join(text.replace("\r\n", "\n").replace("\r", "\n").split())


def _translation_records_from_state(state_path: Path) -> list[TranslationRecord]:
    state = json.loads(state_path.read_text(encoding="utf-8"))
    return [
        TranslationRecord(
            entry_id=item["entryId"],
            source=item["source"],
            translation=item["translation"],
            status=item["status"],
        )
        for item in state["items"]
    ]


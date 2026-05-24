from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
from typing import Any, Callable


def default_workspace() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "GalTranslator"
    return Path.home() / "AppData" / "Local" / "GalTranslator"


@dataclass(frozen=True)
class DesktopShellConfig:
    workspace: Path = field(default_factory=default_workspace)
    source_name: str = "textractor"
    batch_size: int = 40
    source_log_batch_size: int = 1
    source_log_max_batches: int = 1
    source_log_watch_interval: float = 1.0
    model: str = "gpt-5.5"
    translate_timeout: int = 600
    subtitle_width: int = 1200
    subtitle_height: int = 120
    subtitle_x: int | None = 120
    subtitle_y: int | None = 760
    subtitle_font_size: int = 30
    subtitle_opacity: float = 0.82
    subtitle_clear_after: float = 4.0
    subtitle_topmost: bool = True
    subtitle_background: str = "#050505"
    subtitle_foreground: str = "#f5f5f5"
    subtitle_font_family: str = "Microsoft YaHei UI"
    start_luna_hook_bridge: bool = False
    luna_hook_game_process: str = "selectoblige"
    luna_hook_codes: tuple[str, ...] = (
        "ENHVXN-24@195720:selectoblige.exe",
        "HVXN-4C@1971E0:selectoblige.exe",
    )
    luna_hook_duration: float = 3600.0
    luna_hook_max_events: int = 0
    luna_hook_idle_timeout: float = 0.0

    def to_payload(self) -> dict[str, Any]:
        return {
            "workspace": str(self.workspace),
            "sourceName": self.source_name,
            "batchSize": self.batch_size,
            "sourceLogBatchSize": self.source_log_batch_size,
            "sourceLogMaxBatches": self.source_log_max_batches,
            "sourceLogWatchInterval": self.source_log_watch_interval,
            "model": self.model,
            "translateTimeout": self.translate_timeout,
            "subtitle": {
                "width": self.subtitle_width,
                "height": self.subtitle_height,
                "x": self.subtitle_x,
                "y": self.subtitle_y,
                "fontSize": self.subtitle_font_size,
                "opacity": self.subtitle_opacity,
                "clearAfter": self.subtitle_clear_after,
                "topmost": self.subtitle_topmost,
                "background": self.subtitle_background,
                "foreground": self.subtitle_foreground,
                "fontFamily": self.subtitle_font_family,
            },
            "lunaHookBridge": {
                "enabled": self.start_luna_hook_bridge,
                "gameProcess": self.luna_hook_game_process,
                "hookCodes": list(self.luna_hook_codes),
                "duration": self.luna_hook_duration,
                "maxEvents": self.luna_hook_max_events,
                "idleTimeout": self.luna_hook_idle_timeout,
            },
        }


def desktop_shell_payload(config: DesktopShellConfig) -> dict[str, Any]:
    return {
        "status": "ready",
        "app": "Gal Translator Desktop Shell",
        "config": config.to_payload(),
        "entries": [
            {
                "id": "translation_preparation",
                "label": "Translation Preparation",
                "actions": [
                    "scan",
                    "inspect-log",
                    "import",
                    "capture-log",
                    "append-log",
                    "translate-all",
                    "retry-failed",
                    "project-info",
                ],
            },
            {
                "id": "play_output",
                "label": "Play Output",
                "actions": [
                    "subtitle-window",
                    "source-log-session",
                    "live-session",
                    "project-info",
                ],
            },
        ],
        "mvpScope": {
            "externalSubtitleWindow": True,
            "localRuntimeMatching": True,
            "missLogFeedback": True,
            "inGameTextRewrite": False,
            "drmBypass": False,
            "archiveCracking": False,
            "defaultRealtimeLlmTranslation": False,
            "defaultOcrTranslation": False,
        },
        "commandTemplates": {
            "scan": build_scan_command("<game-path>"),
            "inspectLog": build_inspect_log_command("<source-log>", config),
            "captureLog": build_capture_log_command("<game-path>", "<source-log>", config),
            "appendLog": build_append_log_command("<project-root>", "<source-log>", config),
            "translateAll": build_translate_all_command("<project-root>", config),
            "retryFailed": build_retry_failed_command("<project-root>"),
            "subtitleWindow": build_subtitle_window_command(
                "<project-root>",
                config,
                source_log="<source-log>",
                miss_log="<miss-log>",
            ),
            "liveSession": build_live_session_command("<game-path>", "<source-log>", "<miss-log>", config),
            "sourceLogSession": build_source_log_session_command(
                "<project-root>",
                "<source-log>",
                config,
                miss_log="<miss-log>",
                start_luna_hook_bridge=config.start_luna_hook_bridge,
            ),
        },
    }


def build_scan_command(game_path: str | Path) -> list[str]:
    return [sys.executable, "-m", "gal_translator", "scan", str(game_path)]


def build_inspect_log_command(log_path: str | Path, config: DesktopShellConfig) -> list[str]:
    return [
        sys.executable,
        "-m",
        "gal_translator",
        "inspect-log",
        str(log_path),
        "--source-name",
        config.source_name,
    ]


def build_direct_import_command(game_path: str | Path, config: DesktopShellConfig) -> list[str]:
    return [
        sys.executable,
        "-m",
        "gal_translator",
        "import",
        str(game_path),
        "--workspace",
        str(config.workspace),
    ]


def build_capture_log_command(
    game_path: str | Path,
    log_path: str | Path,
    config: DesktopShellConfig,
    append: bool = False,
) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "gal_translator",
        "capture-log",
        str(game_path),
        str(log_path),
        "--workspace",
        str(config.workspace),
        "--source-name",
        config.source_name,
    ]
    if append:
        command.append("--append")
    return command


def build_append_log_command(
    project_root: str | Path,
    log_path: str | Path,
    config: DesktopShellConfig,
) -> list[str]:
    return [
        sys.executable,
        "-m",
        "gal_translator",
        "append-log",
        str(project_root),
        str(log_path),
        "--source-name",
        config.source_name,
    ]


def build_translate_all_command(
    project_root: str | Path,
    config: DesktopShellConfig,
    retry_failed: bool = False,
    dry_run: bool = False,
) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "gal_translator",
        "translate-all",
        str(project_root),
        "--size",
        str(config.batch_size),
        "--model",
        config.model,
        "--timeout",
        str(config.translate_timeout),
    ]
    if retry_failed:
        command.append("--retry-failed")
    if dry_run:
        command.append("--dry-run")
    return command


def build_retry_failed_command(project_root: str | Path) -> list[str]:
    return [sys.executable, "-m", "gal_translator", "retry-failed", str(project_root)]


def build_project_info_command(project_root: str | Path) -> list[str]:
    return [sys.executable, "-m", "gal_translator", "project-info", str(project_root)]


def build_subtitle_window_command(
    project_root: str | Path,
    config: DesktopShellConfig,
    source_log: str | Path | None = None,
    miss_log: str | Path | None = None,
    dry_run: bool = False,
    source_log_from_start: bool = False,
) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "gal_translator",
        "subtitle-window",
        str(project_root),
        "--width",
        str(config.subtitle_width),
        "--height",
        str(config.subtitle_height),
        "--font-size",
        str(config.subtitle_font_size),
        "--opacity",
        str(config.subtitle_opacity),
        "--clear-after",
        str(config.subtitle_clear_after),
        "--background",
        config.subtitle_background,
        "--foreground",
        config.subtitle_foreground,
        "--font-family",
        config.subtitle_font_family,
    ]
    if config.subtitle_x is not None:
        command.extend(["--x", str(config.subtitle_x)])
    if config.subtitle_y is not None:
        command.extend(["--y", str(config.subtitle_y)])
    if not config.subtitle_topmost:
        command.append("--not-topmost")
    if source_log:
        command.extend(["--source-log", str(source_log), "--source-log-name", config.source_name])
    if source_log_from_start:
        command.append("--source-log-from-start")
    if miss_log:
        command.extend(["--miss-log", str(miss_log)])
    if dry_run:
        command.append("--dry-run")
    return command


def build_live_session_command(
    game_path: str | Path,
    log_path: str | Path,
    miss_log: str | Path,
    config: DesktopShellConfig,
    dry_run: bool = False,
) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "gal_translator",
        "live-session",
        str(game_path),
        str(log_path),
        "--workspace",
        str(config.workspace),
        "--source-name",
        config.source_name,
        "--batch-size",
        str(config.batch_size),
        "--model",
        config.model,
        "--translate-timeout",
        str(config.translate_timeout),
        "--subtitle-source-log",
        "--subtitle-detach",
        "--subtitle-miss-log",
        str(miss_log),
        "--width",
        str(config.subtitle_width),
        "--height",
        str(config.subtitle_height),
        "--font-size",
        str(config.subtitle_font_size),
        "--opacity",
        str(config.subtitle_opacity),
        "--clear-after",
        str(config.subtitle_clear_after),
    ]
    if config.subtitle_x is not None:
        command.extend(["--x", str(config.subtitle_x)])
    if config.subtitle_y is not None:
        command.extend(["--y", str(config.subtitle_y)])
    if not config.subtitle_topmost:
        command.append("--not-topmost")
    if dry_run:
        command.append("--translate-dry-run")
        command.append("--subtitle-dry-run")
    return command


def build_source_log_session_command(
    project_root: str | Path,
    source_log: str | Path,
    config: DesktopShellConfig,
    miss_log: str | Path | None = None,
    dry_run: bool = False,
    start_luna_hook_bridge: bool | None = None,
) -> list[str]:
    script_path = Path(__file__).resolve().parent.parent / "scripts" / "source-log-session.ps1"
    command = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script_path),
        "-ProjectRoot",
        str(project_root),
        "-SourceLog",
        str(source_log),
        "-SourceName",
        config.source_name,
        "-BatchSize",
        str(config.source_log_batch_size),
        "-MaxBatches",
        str(config.source_log_max_batches),
        "-WatchInterval",
        str(config.source_log_watch_interval),
        "-Model",
        config.model,
        "-Timeout",
        str(config.translate_timeout),
    ]
    if miss_log:
        command.extend(["-MissLog", str(miss_log)])
    bridge_enabled = config.start_luna_hook_bridge if start_luna_hook_bridge is None else start_luna_hook_bridge
    if bridge_enabled:
        command.append("-StartLunaHookBridge")
        if config.luna_hook_game_process:
            command.extend(["-LunaHookGameProcess", config.luna_hook_game_process])
        command.extend(["-LunaHookDuration", str(config.luna_hook_duration)])
        command.extend(["-LunaHookMaxEvents", str(config.luna_hook_max_events)])
        command.extend(["-LunaHookIdleTimeout", str(config.luna_hook_idle_timeout)])
        for hook_code in config.luna_hook_codes:
            command.extend(["-LunaHookCode", hook_code])
    if dry_run:
        command.append("-DryRun")
    return command


def failed_items_payload(project_root: str | Path, limit: int = 20) -> dict[str, Any]:
    state_path = Path(project_root) / "translation-state.json"
    if not state_path.is_file():
        return {"failedCount": 0, "shownCount": 0, "items": [], "statePath": str(state_path)}
    state = json.loads(state_path.read_text(encoding="utf-8-sig"))
    raw_items = state.get("items") if isinstance(state, dict) else []
    if not isinstance(raw_items, list):
        raw_items = []
    failed = [item for item in raw_items if isinstance(item, dict) and item.get("status") == "failed"]
    shown = failed[: max(0, limit)]
    return {
        "failedCount": len(failed),
        "shownCount": len(shown),
        "statePath": str(state_path),
        "items": [
            {
                "entryId": str(item.get("entryId", "")),
                "error": str(item.get("error", "")),
                "retryCount": int(item.get("retryCount", 0) or 0),
                "maxRetryReached": bool(item.get("maxRetryReached", False)),
            }
            for item in shown
        ],
    }


def launch_desktop_shell(config: DesktopShellConfig) -> None:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    root = tk.Tk()
    root.title("Gal Translator")
    root.geometry("1080x720")
    shell = DesktopShell(root, config, filedialog=filedialog, messagebox=messagebox, ttk=ttk, tk=tk)
    shell.pack(fill="both", expand=True)
    root.mainloop()


class DesktopShell:
    def __init__(self, master: Any, config: DesktopShellConfig, **tk_modules: Any) -> None:
        self.tk = tk_modules["tk"]
        self.ttk = tk_modules["ttk"]
        self.filedialog = tk_modules["filedialog"]
        self.messagebox = tk_modules["messagebox"]
        self.frame = self.ttk.Frame(master, padding=12)
        self.config = config
        self.runner: Callable[[list[str]], tuple[int, str, str]] = self._run_subprocess
        self._build_vars()
        self._build_ui()

    def pack(self, **kwargs: Any) -> None:
        self.frame.pack(**kwargs)

    def _build_vars(self) -> None:
        self.game_path = self.tk.StringVar()
        self.log_path = self.tk.StringVar()
        self.project_root = self.tk.StringVar()
        self.miss_log = self.tk.StringVar()
        self.workspace = self.tk.StringVar(value=str(self.config.workspace))
        self.source_name = self.tk.StringVar(value=self.config.source_name)
        self.model = self.tk.StringVar(value=self.config.model)
        self.batch_size = self.tk.IntVar(value=self.config.batch_size)
        self.timeout = self.tk.IntVar(value=self.config.translate_timeout)
        self.progress_text = self.tk.StringVar(value="No project loaded")
        self.status_text = self.tk.StringVar(value="Ready")

    def _current_config(self) -> DesktopShellConfig:
        return DesktopShellConfig(
            workspace=Path(self.workspace.get()),
            source_name=self.source_name.get().strip() or self.config.source_name,
            batch_size=max(1, int(self.batch_size.get())),
            source_log_batch_size=self.config.source_log_batch_size,
            source_log_max_batches=self.config.source_log_max_batches,
            source_log_watch_interval=self.config.source_log_watch_interval,
            model=self.model.get().strip() or self.config.model,
            translate_timeout=max(0, int(self.timeout.get())),
            subtitle_width=self.config.subtitle_width,
            subtitle_height=self.config.subtitle_height,
            subtitle_x=self.config.subtitle_x,
            subtitle_y=self.config.subtitle_y,
            subtitle_font_size=self.config.subtitle_font_size,
            subtitle_opacity=self.config.subtitle_opacity,
            subtitle_clear_after=self.config.subtitle_clear_after,
            subtitle_topmost=self.config.subtitle_topmost,
            subtitle_background=self.config.subtitle_background,
            subtitle_foreground=self.config.subtitle_foreground,
            subtitle_font_family=self.config.subtitle_font_family,
            start_luna_hook_bridge=self.config.start_luna_hook_bridge,
            luna_hook_game_process=self.config.luna_hook_game_process,
            luna_hook_codes=self.config.luna_hook_codes,
            luna_hook_duration=self.config.luna_hook_duration,
            luna_hook_max_events=self.config.luna_hook_max_events,
            luna_hook_idle_timeout=self.config.luna_hook_idle_timeout,
        )

    def _build_ui(self) -> None:
        header = self.ttk.Frame(self.frame)
        header.pack(fill="x")
        self.ttk.Label(header, text="Gal Translator", font=("Segoe UI", 16, "bold")).pack(side="left")
        self.ttk.Label(header, textvariable=self.status_text).pack(side="right")

        paths = self.ttk.Frame(self.frame)
        paths.pack(fill="x", pady=(12, 8))
        self._game_path_row(paths, 0)
        self._path_row(paths, "Source log", self.log_path, self._browse_log, 1)
        self._path_row(paths, "Project", self.project_root, self._browse_project, 2)
        self._path_row(paths, "Miss log", self.miss_log, self._browse_miss_log, 3)
        self._path_row(paths, "Workspace", self.workspace, self._browse_workspace, 4)

        options = self.ttk.Frame(self.frame)
        options.pack(fill="x", pady=(0, 8))
        self._option_entry(options, "Source", self.source_name, 0)
        self._option_entry(options, "Model", self.model, 1)
        self._option_entry(options, "Batch", self.batch_size, 2, width=8)
        self._option_entry(options, "Timeout", self.timeout, 3, width=8)

        notebook = self.ttk.Notebook(self.frame)
        notebook.pack(fill="both", expand=True)

        prep = self.ttk.Frame(notebook, padding=8)
        play = self.ttk.Frame(notebook, padding=8)
        notebook.add(prep, text="Translation Preparation")
        notebook.add(play, text="Play Output")
        self._build_translation_tab(prep)
        self._build_play_tab(play)

        footer = self.ttk.Frame(self.frame)
        footer.pack(fill="x", pady=(8, 0))
        self.ttk.Label(footer, textvariable=self.progress_text).pack(side="left")

    def _path_row(self, parent: Any, label: str, variable: Any, browse: Callable[[], None], row: int) -> None:
        self.ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=2)
        self.ttk.Entry(parent, textvariable=variable).grid(row=row, column=1, sticky="ew", pady=2)
        self.ttk.Button(parent, text="Browse", command=browse).grid(row=row, column=2, padx=(8, 0), pady=2)
        parent.columnconfigure(1, weight=1)

    def _game_path_row(self, parent: Any, row: int) -> None:
        self.ttk.Label(parent, text="Game").grid(row=row, column=0, sticky="w", padx=(0, 8), pady=2)
        self.ttk.Entry(parent, textvariable=self.game_path).grid(row=row, column=1, sticky="ew", pady=2)
        self.ttk.Button(parent, text="Exe", command=self._browse_game).grid(row=row, column=2, padx=(8, 0), pady=2)
        self.ttk.Button(parent, text="Dir", command=self._browse_game_dir).grid(row=row, column=3, padx=(8, 0), pady=2)
        parent.columnconfigure(1, weight=1)

    def _option_entry(self, parent: Any, label: str, variable: Any, column: int, width: int = 18) -> None:
        self.ttk.Label(parent, text=label).grid(row=0, column=column * 2, sticky="w", padx=(0, 4))
        self.ttk.Entry(parent, textvariable=variable, width=width).grid(row=0, column=(column * 2) + 1, padx=(0, 12))

    def _build_translation_tab(self, parent: Any) -> None:
        buttons = self.ttk.Frame(parent)
        buttons.pack(fill="x")
        for label, command in [
            ("Scan", self.scan_game),
            ("Inspect Log", self.inspect_log),
            ("Import Direct Scripts", self.import_direct_scripts),
            ("Import Log", self.import_log),
            ("Project Info", self.project_info),
            ("Translate All", self.translate_all),
            ("Retry Failed", self.retry_failed),
        ]:
            self.ttk.Button(buttons, text=label, command=lambda callback=command: self._safe(callback)).pack(
                side="left",
                padx=(0, 8),
                pady=(0, 8),
            )
        self.output = self.tk.Text(parent, wrap="word", height=18)
        self.output.pack(fill="both", expand=True)

    def _build_play_tab(self, parent: Any) -> None:
        buttons = self.ttk.Frame(parent)
        buttons.pack(fill="x")
        for label, command in [
            ("Open Subtitle", self.open_subtitle),
            ("Open Subtitle Dry Run", self.subtitle_dry_run),
            ("Start Source-Log Session", self.start_source_log_session),
            ("Start Live Session", self.start_live_session),
        ]:
            self.ttk.Button(buttons, text=label, command=lambda callback=command: self._safe(callback)).pack(
                side="left",
                padx=(0, 8),
                pady=(0, 8),
            )
        self.play_output = self.tk.Text(parent, wrap="word", height=18)
        self.play_output.pack(fill="both", expand=True)

    def _browse_game(self) -> None:
        path = self.filedialog.askopenfilename(title="Select game exe")
        if path:
            self.game_path.set(path)

    def _browse_game_dir(self) -> None:
        path = self.filedialog.askdirectory(title="Select game directory")
        if path:
            self.game_path.set(path)

    def _browse_log(self) -> None:
        path = self.filedialog.askopenfilename(title="Select source log")
        if path:
            self.log_path.set(path)
            if not self.miss_log.get():
                self.miss_log.set(str(Path(path).with_name("gal-translator-misses.txt")))

    def _browse_project(self) -> None:
        path = self.filedialog.askdirectory(title="Select project directory")
        if path:
            self.project_root.set(path)

    def _browse_workspace(self) -> None:
        path = self.filedialog.askdirectory(title="Select workspace")
        if path:
            self.workspace.set(path)

    def _browse_miss_log(self) -> None:
        path = self.filedialog.asksaveasfilename(title="Select miss log", defaultextension=".txt")
        if path:
            self.miss_log.set(path)

    def scan_game(self) -> None:
        self._run_async(build_scan_command(self._required_path(self.game_path, "Game path")), self.output)

    def inspect_log(self) -> None:
        self._run_async(build_inspect_log_command(self._required_path(self.log_path, "Source log"), self._current_config()), self.output)

    def import_direct_scripts(self) -> None:
        self._run_async(
            build_direct_import_command(self._required_path(self.game_path, "Game path"), self._current_config()),
            self.output,
            update_project=True,
        )

    def import_log(self) -> None:
        config = self._current_config()
        project_root = self.project_root.get().strip()
        if project_root:
            command = build_append_log_command(project_root, self._required_path(self.log_path, "Source log"), config)
        else:
            command = build_capture_log_command(
                self._required_path(self.game_path, "Game path"),
                self._required_path(self.log_path, "Source log"),
                config,
            )
        self._run_async(command, self.output, update_project=True)

    def project_info(self) -> None:
        self._run_async(build_project_info_command(self._required_path(self.project_root, "Project")), self.output)

    def translate_all(self) -> None:
        self._run_async(build_translate_all_command(self._required_path(self.project_root, "Project"), self._current_config()), self.output)

    def retry_failed(self) -> None:
        self._run_async(build_retry_failed_command(self._required_path(self.project_root, "Project")), self.output)

    def open_subtitle(self) -> None:
        self._run_async(
            build_subtitle_window_command(
                self._required_path(self.project_root, "Project"),
                self._current_config(),
                source_log=self.log_path.get().strip() or None,
                miss_log=self.miss_log.get().strip() or None,
            ),
            self.play_output,
        )

    def subtitle_dry_run(self) -> None:
        self._run_async(
            build_subtitle_window_command(
                self._required_path(self.project_root, "Project"),
                self._current_config(),
                source_log=self.log_path.get().strip() or None,
                miss_log=self.miss_log.get().strip() or None,
                dry_run=True,
            ),
            self.play_output,
        )

    def start_live_session(self) -> None:
        self._run_async(
            build_live_session_command(
                self._required_path(self.game_path, "Game path"),
                self._required_path(self.log_path, "Source log"),
                self._required_path(self.miss_log, "Miss log"),
                self._current_config(),
            ),
            self.play_output,
            update_project=True,
        )

    def start_source_log_session(self) -> None:
        config = self._current_config()
        self._run_async(
            build_source_log_session_command(
                self._required_path(self.project_root, "Project"),
                self._required_path(self.log_path, "Source log"),
                config,
                miss_log=self.miss_log.get().strip() or None,
                start_luna_hook_bridge=config.start_luna_hook_bridge,
            ),
            self.play_output,
        )

    def _safe(self, callback: Callable[[], None]) -> None:
        try:
            callback()
        except ValueError as error:
            self.status_text.set("Ready")
            self.messagebox.showerror("Missing input", str(error))

    def _required_path(self, variable: Any, label: str) -> str:
        value = variable.get().strip()
        if not value:
            raise ValueError(f"{label} is required")
        return value

    def _run_async(self, command: list[str], output: Any, update_project: bool = False) -> None:
        self.status_text.set("Running")
        self._append_output(output, f"$ {_format_command(command)}\n")

        def worker() -> None:
            return_code, stdout, stderr = self.runner(command)
            self.frame.after(0, lambda: self._finish_command(output, command, return_code, stdout, stderr, update_project))

        threading.Thread(target=worker, daemon=True).start()

    def _finish_command(
        self,
        output: Any,
        command: list[str],
        return_code: int,
        stdout: str,
        stderr: str,
        update_project: bool,
    ) -> None:
        self.status_text.set("Ready" if return_code == 0 else f"Exit {return_code}")
        if stdout:
            self._append_output(output, stdout.rstrip() + "\n")
        if stderr:
            self._append_output(output, stderr.rstrip() + "\n")
        payload = _json_payload(stdout)
        if payload is not None:
            if update_project and isinstance(payload.get("projectRoot"), str):
                self.project_root.set(payload["projectRoot"])
            self._set_progress_from_payload(payload)
            self._append_failed_items(output, payload)
            self._show_retry_limit_hint(payload)

    def _set_progress_from_payload(self, payload: dict[str, Any]) -> None:
        progress = (
            payload.get("progress")
            or payload.get("finalProgress")
            or payload.get("initialProgress")
        )
        project_info = payload.get("projectInfo")
        if progress is None and isinstance(project_info, dict):
            progress = project_info.get("progress")
        if not isinstance(progress, dict):
            return
        self.progress_text.set(
            "Progress: {translated}/{total} translated, {pending} pending, {failed} failed ({percent}%)".format(
                translated=progress.get("translated", 0),
                total=progress.get("total", 0),
                pending=progress.get("pending", 0),
                failed=progress.get("failed", 0),
                percent=progress.get("percent", 0),
            )
        )

    def _append_failed_items(self, output: Any, payload: dict[str, Any]) -> None:
        progress = (
            payload.get("progress")
            or payload.get("finalProgress")
            or payload.get("initialProgress")
        )
        project_info = payload.get("projectInfo")
        if progress is None and isinstance(project_info, dict):
            progress = project_info.get("progress")
        if not isinstance(progress, dict) or int(progress.get("failed", 0) or 0) <= 0:
            return
        project_root = payload.get("projectRoot") or self.project_root.get().strip()
        if not project_root:
            return
        try:
            failed = failed_items_payload(project_root)
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            return
        if failed["failedCount"] <= 0:
            return
        lines = [f"Failed entries ({failed['shownCount']}/{failed['failedCount']} shown):"]
        for item in failed["items"]:
            limit_note = " retry limit reached" if item["maxRetryReached"] else ""
            lines.append(
                "  - {entry_id}: retry {retry_count}/3{limit_note}; {error}".format(
                    entry_id=item["entryId"],
                    retry_count=item["retryCount"],
                    limit_note=limit_note,
                    error=item["error"] or "no error detail",
                )
            )
        self._append_output(output, "\n".join(lines) + "\n")

    def _show_retry_limit_hint(self, payload: dict[str, Any]) -> None:
        retry = payload.get("failedRetry") if isinstance(payload.get("failedRetry"), dict) else payload
        if not isinstance(retry, dict) or retry.get("skippedCount", 0) <= 0:
            return
        actions = retry.get("nextActions") or [
            "Some failed entries reached the retry limit; review them and abandon isolated lines when appropriate."
        ]
        self.messagebox.showwarning("Retry limit", "\n".join(str(action) for action in actions))

    def _append_output(self, widget: Any, text: str) -> None:
        widget.insert("end", text)
        widget.see("end")

    def _run_subprocess(self, command: list[str]) -> tuple[int, str, str]:
        result = subprocess.run(command, check=False, capture_output=True)
        return (
            result.returncode,
            result.stdout.decode("utf-8", errors="replace"),
            result.stderr.decode("utf-8", errors="replace"),
        )


def _json_payload(text: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _format_command(command: list[str]) -> str:
    return " ".join(_quote_command_part(part) for part in command)


def _quote_command_part(part: str) -> str:
    if not part or any(char.isspace() for char in part):
        return json.dumps(part)
    return part

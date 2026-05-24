from __future__ import annotations

from dataclasses import dataclass, field
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Any


class ThreadParam(ctypes.Structure):
    _fields_ = [
        ("processId", ctypes.c_uint),
        ("addr", ctypes.c_uint64),
        ("ctx", ctypes.c_uint64),
        ("ctx2", ctypes.c_uint64),
    ]

    def to_payload(self) -> dict[str, int]:
        return {
            "processId": int(self.processId),
            "addr": int(self.addr),
            "ctx": int(self.ctx),
            "ctx2": int(self.ctx2),
        }


ProcessEvent = ctypes.CFUNCTYPE(None, wintypes.DWORD)
ThreadEventMaybeEmbed = ctypes.CFUNCTYPE(None, ctypes.c_wchar_p, ctypes.c_char_p, ThreadParam, ctypes.c_bool)
ThreadEvent = ctypes.CFUNCTYPE(None, ctypes.c_wchar_p, ctypes.c_char_p, ThreadParam)
OutputCallback = ctypes.CFUNCTYPE(None, ctypes.c_wchar_p, ctypes.c_char_p, ThreadParam, ctypes.c_wchar_p)
HostInfoHandler = ctypes.CFUNCTYPE(None, ctypes.c_int, ctypes.c_wchar_p)
HookInsertHandler = ctypes.CFUNCTYPE(None, wintypes.DWORD, ctypes.c_uint64, ctypes.c_wchar_p)
EmbedCallback = ctypes.CFUNCTYPE(None, ctypes.c_wchar_p, ThreadParam)
I18NQueryCallback = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_wchar_p)
EmuGameInfoCallback = ctypes.CFUNCTYPE(None, ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_wchar_p)


@dataclass(frozen=True)
class LunaHookBridgeConfig:
    luna_root: Path
    game_pid: int
    source_log: Path
    hook_codes: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0
    max_events: int = 0
    idle_timeout_seconds: float = 0.0
    append: bool = True
    encoding: str = "utf-8"
    include_non_japanese: bool = False
    duplicate_window: int = 20
    status_log: Path | None = None

    @property
    def hook_dir(self) -> Path:
        return self.luna_root / "files" / "LunaHook"

    @property
    def host_dll(self) -> Path:
        return self.hook_dir / "LunaHost64.dll"

    @property
    def hook_dll(self) -> Path:
        return self.hook_dir / "LunaHook64.dll"

    @property
    def subprocess_exe(self) -> Path:
        return self.luna_root / "files" / "LunaSubprocess64.exe"


class LunaHookBridge:
    def __init__(self, config: LunaHookBridgeConfig) -> None:
        self.config = config
        self._callbacks: list[Any] = []
        self._seen_outputs: list[str] = []
        self._existing_outputs: set[str] = set()
        self._captured_count = 0
        self._hook_count = 0
        self._process_connect_count = 0
        self._host_messages: list[dict[str, Any]] = []
        self._inserted_hooks: list[dict[str, Any]] = []
        self._synced_threads: list[dict[str, int]] = []

    def dry_run_payload(self) -> dict[str, Any]:
        return {
            "status": "planned",
            "mode": "lunahook_bridge",
            "gamePid": self.config.game_pid,
            "sourceLog": str(self.config.source_log),
            "lunaRoot": str(self.config.luna_root),
            "hostDll": str(self.config.host_dll),
            "hookDll": str(self.config.hook_dll),
            "subprocessExe": str(self.config.subprocess_exe),
            "hookCodes": self.config.hook_codes,
            "append": self.config.append,
            "durationSeconds": self.config.duration_seconds,
            "maxEvents": self.config.max_events,
            "idleTimeoutSeconds": self.config.idle_timeout_seconds,
            "statusLog": str(self.config.status_log) if self.config.status_log else None,
            "nextActions": [
                "Run without --dry-run to connect LunaHook to the game process and append captured Japanese text to the source log.",
                "Keep the scoped source-log watcher and subtitle window running; do not resume translate-all for paused full-archive projects.",
            ],
        }

    def run(self) -> dict[str, Any]:
        if sys.platform != "win32":
            raise RuntimeError("LunaHook bridge is only available on Windows")
        self._validate_files()
        self.config.source_log.parent.mkdir(parents=True, exist_ok=True)
        if self.config.status_log is not None:
            self.config.status_log.parent.mkdir(parents=True, exist_ok=True)
        mode = "a" if self.config.append else "w"
        start = time.monotonic()
        last_activity = start
        last_captured_count = 0
        injection_return_code: int | None = None
        host = self._load_host()
        self._configure_host(host)
        callbacks = self._build_callbacks()
        self._existing_outputs = self._load_existing_outputs() if self.config.append else set()
        self._emit_status("started", {"gamePid": self.config.game_pid, "sourceLog": str(self.config.source_log)})
        with self.config.source_log.open(mode, encoding=self.config.encoding) as handle:
            self._output_handle = handle
            host.Luna_Start(*callbacks)
            host.Luna_Settings(200, False, 932, 10000, 10000, False)
            host.Luna_ConnectProcess(self.config.game_pid)
            if host.Luna_CheckIfNeedInject(self.config.game_pid):
                injection_return_code = self._inject_hook()
                time.sleep(1.0)
            for hook_code in self.config.hook_codes:
                host.Luna_InsertHookCode(self.config.game_pid, hook_code)
            while True:
                now = time.monotonic()
                if self._captured_count != last_captured_count:
                    last_activity = now
                    last_captured_count = self._captured_count
                if self.config.max_events > 0 and self._captured_count >= self.config.max_events:
                    break
                if self.config.duration_seconds > 0 and now - start >= self.config.duration_seconds:
                    break
                if (
                    self.config.idle_timeout_seconds > 0
                    and self._captured_count > 0
                    and now - last_activity >= self.config.idle_timeout_seconds
                ):
                    break
                if self.config.duration_seconds <= 0 and self.config.max_events <= 0:
                    time.sleep(0.1)
                    continue
                time.sleep(0.1)
        payload = {
            "status": "completed",
            "mode": "lunahook_bridge",
            "gamePid": self.config.game_pid,
            "sourceLog": str(self.config.source_log),
            "capturedCount": self._captured_count,
            "hookEventCount": self._hook_count,
            "processConnectCount": self._process_connect_count,
            "injectionReturnCode": injection_return_code,
            "insertedHooks": self._inserted_hooks,
            "syncedThreads": self._synced_threads,
            "hostMessages": self._host_messages[-20:],
            "durationSeconds": round(time.monotonic() - start, 3),
            "nextActions": [
                "Check source-log-status to verify the scoped watcher translated any newly appended lines.",
                "Keep full archive translation paused unless broad token spending is intentional.",
            ],
        }
        self._emit_status("completed", payload)
        return payload

    def _validate_files(self) -> None:
        missing = [
            str(path)
            for path in [self.config.host_dll, self.config.hook_dll, self.config.subprocess_exe]
            if not path.is_file()
        ]
        if missing:
            raise FileNotFoundError("missing LunaHook bridge files: " + ", ".join(missing))

    def _load_host(self) -> ctypes.CDLL:
        dll_dirs = [self.config.luna_root, self.config.luna_root / "files", self.config.hook_dir]
        handles = []
        if hasattr(os, "add_dll_directory"):
            for dll_dir in dll_dirs:
                if dll_dir.is_dir():
                    handles.append(os.add_dll_directory(str(dll_dir)))
        self._dll_directory_handles = handles
        return ctypes.CDLL(str(self.config.host_dll))

    def _configure_host(self, host: ctypes.CDLL) -> None:
        host.Luna_SyncThread.argtypes = (ThreadParam, ctypes.c_bool)
        host.Luna_Settings.argtypes = (
            ctypes.c_int,
            ctypes.c_bool,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_bool,
        )
        host.Luna_ConnectProcess.argtypes = (wintypes.DWORD,)
        host.Luna_CheckIfNeedInject.argtypes = (wintypes.DWORD,)
        host.Luna_CheckIfNeedInject.restype = ctypes.c_bool
        host.Luna_InsertHookCode.argtypes = (wintypes.DWORD, wintypes.LPCWSTR)
        host.Luna_InsertHookCode.restype = ctypes.c_bool
        self._host = host

    def _build_callbacks(self) -> tuple[Any, ...]:
        callbacks = (
            ProcessEvent(self._on_process_connect),
            ProcessEvent(self._on_process_remove),
            ThreadEventMaybeEmbed(self._on_new_hook),
            ThreadEvent(self._on_remove_hook),
            OutputCallback(self._on_output),
            HostInfoHandler(self._on_host_info),
            HookInsertHandler(self._on_hook_insert),
            EmbedCallback(self._on_embed),
            I18NQueryCallback(self._on_i18n_query),
            EmuGameInfoCallback(self._on_emu_game_info),
        )
        self._callbacks.extend(callbacks)
        return callbacks

    def _inject_hook(self) -> int:
        result = subprocess.run(
            [
                str(self.config.subprocess_exe),
                "dllinject",
                str(self.config.game_pid),
                str(self.config.hook_dll),
            ],
            check=False,
            capture_output=True,
        )
        return result.returncode

    def _on_process_connect(self, _pid: int) -> None:
        self._process_connect_count += 1
        self._emit_status("process_connected", {"pid": int(_pid), "processConnectCount": self._process_connect_count})

    def _on_process_remove(self, _pid: int) -> None:
        pass

    def _on_new_hook(self, hook_code: str | None, hook_name: bytes | None, thread_param: ThreadParam, _is_embedable: bool) -> None:
        self._hook_count += 1
        self._emit_status(
            "hook_seen",
            {
                "hookCode": hook_code or "",
                "hookName": (hook_name or b"").decode("utf-8", errors="replace"),
                "thread": thread_param.to_payload(),
                "hookEventCount": self._hook_count,
            },
        )
        if not self.config.hook_codes or (hook_code or "") in self.config.hook_codes:
            self._sync_thread(thread_param)

    def _on_remove_hook(self, _hook_code: str | None, _hook_name: bytes | None, _thread_param: ThreadParam) -> None:
        pass

    def _on_output(self, hook_code: str | None, hook_name: bytes | None, thread_param: ThreadParam, output: str | None) -> None:
        text = (output or "").replace("\r\n", "\n").replace("\r", "\n").strip()
        if not text:
            return
        if not self.config.include_non_japanese and not _contains_japanese(text):
            return
        if _is_control_or_help_text(text):
            self._emit_status(
                "skipped_control",
                {
                    "hookCode": hook_code or "",
                    "hookName": (hook_name or b"").decode("utf-8", errors="replace"),
                    "thread": thread_param.to_payload(),
                    "text": text,
                },
            )
            return
        if text in self._seen_outputs or text in self._existing_outputs:
            return
        self._seen_outputs.append(text)
        if len(self._seen_outputs) > self.config.duplicate_window:
            self._seen_outputs = self._seen_outputs[-self.config.duplicate_window :]
        handle = getattr(self, "_output_handle", None)
        if handle is None:
            return
        handle.write(text + "\n")
        handle.flush()
        self._captured_count += 1
        self._emit_status(
            "captured",
            {
                "capturedCount": self._captured_count,
                "hookCode": hook_code or "",
                "hookName": (hook_name or b"").decode("utf-8", errors="replace"),
                "thread": thread_param.to_payload(),
                "text": text,
            },
        )

    def _load_existing_outputs(self) -> set[str]:
        try:
            return {
                line.strip()
                for line in self.config.source_log.read_text(encoding=self.config.encoding, errors="replace").splitlines()
                if line.strip()
            }
        except OSError:
            return set()

    def _on_host_info(self, level: int, message: str | None) -> None:
        self._host_messages.append({"level": int(level), "message": message or ""})

    def _on_hook_insert(self, pid: int, addr: int, hook_code: str | None) -> None:
        self._inserted_hooks.append({"pid": int(pid), "addr": int(addr), "hookCode": hook_code or ""})
        self._emit_status("hook_inserted", self._inserted_hooks[-1])
        thread_param = ThreadParam()
        thread_param.processId = int(pid)
        thread_param.addr = int(addr)
        thread_param.ctx = 0
        thread_param.ctx2 = 0
        self._sync_thread(thread_param)

    def _on_embed(self, _text: str | None, _thread_param: ThreadParam) -> None:
        pass

    def _on_i18n_query(self, _key: str | None) -> int:
        return 0

    def _on_emu_game_info(self, game_id: str | None, title: str | None, version: str | None) -> None:
        self._host_messages.append({"level": 3, "message": json.dumps({"gameId": game_id, "title": title, "version": version}, ensure_ascii=False)})

    def _sync_thread(self, thread_param: ThreadParam) -> None:
        host = getattr(self, "_host", None)
        if host is None:
            return
        try:
            host.Luna_SyncThread(thread_param, True)
        except OSError:
            return
        self._synced_threads.append(thread_param.to_payload())

    def _emit_status(self, status: str, payload: dict[str, Any]) -> None:
        if self.config.status_log is None:
            return
        event = {"status": status, "timestamp": time.time(), **payload}
        try:
            with self.config.status_log.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(event, ensure_ascii=False) + "\n")
        except OSError:
            return


def _contains_japanese(text: str) -> bool:
    return bool(re.search(r"[\u3040-\u30ff\u3400-\u9fff]", text))


def _is_control_or_help_text(text: str) -> bool:
    ui_terms = [
        "タッチパネル用ＵＩ",
        "バックログ",
        "テキストをスキップ",
        "テキストを自動で読み進め",
        "クイックセーブ",
        "セーブ画面",
        "ロード画面",
        "コンフィグ画面",
        "テキストウィンドウ",
        "タイトル画面",
        "直前に再生されたボイスを再生",
        "マスター音量",
        "次の選択肢",
        "前の選択肢",
    ]
    return any(term in text for term in ui_terms)

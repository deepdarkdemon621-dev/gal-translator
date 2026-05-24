from __future__ import annotations

from dataclasses import dataclass
import ctypes
from ctypes import wintypes
from pathlib import Path
import sys
from typing import Protocol


class ClipboardProvider(Protocol):
    def read_text(self) -> str:
        pass


@dataclass(frozen=True)
class ClipboardEvent:
    raw_text: str


class ClipboardRuntimeInput:
    def __init__(self, provider: ClipboardProvider) -> None:
        self.provider = provider
        self._last_text = ""

    def poll_once(self) -> ClipboardEvent | None:
        text = self.provider.read_text().strip()
        if not text or text == self._last_text:
            return None
        self._last_text = text
        return ClipboardEvent(raw_text=text)


class TextLogRuntimeInput:
    def __init__(
        self,
        log_path: str | Path,
        source_name: str | None = None,
        encoding: str = "utf-8",
        from_start: bool = False,
    ) -> None:
        self.log_path = Path(log_path)
        self.source_name = source_name
        self.encoding = encoding
        self._seen_entry_ids: set[str] = set()
        self._pending: list[str] = []
        if not from_start:
            self._seen_entry_ids.update(entry_id for entry_id, _ in self._load_entries())

    def poll_once(self) -> ClipboardEvent | None:
        if self._pending:
            return ClipboardEvent(raw_text=self._pending.pop(0))
        for entry_id, source in self._load_entries():
            if entry_id in self._seen_entry_ids:
                continue
            self._seen_entry_ids.add(entry_id)
            self._pending.append(source)
        if not self._pending:
            return None
        return ClipboardEvent(raw_text=self._pending.pop(0))

    def _load_entries(self) -> list[tuple[str, str]]:
        if not self.log_path.is_file():
            return []
        from gal_translator.capture import ClipboardLogImporter

        try:
            capture = ClipboardLogImporter().import_log(
                self.log_path,
                source_name=self.source_name,
                encoding=self.encoding,
            )
        except (OSError, UnicodeError):
            return []
        return [(entry.id, entry.source) for entry in capture.entries]


@dataclass(frozen=True)
class ClipboardRecordSummary:
    log_path: Path
    captured_count: int
    poll_count: int
    duration_seconds: float | None
    append: bool


class ClipboardTextRecorder:
    def __init__(self, provider: ClipboardProvider) -> None:
        self.clipboard_input = ClipboardRuntimeInput(provider)

    def record_once(self, log_path: str | Path, append: bool = True) -> ClipboardRecordSummary:
        return self.record(log_path, max_events=1, append=append)

    def record(
        self,
        log_path: str | Path,
        max_events: int = 0,
        append: bool = True,
        max_polls: int = 1,
    ) -> ClipboardRecordSummary:
        path = Path(log_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        mode = "a" if append else "w"
        captured_count = 0
        poll_count = 0
        with path.open(mode, encoding="utf-8") as handle:
            while True:
                if max_polls > 0 and poll_count >= max_polls:
                    break
                event = self.clipboard_input.poll_once()
                poll_count += 1
                if event is not None:
                    handle.write(event.raw_text.replace("\r\n", "\n").replace("\r", "\n") + "\n")
                    captured_count += 1
                    if max_events > 0 and captured_count >= max_events:
                        break
        return ClipboardRecordSummary(
            log_path=path,
            captured_count=captured_count,
            poll_count=poll_count,
            duration_seconds=None,
            append=append,
        )


class WindowsClipboardProvider:
    CF_UNICODETEXT = 13

    def __init__(self) -> None:
        if sys.platform != "win32":
            raise RuntimeError("WindowsClipboardProvider is only available on Windows")
        self.user32 = ctypes.windll.user32
        self.kernel32 = ctypes.windll.kernel32
        self.user32.OpenClipboard.argtypes = [wintypes.HWND]
        self.user32.OpenClipboard.restype = wintypes.BOOL
        self.user32.GetClipboardData.argtypes = [wintypes.UINT]
        self.user32.GetClipboardData.restype = ctypes.c_void_p
        self.user32.CloseClipboard.argtypes = []
        self.user32.CloseClipboard.restype = wintypes.BOOL
        self.kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
        self.kernel32.GlobalLock.restype = ctypes.c_void_p
        self.kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
        self.kernel32.GlobalUnlock.restype = wintypes.BOOL

    def read_text(self) -> str:
        if not self.user32.OpenClipboard(None):
            return ""
        handle = None
        pointer = None
        try:
            handle = self.user32.GetClipboardData(self.CF_UNICODETEXT)
            if not handle:
                return ""
            pointer = self.kernel32.GlobalLock(handle)
            if not pointer:
                return ""
            return ctypes.wstring_at(pointer)
        finally:
            if pointer:
                self.kernel32.GlobalUnlock(handle)
            self.user32.CloseClipboard()

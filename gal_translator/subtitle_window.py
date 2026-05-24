from __future__ import annotations

from dataclasses import dataclass
import tkinter as tk
from typing import Any, Callable, Protocol

from gal_translator.clipboard import ClipboardEvent, ClipboardRuntimeInput, ClipboardProvider
from gal_translator.runtime import RuntimeSubtitleService


class RuntimeTextInput(Protocol):
    def poll_once(self) -> ClipboardEvent | None:
        pass


@dataclass(frozen=True)
class SubtitleWindowConfig:
    interval_ms: int = 250
    font_size: int = 28
    opacity: float = 0.85
    width: int = 900
    height: int = 140
    topmost: bool = True
    x: int | None = None
    y: int | None = None
    font_family: str = "Microsoft YaHei UI"
    background: str = "#050505"
    foreground: str = "#f5f5f5"
    clear_after_ms: int = 0
    exit_after_ms: int = 0

    def geometry(self) -> str:
        base = f"{max(200, self.width)}x{max(80, self.height)}"
        if self.x is None or self.y is None:
            return base
        return f"{base}+{self.x}+{self.y}"

    def normalized_opacity(self) -> float:
        return max(0.2, min(1.0, self.opacity))

    def poll_interval_ms(self) -> int:
        return max(50, self.interval_ms)

    def auto_exit_after_ms(self) -> int:
        return max(0, self.exit_after_ms)

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "intervalMs": self.poll_interval_ms(),
            "fontSize": self.font_size,
            "opacity": self.normalized_opacity(),
            "width": max(200, self.width),
            "height": max(80, self.height),
            "topmost": self.topmost,
            "x": self.x,
            "y": self.y,
            "fontFamily": self.font_family,
            "background": self.background,
            "foreground": self.foreground,
            "clearAfterMs": max(0, self.clear_after_ms),
            "exitAfterMs": self.auto_exit_after_ms(),
        }

    @classmethod
    def from_json_dict(cls, payload: dict[str, Any]) -> "SubtitleWindowConfig":
        return cls(
            interval_ms=_int_value(payload, "intervalMs", cls.interval_ms),
            font_size=_int_value(payload, "fontSize", cls.font_size),
            opacity=_float_value(payload, "opacity", cls.opacity),
            width=_int_value(payload, "width", cls.width),
            height=_int_value(payload, "height", cls.height),
            topmost=_bool_value(payload, "topmost", cls.topmost),
            x=_optional_int_value(payload, "x"),
            y=_optional_int_value(payload, "y"),
            font_family=_str_value(payload, "fontFamily", cls.font_family),
            background=_str_value(payload, "background", cls.background),
            foreground=_str_value(payload, "foreground", cls.foreground),
            clear_after_ms=_int_value(payload, "clearAfterMs", cls.clear_after_ms),
            exit_after_ms=_int_value(payload, "exitAfterMs", cls.exit_after_ms),
        )


def _int_value(payload: dict[str, Any], key: str, default: int) -> int:
    value = payload.get(key, default)
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _optional_int_value(payload: dict[str, Any], key: str) -> int | None:
    value = payload.get(key)
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float_value(payload: dict[str, Any], key: str, default: float) -> float:
    value = payload.get(key, default)
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _bool_value(payload: dict[str, Any], key: str, default: bool) -> bool:
    value = payload.get(key, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return default


def _str_value(payload: dict[str, Any], key: str, default: str) -> str:
    value = payload.get(key, default)
    if value is None:
        return default
    return str(value)


@dataclass(frozen=True)
class SubtitleViewState:
    text: str
    match_type: str
    visible: bool
    updated_at_ms: int | None = None


class SubtitleViewModel:
    def __init__(self, runtime: RuntimeSubtitleService) -> None:
        self.runtime = runtime
        self.state = SubtitleViewState(text="", match_type="idle", visible=False)
        self._last_source_text: str | None = None

    @property
    def last_source_text(self) -> str:
        return self._last_source_text or ""

    def update_source(self, source_text: str, now_ms: int | None = None) -> SubtitleViewState:
        self._last_source_text = source_text
        display = self.runtime.display_for(source_text)
        self.state = SubtitleViewState(
            text=display.text,
            match_type=display.match_type,
            visible=bool(display.text),
            updated_at_ms=now_ms,
        )
        return self.state

    def refresh_unmatched_source(self, now_ms: int | None = None) -> tuple[SubtitleViewState, bool]:
        if self._last_source_text is None or self.state.match_type != "unmatched":
            return self.state, False
        display = self.runtime.display_for(self._last_source_text)
        if not display.text:
            return self.state, False
        self.state = SubtitleViewState(
            text=display.text,
            match_type=display.match_type,
            visible=True,
            updated_at_ms=now_ms,
        )
        return self.state, True

    def clear_if_stale(self, now_ms: int, clear_after_ms: int) -> SubtitleViewState:
        if clear_after_ms <= 0 or not self.state.visible or self.state.updated_at_ms is None:
            return self.state
        if now_ms - self.state.updated_at_ms < clear_after_ms:
            return self.state
        self.state = SubtitleViewState(text="", match_type="cleared", visible=False, updated_at_ms=now_ms)
        return self.state


class SubtitleWindow:
    def __init__(
        self,
        runtime: RuntimeSubtitleService,
        clipboard_provider: ClipboardProvider | None = None,
        config: SubtitleWindowConfig | None = None,
        event_logger: Callable[[str, SubtitleViewState], None] | None = None,
        initial_source_text: str | None = None,
        runtime_input: RuntimeTextInput | None = None,
    ) -> None:
        self.view_model = SubtitleViewModel(runtime)
        if runtime_input is None and clipboard_provider is None:
            raise ValueError("clipboard_provider is required when runtime_input is not provided")
        self.runtime_input = runtime_input or ClipboardRuntimeInput(clipboard_provider)
        self.config = config or SubtitleWindowConfig()
        self.event_logger = event_logger
        self.root = tk.Tk()
        self.root.title("Gal Translator")
        self.root.geometry(self.config.geometry())
        self.root.configure(bg=self.config.background)
        self.root.attributes("-alpha", self.config.normalized_opacity())
        self.root.attributes("-topmost", self.config.topmost)

        self.label = tk.Label(
            self.root,
            text="",
            bg=self.config.background,
            fg=self.config.foreground,
            font=(self.config.font_family, self.config.font_size),
            wraplength=max(100, self.config.width - 40),
            justify="center",
        )
        self.label.pack(fill="both", expand=True, padx=20, pady=16)
        if initial_source_text:
            now_ms = int(self.root.tk.call("clock", "milliseconds"))
            state = self.view_model.update_source(initial_source_text, now_ms=now_ms)
            self.label.configure(text=state.text)

    def run(self) -> None:
        exit_after_ms = self.config.auto_exit_after_ms()
        if exit_after_ms > 0:
            self.root.after(exit_after_ms, self.root.destroy)
        self._poll()
        self.root.mainloop()

    def _poll(self) -> None:
        event = self.runtime_input.poll_once()
        now_ms = int(self.root.tk.call("clock", "milliseconds"))
        if event is not None:
            state = self.view_model.update_source(event.raw_text, now_ms=now_ms)
            if self.event_logger is not None:
                self.event_logger(event.raw_text, state)
        else:
            state, refreshed = self.view_model.refresh_unmatched_source(now_ms=now_ms)
            if refreshed and self.event_logger is not None:
                self.event_logger(self.view_model.last_source_text, state)
            state = self.view_model.clear_if_stale(now_ms, self.config.clear_after_ms)
        self.label.configure(text=state.text)
        self.root.after(self.config.poll_interval_ms(), self._poll)

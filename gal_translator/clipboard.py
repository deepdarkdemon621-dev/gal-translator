from __future__ import annotations

from dataclasses import dataclass
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

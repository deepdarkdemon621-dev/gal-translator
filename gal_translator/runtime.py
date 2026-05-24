from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from gal_translator.matching import MatchIndex


@dataclass(frozen=True)
class SubtitleDisplay:
    text: str
    match_type: str
    show_source: bool


class RuntimeSubtitleService:
    def __init__(self, match_index: MatchIndex) -> None:
        self.match_index = match_index

    def display_for(self, source_text: str) -> SubtitleDisplay:
        match = self.match_index.lookup(source_text)
        if match.translation is None:
            return SubtitleDisplay(text="", match_type=match.match_type, show_source=False)
        return SubtitleDisplay(text=match.translation, match_type=match.match_type, show_source=False)


class ReloadableRuntimeSubtitleService(RuntimeSubtitleService):
    def __init__(
        self,
        load_records: Callable[[], list[Any]],
        current_signature: Callable[[], Any],
    ) -> None:
        self._load_records = load_records
        self._current_signature = current_signature
        self._signature = None
        self.reload_error = ""
        super().__init__(MatchIndex([]))
        self.reload_if_changed(force=True)

    def display_for(self, source_text: str) -> SubtitleDisplay:
        self.reload_if_changed()
        return super().display_for(source_text)

    def reload_if_changed(self, force: bool = False) -> bool:
        signature = self._current_signature()
        if not force and signature == self._signature:
            return False
        try:
            self.match_index = MatchIndex(self._load_records())
        except Exception as error:
            self.reload_error = str(error)
            return False
        self._signature = signature
        self.reload_error = ""
        return True

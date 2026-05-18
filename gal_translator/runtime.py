from __future__ import annotations

from dataclasses import dataclass

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

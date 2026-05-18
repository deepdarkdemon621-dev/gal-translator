from __future__ import annotations

import re

from gal_translator.parser import ScriptEntry


class StoryTextFilter:
    def keep_story_entries(self, entries: list[ScriptEntry]) -> list[ScriptEntry]:
        return [entry for entry in entries if _is_story_entry(entry)]


def _is_story_entry(entry: ScriptEntry) -> bool:
    path_parts = {part.lower() for part in re.split(r"[\\/]", entry.file)}
    if path_parts.intersection({"system", "config", "ui", "gui", "menu"}):
        return False
    if not _contains_japanese(entry.source):
        return False
    return True


def _contains_japanese(text: str) -> bool:
    return bool(re.search(r"[\u3040-\u30ff\u3400-\u9fff]", text))

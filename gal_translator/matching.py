from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
import unicodedata


@dataclass(frozen=True)
class TranslationRecord:
    entry_id: str
    source: str
    translation: str
    status: str


@dataclass(frozen=True)
class MatchResult:
    entry_id: str | None
    translation: str | None
    match_type: str


class MatchIndex:
    def __init__(self, records: list[TranslationRecord]) -> None:
        translated = [record for record in records if record.status == "translated" and record.translation]
        self._exact = {_hash(record.source): record for record in translated}
        self._normalized = {_normalize(record.source): record for record in translated}

    def lookup(self, raw_text: str) -> MatchResult:
        exact = self._exact.get(_hash(raw_text))
        if exact is not None:
            return MatchResult(exact.entry_id, exact.translation, "exact")

        normalized = self._normalized.get(_normalize(raw_text))
        if normalized is not None:
            return MatchResult(normalized.entry_id, normalized.translation, "normalized")

        return MatchResult(None, None, "unmatched")


def _hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def _normalize(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text)
    lines = [line.strip() for line in re.split(r"\r?\n", normalized) if line.strip()]
    lines = _collapse_consecutive_duplicates(lines)
    joined = "".join(lines)
    joined = re.sub(r"\s+", "", joined)
    return joined


def _collapse_consecutive_duplicates(lines: list[str]) -> list[str]:
    collapsed: list[str] = []
    for line in lines:
        if collapsed and collapsed[-1] == line:
            continue
        collapsed.append(line)
    return collapsed

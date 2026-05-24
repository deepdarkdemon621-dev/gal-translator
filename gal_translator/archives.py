from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re


DEFAULT_SAMPLE_BYTES = 8 * 1024 * 1024
VISIBLE_EXTENSIONS = {
    ".ast",
    ".csv",
    ".jpg",
    ".jpeg",
    ".json",
    ".ks",
    ".lua",
    ".mp4",
    ".ogg",
    ".otf",
    ".png",
    ".rpy",
    ".scn",
    ".ttc",
    ".ttf",
    ".txt",
    ".wav",
    ".webm",
}
SCRIPT_EXTENSIONS = {".ast", ".ks", ".rpy", ".scn", ".txt"}
MAX_ENTRY_NAME_BYTES = 512


@dataclass(frozen=True)
class ArchiveEntry:
    path: str
    offset: int
    size: int


@dataclass(frozen=True)
class ArchiveDiagnostic:
    relative_path: str
    format_id: str
    label: str
    magic: str
    size: int
    sampled_bytes: int
    structured_entry_count: int
    entries: tuple[ArchiveEntry, ...]
    visible_extension_counts: dict[str, int]
    visible_script_paths: tuple[str, ...]
    notes: tuple[str, ...]


class ArchiveInspector:
    def inspect_game_root(self, game_root: Path, relative_paths: list[str]) -> tuple[ArchiveDiagnostic, ...]:
        diagnostics: list[ArchiveDiagnostic] = []
        for relative_path in relative_paths:
            path = game_root / relative_path
            if not path.is_file() or not _is_candidate_archive(relative_path):
                continue
            diagnostic = self.inspect_file(path, relative_path)
            if diagnostic is not None:
                diagnostics.append(diagnostic)
        return tuple(diagnostics)

    def inspect_file(self, path: Path, relative_path: str | None = None) -> ArchiveDiagnostic | None:
        size = path.stat().st_size
        with path.open("rb") as handle:
            sample = handle.read(min(size, DEFAULT_SAMPLE_BYTES))

        if not sample.startswith(b"pf8"):
            return None

        entries = _parse_pf8_entries(sample, archive_size=size)
        archive_paths = tuple(entry.path for entry in entries)
        if not archive_paths:
            archive_paths = _extract_visible_paths(sample)

        extension_counts: dict[str, int] = {}
        for archive_path in archive_paths:
            extension = _extension(archive_path)
            extension_counts[extension] = extension_counts.get(extension, 0) + 1

        script_paths = tuple(
            archive_path for archive_path in archive_paths if _looks_like_script_path(archive_path)
        )[:50]
        notes = ["sampled archive header/file table only; no extraction was performed"]
        if entries:
            notes.append("structured pf8 file-table entries were parsed")
        if script_paths:
            notes.append("visible script-like entries found")

        return ArchiveDiagnostic(
            relative_path=relative_path or path.name,
            format_id="pf8_pfs",
            label="PFS/pf8 archive",
            magic=sample[:8].hex(" "),
            size=size,
            sampled_bytes=len(sample),
            structured_entry_count=len(entries),
            entries=entries,
            visible_extension_counts=dict(sorted(extension_counts.items())),
            visible_script_paths=script_paths,
            notes=tuple(notes),
        )


def _is_candidate_archive(relative_path: str) -> bool:
    lower = relative_path.lower()
    return lower.endswith(".pfs") or ".pfs." in lower


def _extract_visible_paths(sample: bytes) -> tuple[str, ...]:
    text = sample.decode("ascii", errors="ignore")
    candidates = re.findall(r"[A-Za-z0-9_@./\\ -]{2,}\.[A-Za-z0-9]{1,8}", text)
    paths: set[str] = set()
    for candidate in candidates:
        cleaned = candidate.strip(" \t\r\n\x00")
        if _is_plausible_path(cleaned):
            paths.add(cleaned)
    return tuple(sorted(paths, key=lambda item: item.lower()))


def _parse_pf8_entries(sample: bytes, archive_size: int) -> tuple[ArchiveEntry, ...]:
    entries: dict[tuple[str, int, int], ArchiveEntry] = {}
    lower_bound = 3
    upper_bound = len(sample) - 12
    for position in range(lower_bound, upper_bound):
        offset = int.from_bytes(sample[position : position + 4], "little")
        item_size = int.from_bytes(sample[position + 4 : position + 8], "little")
        name_size = int.from_bytes(sample[position + 8 : position + 12], "little")
        if name_size <= 0 or name_size > MAX_ENTRY_NAME_BYTES:
            continue
        name_start = position + 12
        name_end = name_start + name_size
        if name_end > len(sample):
            continue
        raw_name = sample[name_start:name_end]
        try:
            path = raw_name.decode("utf-8")
        except UnicodeDecodeError:
            continue
        if not _is_plausible_path(path):
            continue
        if offset < 0 or offset >= archive_size:
            continue
        if item_size <= 0 or item_size > archive_size:
            continue
        entries[(path, offset, item_size)] = ArchiveEntry(path=path, offset=offset, size=item_size)
    return tuple(sorted(entries.values(), key=lambda entry: entry.path.lower()))


def _is_plausible_path(path: str) -> bool:
    if len(path) > 180:
        return False
    if path.startswith(".") or path.endswith("."):
        return False
    if any(ord(character) < 32 for character in path):
        return False
    if _extension(path) not in VISIBLE_EXTENSIONS:
        return False
    if any(part in {"", ".", ".."} for part in re.split(r"[\\/]", path)):
        return False
    return True


def _extension(path: str) -> str:
    match = re.search(r"(\.[A-Za-z0-9]{1,8})$", path)
    return match.group(1).lower() if match else ""


def _looks_like_script_path(path: str) -> bool:
    extension = _extension(path)
    lower = path.lower().replace("/", "\\")
    if extension == ".ast":
        return True
    if extension in SCRIPT_EXTENSIONS and (
        lower.startswith("script\\")
        or lower.startswith("scenario\\")
        or "\\script\\" in lower
        or "\\scenario\\" in lower
    ):
        return True
    return False


def is_script_entry(entry: ArchiveEntry) -> bool:
    return _looks_like_script_path(entry.path)

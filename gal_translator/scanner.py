from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ScannedFile:
    relative_path: str
    extension: str
    size: int


@dataclass(frozen=True)
class ScanReport:
    input_path: Path
    game_root: Path
    input_was_exe: bool
    files: tuple[ScannedFile, ...]
    directories: tuple[str, ...]
    extensions: tuple[str, ...]
    files_by_extension: dict[str, tuple[ScannedFile, ...]]


class GameScanner:
    def scan(self, input_path: str | Path) -> ScanReport:
        resolved_input = Path(input_path).resolve()
        input_was_exe = resolved_input.is_file() and resolved_input.suffix.lower() == ".exe"
        game_root = resolved_input.parent if input_was_exe else resolved_input

        files: list[ScannedFile] = []
        directories: set[str] = set()
        grouped: dict[str, list[ScannedFile]] = {}

        for path in sorted(game_root.rglob("*")):
            relative_path = path.relative_to(game_root).as_posix()
            if path.is_dir():
                directories.add(relative_path)
                continue
            if not path.is_file():
                continue

            extension = path.suffix.lower()
            scanned = ScannedFile(
                relative_path=relative_path,
                extension=extension,
                size=path.stat().st_size,
            )
            files.append(scanned)
            grouped.setdefault(extension, []).append(scanned)

        files_by_extension = {
            extension: tuple(items)
            for extension, items in sorted(grouped.items(), key=lambda item: item[0])
        }

        return ScanReport(
            input_path=resolved_input,
            game_root=game_root,
            input_was_exe=input_was_exe,
            files=tuple(files),
            directories=tuple(sorted(directories)),
            extensions=tuple(files_by_extension.keys()),
            files_by_extension=files_by_extension,
        )


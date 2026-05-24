from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

from gal_translator.scanner import ScanReport


@dataclass(frozen=True)
class ExtractorProfile:
    profile_id: str
    label: str
    source_lang: str
    target_lang: str
    extensions: tuple[str, ...]
    directories: tuple[str, ...]
    script_globs: tuple[str, ...]
    encoding: str


class ExtractorProfileRegistry:
    def __init__(self, profiles: list[ExtractorProfile]) -> None:
        self._profiles = profiles

    @classmethod
    def default(cls) -> ExtractorProfileRegistry:
        return cls(
            [
                ExtractorProfile(
                    profile_id="direct_script",
                    label="Direct script files",
                    source_lang="ja",
                    target_lang="zh-Hans",
                    extensions=(".ks", ".rpy", ".txt", ".json", ".csv"),
                    directories=("scenario", "script"),
                    script_globs=(
                        "**/*.ks",
                        "**/*.rpy",
                        "0.txt",
                        "scenario/**/*.txt",
                        "scenario/**/*.json",
                        "scenario/**/*.csv",
                        "script/**/*.txt",
                        "script/**/*.json",
                        "script/**/*.csv",
                    ),
                    encoding="utf-8",
                )
            ]
        )

    @classmethod
    def from_directories(cls, directories: list[str | Path]) -> ExtractorProfileRegistry:
        profiles: list[ExtractorProfile] = []
        for directory in directories:
            profile_dir = Path(directory)
            if not profile_dir.is_dir():
                continue
            for path in sorted(profile_dir.glob("*.json")):
                profiles.append(_load_profile(path))
        return cls(profiles)

    def match(self, report: ScanReport) -> list[ExtractorProfile]:
        return [profile for profile in self._profiles if _matches(profile, report)]


def _matches(profile: ExtractorProfile, report: ScanReport) -> bool:
    if profile.profile_id == "direct_script":
        return _matches_direct_script(report)

    if set(profile.extensions).intersection(report.extensions):
        return True

    root_dirs = {directory.split("/", 1)[0].lower() for directory in report.directories}
    return bool(root_dirs.intersection(profile.directories))


def _matches_direct_script(report: ScanReport) -> bool:
    root_dirs = {directory.split("/", 1)[0].lower() for directory in report.directories}
    if root_dirs.intersection({"scenario", "script"}):
        return True

    for file in report.files:
        normalized = file.relative_path.lower().replace("\\", "/")
        if file.extension in {".ks", ".rpy"}:
            return True
        if normalized == "0.txt":
            return True
        if normalized.startswith(("scenario/", "script/")) and file.extension in {
            ".csv",
            ".json",
            ".txt",
        }:
            return True
    return False


def _load_profile(path: Path) -> ExtractorProfile:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return ExtractorProfile(
        profile_id=payload["profileId"],
        label=payload["label"],
        source_lang=payload.get("sourceLang", "ja"),
        target_lang=payload.get("targetLang", "zh-Hans"),
        extensions=tuple(extension.lower() for extension in payload.get("extensions", [])),
        directories=tuple(directory.lower() for directory in payload.get("directories", [])),
        script_globs=tuple(payload.get("scriptGlobs", [])),
        encoding=payload.get("encoding", "utf-8"),
    )

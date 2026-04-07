from __future__ import annotations

import dataclasses
import fnmatch
import os
import sysconfig
from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

from packaging.specifiers import SpecifierSet
from packaging.tags import Tag

if TYPE_CHECKING:
    from hanzo.settings import BuildConfig, HanzoSettings


class GitignorePattern(NamedTuple):
    pattern: str
    negated: bool


def _load_gitignore_patterns(root: Path) -> list[GitignorePattern]:
    """Read .gitignore from root and return a list of GitignorePattern entries."""
    gitignore = root / ".gitignore"
    if not gitignore.exists():
        return []
    patterns: list[GitignorePattern] = []
    for line in gitignore.read_text(encoding="utf-8").splitlines():
        line = line.rstrip()
        if not line or line.startswith("#"):
            continue
        negated = line.startswith("!")
        if negated:
            line = line[1:]
        patterns.append(GitignorePattern(line, negated))
    return patterns


def _gitignore_matches(posix_path: str, pattern: str, *, is_dir: bool = False) -> bool:
    """Return True if posix_path matches the given gitignore pattern."""
    dir_only = pattern.endswith("/")
    if dir_only:
        if not is_dir:
            return False
        pattern = pattern[:-1]

    if not pattern:
        return False

    # No slash in pattern: match against basename only (any depth)
    if "/" not in pattern.lstrip("/"):
        name = posix_path.rsplit("/", 1)[-1] if "/" in posix_path else posix_path
        return fnmatch.fnmatch(name, pattern)

    # Pattern with slash: match against the full path from root
    pat = pattern.lstrip("/")
    return fnmatch.fnmatch(posix_path, pat) or fnmatch.fnmatch(posix_path, "*/" + pat)


def _is_gitignored(
    posix_path: str, patterns: list[GitignorePattern], *, is_dir: bool = False
) -> bool:
    """Return True if posix_path is excluded by the given gitignore patterns."""
    ignored = False
    for entry in patterns:
        if _gitignore_matches(posix_path, entry.pattern, is_dir=is_dir):
            ignored = not entry.negated
    return ignored


def collect_src_files(src_dir: Path) -> Iterator[tuple[Path, Path]]:
    """Yield ``(archive_path, disk_path)`` for all non-gitignored files under src_dir.

    ``archive_path`` is relative to src_dir (e.g. ``hello/__init__.py``).
    ``disk_path`` is the absolute path on disk.

    .gitignore patterns are loaded from the current working directory.
    """
    cwd = Path.cwd()
    src_dir = src_dir if src_dir.is_absolute() else cwd / src_dir
    patterns = _load_gitignore_patterns(cwd)

    for dirpath_str, dirnames, filenames in os.walk(src_dir):
        dirpath = Path(dirpath_str)
        rel_dir = dirpath.relative_to(cwd)

        # Prune ignored directories in-place so os.walk skips their subtrees
        dirnames[:] = [
            d
            for d in dirnames
            if not _is_gitignored((rel_dir / d).as_posix(), patterns, is_dir=True)
        ]

        for fname in filenames:
            rel_file = rel_dir / fname
            if not _is_gitignored(rel_file.as_posix(), patterns):
                yield dirpath.relative_to(src_dir) / fname, dirpath / fname


def to_snakecase(s: str) -> str:
    return s.replace("-", "_").replace(".", "_")


def calculate_wheel_tag(settings: HanzoSettings, config: BuildConfig, root_is_purelib: bool) -> Tag:
    if root_is_purelib:
        return Tag("py3", "none", "any")

    current_interpreter = "cp" + sysconfig.get_config_var("py_version_nodot")
    current_python_version = sysconfig.get_config_var("py_version")
    stable_abi = settings.wheel.stable_abi

    interpreter = current_interpreter
    abi = current_interpreter

    if stable_abi is not None:
        stable_abi_spec = SpecifierSet(stable_abi)
        if len(stable_abi_spec) > 1:
            raise ValueError(f"stable ABI must be a single specifier, got {stable_abi!r}")
        if current_python_version in stable_abi_spec:
            (spec,) = stable_abi_spec
            if spec.operator != ">=":
                raise ValueError(
                    f"stable ABI specifier must use '>=' operator, got {spec.operator!r}"
                )
            # TODO: Clean this up to allow prereleases
            interpreter = "cp" + spec.version.replace(".", "")
            abi = "abi3"

    platform = config.platform
    if platform.os_version is None:
        if platform.system == "macosx":
            guessed_macver = guess_minimum_macver(settings, platform.arch)
            platform = dataclasses.replace(platform, os_version=guessed_macver)

    return Tag(interpreter, abi, str(platform))


def guess_minimum_macver(settings: HanzoSettings, arch: str) -> str:
    if arch not in ("arm64", "x86_64", "universal2"):
        raise ValueError(f"unsupported macOS architecture: {arch!r}")
    if arch == "arm64":
        # Apple Silicon only runs macOS>=11.0.
        return "11.0"
    if settings.cc.standard == "c++17":
        # C++17 support is only available starting in macOS 10.15 ("Catalina").
        return "10.15"
    # best-effort guess.
    return "10.13"


__all__ = [
    "GitignorePattern",
    "calculate_wheel_tag",
    "collect_src_files",
    "guess_minimum_macver",
    "to_snakecase",
]

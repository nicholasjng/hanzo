from __future__ import annotations

import dataclasses
import fnmatch
import os
import sysconfig
from collections.abc import Iterable
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple, Self

from packaging.specifiers import SpecifierSet
from packaging.tags import Tag

if TYPE_CHECKING:
    from hanzo.settings import BuildConfig, HanzoSettings


class GitignorePattern(NamedTuple):
    pattern: str
    negated: bool


class GitignoreMatcher:
    def __init__(self, patterns: list[GitignorePattern]):
        self.patterns: list[GitignorePattern] = patterns

    @classmethod
    def from_gitignore(cls, path: str | os.PathLike[str] | None = None) -> Self:
        if path is None:
            path = Path.cwd()
        gitignore = Path(path) / ".gitignore"
        if not gitignore.exists():
            return cls([])

        patterns: list[GitignorePattern] = []
        for line in gitignore.read_text(encoding="utf-8").splitlines():
            line = line.rstrip()
            if not line or line.startswith("#"):
                continue
            negated = line.startswith("!")
            if negated:
                line = line[1:]
            patterns.append(GitignorePattern(line, negated))
        return cls(patterns)

    def ignored(self, path: str | os.PathLike[str]) -> bool:
        """Check if a path is ignored based on the patterns in this .gitignore file."""
        if not self.patterns:
            return False

        pathlib_path = Path(path)
        ignored: bool = False
        for pattern, negated in self.patterns:
            dir_only = pattern.endswith("/")
            if dir_only:
                if not pathlib_path.is_dir():
                    continue
                pattern = pattern[:-1]

            # No slash in pattern: match against basename only (any depth)
            pat = pattern.lstrip("/")
            if "/" not in pat:
                match = fnmatch.fnmatch(pathlib_path.name, pattern)
            else:
                # Pattern with slash: match against the full path from root
                posix_path = pathlib_path.as_posix()
                match = fnmatch.fnmatch(posix_path, pat) or fnmatch.fnmatch(posix_path, "*/" + pat)

            if match:
                ignored = not negated

        return ignored

    def match_files(self, path: str | os.PathLike[str]) -> Iterable[Path]:
        path = Path(path).resolve()

        for sdirpath, dirnames, filenames in os.walk(path):
            dirpath = Path(sdirpath)
            rel_dir = dirpath.relative_to(Path.cwd())

            # Prune ignored directories in-place so os.walk skips their subtrees
            dirnames[:] = [d for d in dirnames if not self.ignored(Path(d).resolve())]

            for fname in filenames:
                rel_file = rel_dir / fname
                if not self.ignored(rel_file):
                    yield rel_file


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
    "GitignoreMatcher",
    "GitignorePattern",
    "calculate_wheel_tag",
    "guess_minimum_macver",
    "to_snakecase",
]

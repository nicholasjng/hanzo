import contextlib
import os
import site
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Required, Self, TypedDict, cast, overload

SITE_ID = "@site"
ROOTPATH_ID = "@rootpath"

"""Ninja rule definitions in Python."""

# TODO: Instead of string templates, use actual Python rule classes later.
cc_compile = """
rule cc
  depfile = $depfile
  deps = gcc
  command = {compiler} $defines $includes $flags -MD -MT $out -MF $depfile -o $out -c $in
  description = Building C++ object $out
"""

cc_linkstatic = """
rule cc-linkstatic
  command = $pre_link && rm -f $target_file && {archiver} $target_file $linkflags $in && {ranlib} $target_file && touch $target_file && $post_build
  description = Linking C++ static library $target_file
  restat = $restat
"""

cc_linkshared = """
rule cc_linkshared
  command = $pre_link && {compiler} $cflags $archflags $ldflags -o $target_file $in $link_path $link_libraries && $post_build
  description = Linking C++ shared module $target_file
  restat = $restat
"""


class GlobDict(TypedDict, total=False):
    include: Required[list[str]]
    exclude: list[str]
    allow_empty: bool


@dataclass(frozen=True)
class FileGlob:
    include: list[str]
    exclude: list[str] = field(default_factory=list)
    allow_empty: bool = False

    def resolve(self) -> list[str]:
        results: list[str] = []
        for p in self.include:
            star = p.find("*")
            if star == -1:
                if p not in self.exclude:
                    results.append(p)
            else:
                path, pattern = Path(p[:star]), p[star:]
                # paths are relative to cwd, so use with chdir().
                for res in path.glob(pattern):
                    res = str(res)
                    if res not in self.exclude:
                        results.append(res)
        if not results and not self.allow_empty:
            raise ValueError(f"glob pattern {self.include} did not yield any results")

        return results


@overload
def substitute(path: str | os.PathLike[str], sentinel: str, value: str) -> Path: ...


@overload
def substitute(
    path: str | os.PathLike[str], sentinel: Iterable[str], value: Iterable[str]
) -> Path: ...


def substitute(
    path: str | os.PathLike[str], sentinel: str | Iterable[str], value: str | Iterable[str]
) -> Path:
    spath = str(path)
    if isinstance(sentinel, str):
        value = cast(str, value)
        spath = spath.replace(sentinel, value)
    else:
        for s, v in zip(sentinel, value):
            spath = spath.replace(s, v)
    return Path(str(path))


class Target:
    def __init__(self, name: str) -> None:
        self._name = name

    @property
    def name(self) -> str:
        return self._name


class CCLibraryTarget(Target):
    def __init__(
        self,
        name: str,
        rootpath: str | os.PathLike[str],
        sources: list[str | GlobDict],
        includes: list[str] | None = None,
        defines: list[str] | None = None,
        flags: list[str] | None = None,
        ldflags: list[str] | None = None,
    ):
        super().__init__(name)
        (site_packages,) = site.getsitepackages()
        self.rootpath = substitute(rootpath, SITE_ID, site_packages)
        self.sources = self.collect_sources(sources)
        self.includes = self.process_includes(includes or [])
        self.defines = self.process_defines(defines or [])
        self.flags = self.process_flags(flags or [], str(self.rootpath))
        self.ldflags = self.process_flags(ldflags or [], str(self.rootpath))

    @classmethod
    def from_toml(cls, toml: dict[str, Any]) -> Self: ...

    def to_string(self, toolchain, rules: list[str]) -> str: ...

    def collect_sources(self, sources: list[str | GlobDict]) -> list[str]:
        results: list[str] = []
        for item in sources:
            if isinstance(item, str):
                results.append(item)
            else:
                g = FileGlob(**item)
                with contextlib.chdir(self.rootpath):
                    results.extend(g.resolve())
        return results

    def process_defines(self, defines: list[str]) -> list[str]:
        return [d if d.startswith("-D") else "-D" + d for d in defines]

    # TODO: Use some kind of context object instead of just rootpath to interpolate flags
    # (important later when selecting flag sets based on compilation environment)
    def process_flags(self, flags: list[str], rootpath: str) -> list[str]:
        results: list[str] = []
        for f in flags:
            f = substitute(f, ROOTPATH_ID, rootpath)
            results.append(str(f))
        return results

    def process_includes(self, includes: list[str]) -> list[str]:
        return [str(self.rootpath / i) for i in includes]

    @property
    def rules(self) -> dict[str, str]:
        return {
            "cc_compile": cc_compile,
            "cc_linkstatic": cc_linkstatic,
            "cc_linkshared": cc_linkshared,
        }

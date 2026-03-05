"""Ninja rule definitions in Python."""

import contextlib
import os
import site
import sysconfig
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Required, Self, TypedDict

from .rules import cc_compile, cc_linkshared, cc_linkstatic

SITE_ID = "@site"
ROOTPATH_ID = "@rootpath"
PYTHON_HEADERS_ID = "@python_headers"


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


def substitute(path: str | os.PathLike[str], replacements: dict[str, str]) -> Path:
    spath = str(path)
    for k, v in replacements.items():
        spath = spath.replace(k, v)
    return Path(spath)


class Target:
    def __init__(
        self,
        name: str,
        sources: list[str | GlobDict],
        rootpath: str | os.PathLike[str] | None = None,
        dependencies: list["Target"] | None = None,
    ) -> None:
        self._name = name
        self._sources = sources

        (site_packages,) = site.getsitepackages()
        rootpath = substitute(rootpath or Path.cwd(), {SITE_ID: site_packages})
        self._rootpath = Path(rootpath)
        self._dependencies = dependencies or []

    @property
    def name(self) -> str:
        return self._name

    @property
    def root(self) -> Path:
        return self._rootpath

    @property
    def sources(self) -> list[str]:
        return self.collect_sources(self._sources)

    def collect_sources(self, sources: list[str | GlobDict]) -> list[str]:
        results: list[str] = []
        for item in sources:
            if isinstance(item, str):
                results.append(item)
            else:
                g = FileGlob(**item)
                with contextlib.chdir(self._rootpath):
                    results.extend(g.resolve())
        return results

    @classmethod
    def from_toml(cls, toml: dict[str, Any]) -> Self:
        return cls(**toml)

    @property
    def rules(self) -> Mapping[str, str]: ...

    def build_outputs(self) -> list[dict]: ...  # TODO: Make this typing more precise


class CCLibraryTarget(Target):
    def __init__(
        self,
        name: str,
        sources: list[str | GlobDict],
        rootpath: str | os.PathLike[str] | None = None,
        includes: list[str] | None = None,
        dependencies: list["CCLibraryTarget"] | None = None,
        defines: list[str] | None = None,
        flags: list[str] | None = None,
        ldflags: list[str] | None = None,
    ):
        super().__init__(name, sources, rootpath)

        self.includes = self.process_includes(includes or [])
        self.defines = self.process_defines(defines or [])
        self.dependencies = dependencies or []
        self.flags = self.process_flags(flags or [], str(self._rootpath))
        self.ldflags = self.process_flags(ldflags or [], str(self._rootpath))

    def process_defines(self, defines: list[str]) -> list[str]:
        return [d if d.startswith("-D") else "-D" + d for d in defines]

    # TODO: Use some kind of context object instead of just rootpath to interpolate flags
    # (important later when selecting flag sets based on compilation environment)
    def process_flags(self, flags: list[str], rootpath: str) -> list[str]:
        results: list[str] = []
        for f in flags:
            f = substitute(f, {ROOTPATH_ID: rootpath})
            results.append(str(f))
        return results

    def process_includes(self, includes: list[str]) -> list[str]:
        # TODO: Give third-party includes as -isystem based on a heuristic.
        results = []
        for i in includes:
            if i.startswith("@"):
                i = substitute(i, {PYTHON_HEADERS_ID: sysconfig.get_paths()["include"]})
            else:
                i = str(self.root / i)
            results.append(f"-I{i}")
        return results

    @property
    def rules(self) -> Mapping[str, str]:
        return MappingProxyType(
            {
                "cc": cc_compile,
                "cc_linkstatic": cc_linkstatic,
                "cc_linkshared": cc_linkshared,
            }
        )

    def build_outputs(self) -> list[dict]:
        _targets = []
        _objfiles: list[str] = []
        for src in self.sources:
            input = self.root / src
            output = Path(self.name) / src
            if output.suffix == ".h":
                # header files don't need compiling.
                continue

            variables: list[tuple[str, str | list[str]]] = [
                ("depfile", str(output.with_suffix(output.suffix + ".o.d"))),
                ("includes", self.includes),
                ("defines", self.defines),
                ("flags", self.flags),
            ]

            _objfile = str(output.with_suffix(output.suffix + ".o"))
            _objfiles.append(_objfile)
            target: dict[str, Any] = {
                "outputs": _objfile,
                "rule": "cc",
                "inputs": [str(input)],
                "variables": variables,
            }

            _targets.append(target)

        # TODO: Support shared linkage of libnanobind
        libname = "lib" + self.name + ".a"
        libtarget = {
            "outputs": libname,
            "rule": "cc-linkstatic",
            "inputs": _objfiles,
            "variables": [
                ("target_file", libname),
                ("pre_link", ":"),  # ":" is a placeholder for noop
                ("post_build", ":"),
                ("restat", "1"),
            ],
        }
        _targets.append(libtarget)

        return _targets


_BUILTIN_TARGETS: dict[str, type[Target]] = {"cc-library": CCLibraryTarget}

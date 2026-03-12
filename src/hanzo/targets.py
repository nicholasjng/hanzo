"""Ninja rule definitions in Python."""

import contextlib
import importlib.machinery
import operator
import os
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal, Required, Self, TypedDict, cast

from hanzo.rules import cc_compile, cc_linkshared, cc_linkstatic
from hanzo.settings import HanzoSettings, parse_hanzo_settings
from hanzo.utils import calculate_wheel_abi

settings = parse_hanzo_settings()

_SABI_MAP: dict[str, str] = {
    "cp3" + str(minor): hex((3 << 24) + (minor << 16)) for minor in range(1, 16)
}

Processor = Callable[[str, HanzoSettings], str]


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


def substitute(
    path: str | os.PathLike[str],
    settings: HanzoSettings,
    root: str | os.PathLike[str] | None = None,
) -> Path:
    # TODO: Get "root" into the settings somehow, or make a derivative context type.

    def _interpolate(matchobj: re.Match) -> str:
        # strip away the "@" marker in front.
        var = matchobj.group(0)[1:]
        if var == "rootpath":  # TODO: Make this less hacky
            if root is None:
                raise ValueError("could not substitute @rootpath")
            return str(root)
        getter = operator.attrgetter(var)
        return str(getter(settings))

    spath = str(path)
    attr_regex = re.compile(r"(@[a-zA-Z_][a-zA-Z0-9_.]*)")

    res = attr_regex.sub(_interpolate, spath)
    return Path(res)


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
        self._rootpath = substitute(rootpath or Path.cwd(), settings)
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

    def process_dependencies(self) -> None: ...

    @classmethod
    def from_toml(cls, toml: dict[str, Any]) -> Self:
        from hanzo.settings import get_build_graph

        build_graph = get_build_graph()
        deps: list[str] = toml.pop("dependencies", [])
        targets: list[Target] = []
        for dep in deps:
            targets.append(build_graph[dep])

        toml["dependencies"] = targets
        return cls(**toml)

    @property
    def rules(self) -> Mapping[str, str]: ...

    def build_outputs(self) -> list[dict]: ...  # TODO: Make this typing more precise


class CCLibraryTarget(Target):
    def __init__(
        self,
        name: str,
        sources: list[str | GlobDict],
        headers: list[str] | None = None,
        rootpath: str | os.PathLike[str] | None = None,
        includes: list[str] | None = None,
        dependencies: list[Target] | None = None,
        defines: list[str] | None = None,
        flags: list[str] | None = None,
        linkflags: list[str] | None = None,
        linkmode: Literal["static", "shared"] = "static",
        libname: str | None = None,
    ):
        super().__init__(name, sources, rootpath, dependencies)

        self.includes = self.process_includes(includes or [])
        self.headers = self.process_includes(headers or []) or self.includes
        self.defines = self.process_defines(defines or [])
        self.flags = self.process_flags(flags or [], str(self._rootpath))
        self.linkflags = self.process_flags(linkflags or [], str(self._rootpath))
        self.linkmode = linkmode
        self._libname = libname

    @property
    def libname(self) -> str:
        if self._libname is not None:
            return self._libname
        else:
            suffix = ".a" if self.linkmode == "static" else ".so"
            return "lib" + self.name + suffix

    def process_defines(self, defines: list[str]) -> list[str]:
        interpreter, abi = calculate_wheel_abi(settings, pure=False)
        if abi == "abi3":
            defines.append("-DPy_LIMITED_API=" + _SABI_MAP[interpreter])

        return [d if d.startswith("-D") else "-D" + d for d in defines]

    def process_dependencies(self) -> None:
        # only other CCLibraryTargets are allowed
        for dep in cast(list[Self], self._dependencies):
            self.includes += dep.headers
            self.defines += dep.defines
            self.linkflags += dep.linkflags
            self.flags += dep.flags

    # TODO: Use some kind of context object instead of just rootpath to interpolate flags
    # (important later when selecting flag sets based on compilation environment)
    def process_flags(self, flags: list[str], rootpath: str) -> list[str]:
        results: list[str] = []
        for f in flags:
            f = substitute(f, settings, self._rootpath)
            results.append(str(f))
        return results

    def process_includes(self, includes: list[str]) -> list[str]:
        # TODO: Give third-party includes as -isystem based on a heuristic.
        results = []
        for i in includes:
            if i.startswith("@"):
                i = substitute(i, settings, self._rootpath)
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
        self.process_dependencies()

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

        linkstatic = self.linkmode == "static"
        libnames = [dep.libname for dep in cast(list[Self], self._dependencies)]
        variables: list[tuple[str, str | list[str]]] = [
            ("target_file", self.libname),
            ("pre_link", ":"),  # ":" is a placeholder for noop
            ("post_build", ":"),
            ("restat", "1"),
        ]
        if not linkstatic:
            variables.append(("linkflags", self.linkflags))
            variables.append(("link_libraries", libnames))

        libtarget = {
            "outputs": self.libname,
            "rule": "cc-linkstatic" if linkstatic else "cc-linkshared",
            "inputs": _objfiles,
            "variables": variables,
            "implicit": libnames,
            "order_only": libnames,
        }

        _targets.append(libtarget)
        return _targets


class CCExtensionTarget(CCLibraryTarget):
    def __init__(
        self,
        name: str,
        sources: list[str | GlobDict],
        rootpath: str | os.PathLike[str] | None = None,
        includes: list[str] | None = None,
        headers: list[str] | None = None,
        dependencies: list[Target] | None = None,
        defines: list[str] | None = None,
        flags: list[str] | None = None,
        linkflags: list[str] | None = None,
        linkmode: Literal["static", "shared"] = "shared",
        libname: str | None = None,
    ):
        if linkmode != "shared":
            raise ValueError("Python extensions have to be shared libraries")

        super().__init__(
            name=name,
            sources=sources,
            headers=headers,
            rootpath=rootpath,
            includes=includes,
            dependencies=dependencies,
            defines=defines,
            flags=flags,
            linkflags=linkflags,
            linkmode=linkmode,
            libname=libname,
        )

    @property
    def libname(self) -> str:
        if self._libname is not None:
            return self._libname
        else:
            ext_suffixes = importlib.machinery.EXTENSION_SUFFIXES
            # TODO: Make decision based on hanzo extension abi settings.
            # first is non-abi3 extension, second is abi3.
            suffix = ext_suffixes[0] if False else ext_suffixes[1]
            return self.name + suffix


_BUILTIN_TARGETS: dict[str, type[Target]] = {
    "cc-library": CCLibraryTarget,
    "cc-extension": CCExtensionTarget,
}

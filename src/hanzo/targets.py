"""Ninja rule definitions in Python."""

import contextlib
import importlib.machinery
import operator
import os
import re
from collections.abc import Callable, Mapping
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal, Self, cast

from hanzo.rules import cc_compile, cc_linkshared, cc_linkstatic
from hanzo.settings import BuildConfig
from hanzo.types import Define, DefineDict, FileGlob, GlobDict, Include, IncludeDict

_SABI_MAP: dict[str, str] = {
    "cp3" + str(minor): hex((3 << 24) + (minor << 16)) for minor in range(1, 16)
}

Processor = Callable[[str, BuildConfig], str]


def substitute(
    path: str | os.PathLike[str],
    config: BuildConfig,
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
        return str(getter(config))

    spath = str(path)
    attr_regex = re.compile(r"(@[a-zA-Z_][a-zA-Z0-9_.]*)")

    res = attr_regex.sub(_interpolate, spath)
    return Path(res)


def collect(sources: list[str | GlobDict], cwd: str | os.PathLike[str]) -> list[str]:
    results: list[str] = []
    for item in sources:
        if isinstance(item, str):
            results.append(item)
        else:
            g = FileGlob(**item)
            with contextlib.chdir(cwd):
                results.extend(g.resolve())
    return results


class Target:
    def __init__(
        self,
        name: str,
        sources: list[str | GlobDict],
        config: BuildConfig,
        rootpath: str | os.PathLike[str] | None = None,
        dependencies: list["Target"] | None = None,
    ) -> None:
        self._name = name
        self._rootpath = substitute(rootpath or Path.cwd(), config)
        self._sources = collect(sources, self._rootpath)
        self._dependencies = dependencies or []
        self._config = config

    @property
    def name(self) -> str:
        return self._name

    @property
    def root(self) -> Path:
        return self._rootpath

    @property
    def sources(self) -> list[str]:
        return self._sources

    @property
    def config(self) -> BuildConfig:
        return self._config

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
        config: BuildConfig,
        rootpath: str | os.PathLike[str] | None = None,
        dependencies: list[Target] | None = None,
        features: list[str] | None = None,
        includes: list[str | IncludeDict] | None = None,
        defines: list[str | DefineDict] | None = None,
        flags: list[str] | None = None,
        linkflags: list[str] | None = None,
        linkmode: Literal["static", "shared"] = "static",
        libname: str | None = None,
    ):
        super().__init__(name, sources, config, rootpath, dependencies)

        # TODO: Move these methods out of class
        self.includes = self.process_includes(includes or [])
        self.defines = self.process_defines(defines or [])
        self.flags = self.process_flags(flags or [], str(self._rootpath))
        self.linkflags = self.process_flags(linkflags or [], str(self._rootpath))
        self.linkmode = linkmode

        if libname is not None:
            self._libname = libname
        else:
            suffix = ".a" if linkmode == "static" else ".so"
            self._libname = "lib" + self.name + suffix

    @property
    def libname(self) -> str:
        return self._libname

    @property
    def headers(self) -> list[Include]:
        return [inc for inc in self.includes if not inc.local]

    def process_defines(self, defines: list[str | DefineDict]) -> list[Define]:
        # # TODO: Pack this into a feature
        # interpreter, abi = calculate_wheel_abi(settings, pure=False)
        # if abi == "abi3":
        #     defines.append("-DPy_LIMITED_API=" + _SABI_MAP[interpreter])
        defs: list[Define] = []
        for define in defines:
            if isinstance(define, str):
                defs.append(Define.from_literal(define))
            else:
                defs.append(Define(**define))
        return defs

    def process_dependencies(self) -> None:
        # TODO: This has to be called on construction of the build graph.
        # only other CCLibraryTargets are allowed
        for dep in cast(list[Self], self._dependencies):
            self.includes += dep.headers
            self.defines += [_d for _d in dep.defines if not _d.local]
            self.linkflags += dep.linkflags
            self.flags += dep.flags

    def process_features(self) -> None:
        # only other CCLibraryTargets are allowed
        for dep in cast(list[Self], self._dependencies):
            self.includes += dep.headers
            self.defines += [_d for _d in dep.defines if not _d.local]
            self.linkflags += dep.linkflags
            self.flags += dep.flags

    # TODO: Use some kind of context object instead of just rootpath to interpolate flags
    # (important later when selecting flag sets based on compilation environment)
    def process_flags(self, flags: list[str], rootpath: str) -> list[str]:
        results: list[str] = []
        for f in flags:
            f = substitute(f, self.config, self.root)
            results.append(str(f))
        return results

    def process_includes(self, includes: list[str | IncludeDict]) -> list[Include]:
        results: list[Include] = []
        for inc in includes:
            if isinstance(inc, str):
                # TODO: Substitute, then prepend self.root if not absolute
                if inc.startswith("@"):
                    path = substitute(inc, self.config, self.root)
                else:
                    path = str(self.root / inc)
                results.append(Include(path))
            else:
                inc["path"] = str(self.root / inc["path"])
                results.append(Include(**inc))
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
                ("includes", list(map(str, self.includes))),
                ("defines", list(map(str, self.defines))),
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
        config: BuildConfig,
        rootpath: str | os.PathLike[str] | None = None,
        dependencies: list[Target] | None = None,
        includes: list[str | IncludeDict] | None = None,
        defines: list[str | DefineDict] | None = None,
        flags: list[str] | None = None,
        linkflags: list[str] | None = None,
        linkmode: Literal["static", "shared"] = "shared",
        libname: str | None = None,
    ):
        if linkmode != "shared":
            raise ValueError("Python extensions have to be shared libraries")

        if libname is None:
            ext_suffixes = importlib.machinery.EXTENSION_SUFFIXES
            # TODO: Make decision based on hanzo extension abi settings.
            # first is non-abi3 extension, second is abi3.
            suffix = ext_suffixes[0] if True else ext_suffixes[1]
            libname = name + suffix

        super().__init__(
            name=name,
            sources=sources,
            config=config,
            rootpath=rootpath,
            includes=includes,
            dependencies=dependencies,
            defines=defines,
            flags=flags,
            linkflags=linkflags,
            linkmode=linkmode,
            libname=libname,
        )


_BUILTIN_TARGETS: dict[str, type[Target]] = {
    "cc-library": CCLibraryTarget,
    "cc-extension": CCExtensionTarget,
}

"""Ninja rule definitions in Python."""

import importlib.machinery
import operator
import os
import re
from collections.abc import Mapping
from functools import cached_property
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal, Self, cast

from hanzo.features import CcFeature, Feature
from hanzo.rules import Rule
from hanzo.settings import BuildConfig
from hanzo.types import Define, DefineDict, FileGlob, GlobDict, Include, IncludeDict


def substitute(
    path: str | os.PathLike[str],
    config: BuildConfig,
    root: str | os.PathLike[str] | None = None,
) -> str:
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

    attr_regex = re.compile(r"(@[a-zA-Z_][a-zA-Z0-9_.]*)")
    return attr_regex.sub(_interpolate, Path(path).as_posix())


def collect(sources: list[str | GlobDict], cwd: str | os.PathLike[str]) -> list[str]:
    results: list[str] = []
    for item in sources:
        if isinstance(item, str):
            results.append(item)
        else:
            g = FileGlob(**item)
            results.extend(g.resolve(cwd))
    return results


class Target:
    COMPATIBLE_FEATURES: tuple[str, ...] = ()

    def __init__(
        self,
        name: str,
        sources: list[str | GlobDict],
        config: BuildConfig,
        rootpath: str | os.PathLike[str] | None = None,
    ) -> None:
        self._name = name
        self._rootpath = substitute(rootpath or Path.cwd(), config)
        self._sources = collect(sources, self._rootpath)
        self._dependencies: list[Target] = []
        self._config = config

    @property
    def name(self) -> str:
        return self._name

    @property
    def root(self) -> Path:
        return Path(self._rootpath)

    @property
    def sources(self) -> list[str]:
        return self._sources

    @property
    def config(self) -> BuildConfig:
        return self._config

    def add_dependency(self, dep: "Target") -> None: ...

    def add_feature(self, feature: Feature) -> None: ...

    @classmethod
    def from_toml(cls, toml: dict[str, Any], config: BuildConfig) -> Self: ...

    @property
    def rules(self) -> Mapping[str, Rule]: ...

    def build_outputs(self) -> list[dict]: ...  # TODO: Make this typing more precise


class CCLibraryTarget(Target):
    COMPATIBLE_FEATURES: tuple[str, ...] = ("cc-standard",)

    def __init__(
        self,
        name: str,
        sources: list[str | GlobDict],
        config: BuildConfig,
        rootpath: str | os.PathLike[str] | None = None,
        includes: list[Include] | None = None,
        defines: list[Define] | None = None,
        flags: list[str] | None = None,
        linkflags: list[str] | None = None,
        linkmode: Literal["static", "shared"] = "static",
        libname: str | None = None,
    ):
        super().__init__(name, sources, config, rootpath)

        self.includes = includes or []
        self.defines = defines or []
        self.flags = flags or []
        self.linkflags = linkflags or []
        self.linkmode = linkmode

        self._libname = libname

    @cached_property
    def libname(self) -> str:
        if self._libname is not None:
            return self._libname
        else:
            suffix = ".a" if self.linkmode == "static" else ".so"
            return "lib" + self.name + suffix

    @property
    def headers(self) -> list[Include]:
        return [inc for inc in self.includes if not inc.local]

    @classmethod
    def from_toml(cls, toml: dict[str, Any], config: BuildConfig) -> Self:
        def _expand_path(path: str | os.PathLike[str], root: str | os.PathLike[str]) -> str:
            root = Path(root)
            path = substitute(path, config, root)
            return str(path if Path(path).is_absolute() else root / path)

        parsed_config = toml.copy()

        rootpath: str | os.PathLike[str] = toml.get("rootpath", Path.cwd())
        rootpath = substitute(rootpath, config)
        raw_includes: list[str | IncludeDict] = toml.get("includes", [])
        raw_defines: list[str | DefineDict] = toml.get("defines", [])
        raw_flags: list[str] = toml.get("flags", [])
        raw_ldflags: list[str] = toml.get("linkflags", [])
        (
            includes,
            defines,
            flags,
            linkflags,
        ) = [], [], [], []

        for inc in raw_includes:
            if isinstance(inc, str):
                path = _expand_path(inc, rootpath)
                includes.append(Include(path))
            else:
                inc["path"] = _expand_path(inc["path"], rootpath)
                includes.append(Include(**inc))

        for _def in raw_defines:
            if isinstance(_def, str):
                defines.append(Define.from_literal(_def))
            else:
                defines.append(Define(**_def))

        for flag in raw_flags:
            parsed_flag = substitute(flag, config, rootpath)
            flags.append(parsed_flag)

        for flag in raw_ldflags:
            parsed_flag = substitute(flag, config, rootpath)
            linkflags.append(parsed_flag)

        parsed_config |= dict(includes=includes, defines=defines, flags=flags, linkflags=linkflags)
        inst = cls(**parsed_config)
        return inst

    def add_dependency(self, dep: Target) -> None:
        # TODO: If unable to restrict typing, go loud and throw errors here.
        # only other CCLibraryTargets are allowed
        if isinstance(dep, CCLibraryTarget):
            self._dependencies.append(dep)

            self.includes += dep.headers
            self.defines += [_d for _d in dep.defines if not _d.local]
            self.linkflags += dep.linkflags
            self.flags += dep.flags

    def add_feature(self, feature: Feature) -> None:
        if isinstance(feature, CcFeature):
            self.flags += feature.flags
            self.linkflags += feature.linkflags
            self.defines += feature.defines

    @property
    def rules(self) -> Mapping[str, Rule]:
        from hanzo.rules import cc_compile, cc_linkshared, cc_linkstatic

        return MappingProxyType(
            {rule.name: rule for rule in (cc_compile, cc_linkstatic, cc_linkshared)}
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
                ("depfile", str(output.with_suffix(".o.d"))),
                ("includes", list(map(str, self.includes))),
                ("defines", list(map(str, self.defines))),
                ("flags", self.flags),
            ]

            _objfile = str(output.with_suffix(".o"))
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
        includes: list[Include] | None = None,
        defines: list[Define] | None = None,
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
            config=config,
            rootpath=rootpath,
            includes=includes,
            defines=defines,
            flags=flags,
            linkflags=linkflags,
            linkmode=linkmode,
            libname=libname,
        )

    @cached_property
    def libname(self) -> str:
        if self._libname is not None:
            return self._libname
        else:
            uses_stable_abi = any(d.name == "Py_LIMITED_API" for d in self.defines)
            ext_suffixes = importlib.machinery.EXTENSION_SUFFIXES
            suffix = ext_suffixes[0] if not uses_stable_abi else ext_suffixes[1]
            return self.name + suffix


_BUILTIN_TARGETS: dict[str, type[Target]] = {
    "cc-library": CCLibraryTarget,
    "cc-extension": CCExtensionTarget,
}

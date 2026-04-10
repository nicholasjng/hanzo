import json
import os
import subprocess
import sys
import sysconfig
from enum import StrEnum, auto
from typing import Literal, Self, overload

from packaging.version import Version


class ToolchainNotFoundError(Exception):
    pass


class ToolchainType(StrEnum):
    CC = auto()
    PYTHON = auto()


class Toolchain:
    """A class representing a set of tools for a specific workload.

    Typically, a toolchain should contain all necessary tools to work with
    a specified set of source file types. For example, a C++ toolchain should
    be able to compile source files to object files, and link object files into
    a library.
    """

    def __init__(self, name: str):
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    def to_dict(self) -> dict[str, str]:
        return {k[1:]: v for k, v in self.__dict__.items()}


class CcToolchain(Toolchain):
    """An implementation of a C++ toolchain."""

    def __init__(
        self,
        name: str,
        compiler: str | os.PathLike[str],
        linker: str | os.PathLike[str],
        archiver: str | os.PathLike[str],
        ranlib: str | os.PathLike[str],
    ) -> None:
        super().__init__(name=name)

        self._compiler = str(compiler)
        self._linker = str(linker)
        self._archiver = str(archiver)
        self._ranlib = str(ranlib)

    @property
    def name(self) -> str:
        return self._name

    @property
    def compiler(self) -> str:
        return self._compiler

    @property
    def linker(self) -> str:
        return self._linker

    @property
    def archiver(self) -> str:
        return self._archiver

    @property
    def ranlib(self) -> str:
        return self._ranlib

    @property
    def supported_platforms(self) -> tuple[str, ...]:
        return ("macos",)


class PythonToolchain(Toolchain):
    """A Python toolchain."""

    def __init__(
        self,
        name: str,
        executable: str,
    ):
        super().__init__(name=name)

        self._executable = executable

        if self._executable == sys.executable:
            paths = sysconfig.get_paths()
            version = sysconfig.get_config_var("py_version")
        else:
            paths = json.loads(
                subprocess.check_output(  # noqa: S603
                    [self._executable, "-c", "import sysconfig; print(sysconfig.get_paths())"],
                    encoding="utf-8",
                ).replace("'", '"')
            )
            version = subprocess.check_output(  # noqa: S603
                [
                    self._executable,
                    "-c",
                    "import sysconfig; print(sysconfig.get_config_var('py_version'))",
                ],
                encoding="utf-8",
            )

        self._include = paths["include"]
        self._libdir = paths["stdlib"]
        self._site = paths["platlib"]
        self._version = Version(version)

    @classmethod
    def current(cls) -> Self:
        return cls(name="current", executable=sys.executable)

    @property
    def executable(self) -> str:
        return self._executable

    @property
    def include(self) -> str:
        return self._include

    @property
    def libdir(self) -> str:
        return self._libdir

    @property
    def site(self) -> str:
        return self._site

    @property
    def version(self) -> Version:
        return self._version

    # @property
    # def ext_suffix(self) -> str:
    #     return self._ext_suffix


CcHostToolchain = CcToolchain(
    name="host",
    compiler="/usr/bin/c++",
    linker="/usr/bin/c++",
    archiver="/usr/bin/ar rcs",
    ranlib="/usr/bin/ranlib",
)

PythonCurrentInterpreterToolchain = PythonToolchain.current()


_toolchains: dict[str, Toolchain] = {
    "cc-host": CcHostToolchain,
    "python-current": PythonCurrentInterpreterToolchain,
}


@overload
def get_toolchain(name: str, typ: Literal[ToolchainType.CC]) -> CcToolchain: ...


@overload
def get_toolchain(name: str, typ: Literal[ToolchainType.PYTHON]) -> PythonToolchain: ...


def get_toolchain(name: str, typ: ToolchainType) -> Toolchain:
    key = f"{typ}-{name}"
    try:
        return _toolchains[key]
    except KeyError:
        raise ToolchainNotFoundError(f"no {typ} toolchain named {name!r}") from None


__all__ = [
    "Toolchain",
    "CcToolchain",
    "PythonToolchain",
    "CcHostToolchain",
    "PythonCurrentInterpreterToolchain",
    "get_toolchain",
]

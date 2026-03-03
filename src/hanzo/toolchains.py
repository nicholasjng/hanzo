import os


class Toolchain:
    """A class representing a set of tools for a specific workload.

    Typically, a toolchain should contain all necessary tools to work with
    a specified set of source file types. For example, a C++ toolchain should
    be able to compile source files to object files, and link object files into
    a library.
    """


class CppToolchain(Toolchain):
    """An implementation of a C++ toolchain."""

    def __init__(
        self,
        name: str,
        compiler: str | os.PathLike[str],
        linker: str | os.PathLike[str],
        archiver: str | os.PathLike[str],
        ranlib: str | os.PathLike[str],
    ) -> None:
        self._name = name
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

    def to_dict(self) -> dict[str, str]:
        # strip leading underscore off all private field names.
        return {k[1:]: v for k, v in self.__dict__.items()}


CppHostToolchain = CppToolchain(
    name="host",
    compiler="/usr/bin/c++",
    linker="/usr/bin/c++",
    archiver="/usr/bin/ar rcs",
    ranlib="/usr/bin/ranlib",
)

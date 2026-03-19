import contextlib
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Required, Self, TypedDict


class GlobDict(TypedDict, total=False):
    include: Required[list[str]]
    exclude: list[str]
    allow_empty: bool


@dataclass(frozen=True)
class FileGlob:
    include: list[str]
    exclude: list[str] = field(default_factory=list)
    allow_empty: bool = False

    def resolve(self, directory: str | os.PathLike[str]) -> list[str]:
        with contextlib.chdir(directory):
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


class IncludeDict(TypedDict, total=False):
    path: Required[str]
    system: bool
    local: bool


@dataclass(frozen=True)
class Include:
    path: str | os.PathLike[str]
    system: bool = False
    local: bool = False

    def __str__(self) -> str:
        prefix = "-isystem" if self.system else "-I"
        return prefix + Path(self.path).as_posix()


class DefineDict(TypedDict, total=False):
    name: Required[str]
    value: str | int | bool | None
    local: bool


@dataclass(frozen=True)
class Define:
    name: str
    value: str | int | bool | None = None
    local: bool = False

    @classmethod
    def from_literal(cls, lit: str) -> Self:
        if lit.startswith("-D"):
            lit = lit[2:]

        try:
            name, val = lit.split("=", 1)
        except ValueError:
            # true-ish define like -DNDEBUG
            name, val = lit, True
        # if you want a local define, use a TOML struct.
        return cls(name, val)

    def __str__(self) -> str:
        sdefine = "-D" + self.name
        if isinstance(self.value, bool | None):
            return sdefine
        else:
            return sdefine + "=" + str(self.value)


__all__ = [
    "GlobDict",
    "IncludeDict",
    "DefineDict",
    "FileGlob",
    "Include",
    "Define",
]

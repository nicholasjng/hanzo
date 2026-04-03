"""Ninja rule definitions in Python."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Self

if TYPE_CHECKING:
    from hanzo.toolchains import Toolchain


@dataclass(unsafe_hash=True)
class Rule:
    name: str
    command: str
    description: str | None = field(default=None)
    depfile: str | None = field(default=None)
    deps: str | None = field(default=None)
    restat: str | None = field(default=None)

    def __str__(self):
        lines = [f"rule {self.name}"]
        if self.depfile:
            lines.append(f"  depfile = {self.depfile}")
        if self.deps:
            lines.append(f"  deps = {self.deps}")
        if self.description:
            lines.append(f"  description = {self.description}")
        if self.restat:
            lines.append(f"  restat = {self.restat}")
        lines.append(f"  command = {self.command}")
        return "\n".join(lines)

    def interpolate(self, toolchain: Toolchain) -> Self:
        try:
            cmd = self.command.format(**toolchain.to_dict())
            self.command = cmd
            return self
        except KeyError as e:
            raise KeyError(f"no tool {e} on toolchain {toolchain.name!r}") from None

    def commandline(self, variables: dict[str, str | list[str]]) -> str:
        def replace(m: re.Match) -> str:
            val = variables.get(m.group(1), "")
            if isinstance(val, list):
                return " ".join(val)
            return val

        cmd = re.sub(r"\$(\w+)", replace, self.command)
        return cmd.strip().strip("&").strip()


cc_compile = Rule(
    name="cc",
    command="""{compiler} $defines $includes $flags -MD -MT $out -MF $depfile -o $out -c $in""",
    description="Building C++ object $out",
    depfile="$depfile",
    deps="gcc",
)

cc_linkstatic = Rule(
    name="cc-linkstatic",
    command="""$pre_link && rm -f $target_file && {archiver} $target_file $linkflags $in && {ranlib} $target_file && touch $target_file && $post_build""",
    description="Linking C++ static library $target_file",
    restat="$restat",
)

cc_linkshared = Rule(
    name="cc-linkshared",
    command="""$pre_link && {compiler} $cflags $archflags $linkflags -o $target_file $in $link_path $link_libraries && $post_build""",
    description="Linking C++ shared module $target_file",
    restat="$restat",
)

from __future__ import annotations

import sysconfig
from dataclasses import dataclass

from hanzo.utils import to_snakecase


@dataclass(frozen=True)
class Platform:
    system: str
    os_version: str | None
    arch: str

    def __str__(self) -> str:
        if self.os_version is not None:
            return to_snakecase(f"{self.system}-{self.os_version}-{self.arch}")
        return to_snakecase(f"{self.system}-{self.arch}")

    @classmethod
    def parse(cls, s: str) -> Platform:
        parts = s.split("-")
        if len(parts) == 3:
            system, os_version, arch = parts
        elif len(parts) == 2:
            system, arch = parts
            os_version = None
        else:
            raise ValueError(f"invalid platform string: {s!r}")
        return cls(system=system, os_version=os_version, arch=arch)

    @classmethod
    def host(cls) -> Platform:
        return cls.parse(sysconfig.get_platform())

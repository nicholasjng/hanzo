from __future__ import annotations

import os
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

        # prefer MACOSX_DEPLOYMENT_TARGET over actual macOS version.
        if system.startswith("macos"):
            macos_deployment_target = os.getenv("MACOSX_DEPLOYMENT_TARGET")
            if macos_deployment_target is not None:
                os_version = macos_deployment_target

        return cls(system=system, os_version=os_version, arch=arch)

    @classmethod
    def host(cls) -> Platform:
        return cls.parse(sysconfig.get_platform())

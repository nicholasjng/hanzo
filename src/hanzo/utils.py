from __future__ import annotations

import dataclasses
import sysconfig
from typing import TYPE_CHECKING

from packaging.specifiers import SpecifierSet
from packaging.tags import Tag

if TYPE_CHECKING:
    from hanzo.settings import BuildConfig, HanzoSettings


def to_snakecase(s: str) -> str:
    return s.replace("-", "_").replace(".", "_")


def calculate_wheel_tag(settings: HanzoSettings, config: BuildConfig, root_is_purelib: bool) -> Tag:
    if root_is_purelib:
        return Tag("py3", "none", "any")

    current_interpreter = "cp" + sysconfig.get_config_var("py_version_nodot")
    current_python_version = sysconfig.get_config_var("py_version")
    stable_abi = settings.wheel.stable_abi

    interpreter = current_interpreter
    abi = current_interpreter

    if stable_abi is not None:
        stable_abi_spec = SpecifierSet(stable_abi)
        if len(stable_abi_spec) > 1:
            raise ValueError(f"stable ABI must be a single specifier, got {stable_abi!r}")
        if current_python_version in stable_abi_spec:
            (spec,) = stable_abi_spec
            if spec.operator != ">=":
                raise ValueError(
                    f"stable ABI specifier must use '>=' operator, got {spec.operator!r}"
                )
            # TODO: Clean this up to allow prereleases
            interpreter = "cp" + spec.version.replace(".", "")
            abi = "abi3"

    platform = config.platform
    if platform.os_version is None:
        if platform.system == "macosx":
            guessed_macver = guess_minimum_macver(settings, platform.arch)
            platform = dataclasses.replace(platform, os_version=guessed_macver)

    return Tag(interpreter, abi, str(platform))


def guess_minimum_macver(settings: HanzoSettings, arch: str) -> str:
    if arch not in ("arm64", "x86_64", "universal2"):
        raise ValueError(f"unsupported macOS architecture: {arch!r}")
    if arch == "arm64":
        # Apple Silicon only runs macOS>=11.0.
        return "11.0"
    if settings.cc.standard == "c++17":
        # C++17 support is only available starting in macOS 10.15 ("Catalina").
        return "10.15"
    # best-effort guess.
    return "10.13"


__all__ = ["calculate_wheel_tag", "guess_minimum_macver", "to_snakecase"]

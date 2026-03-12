import functools
import tomllib
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Self, cast

from packaging.metadata import Metadata, RawMetadata

from hanzo.constants import DEFAULT_CC_TOOLCHAIN_NAME, DEFAULT_PY_TOOLCHAIN_NAME, METADATA_VERSION
from hanzo.toolchains import (
    CcToolchain,
    PythonToolchain,
    ToolchainType,
    get_toolchain,
)

if TYPE_CHECKING:
    from hanzo.targets import Target

_build_graph: dict[str, "Target"] = {}


def get_build_graph() -> Mapping[str, "Target"]:
    return MappingProxyType(_build_graph)


class HanzoSettings:
    _cc: CcToolchain
    _py: PythonToolchain
    _features: list[str]

    stable_abi: str | None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Self:
        """Hydrates the class with toolchains from PEP517 config settings."""
        ins = cls()
        # TODO: Parse these config settings with argparse or similar
        cc_toolchain_name: str = d.get("--cc-toolchain", DEFAULT_CC_TOOLCHAIN_NAME)
        py_toolchain_name: str = d.get("--python-toolchain", DEFAULT_PY_TOOLCHAIN_NAME)
        features: list[str] = d.get("--features", [])
        stable_abi: str | None = d.get("stable-abi", None)

        # assigns private instance variables with parsed values.
        ins._cc = get_toolchain(cc_toolchain_name, ToolchainType.CC)
        ins._py = get_toolchain(py_toolchain_name, ToolchainType.PYTHON)
        ins._features = features
        ins.stable_abi = stable_abi
        return ins

    @property
    def cc(self) -> CcToolchain:
        return self._cc

    @property
    def python(self) -> PythonToolchain:
        return self._py

    @property
    def features(self) -> list[str]:
        return self._features


@functools.lru_cache(maxsize=1)
def parse_pyproject() -> dict[str, Any]:
    # in a wheel build, cwd is the project root.
    pyproject_path = Path("pyproject.toml")
    with open(pyproject_path, "rb") as pyproj:
        pyproject = tomllib.load(pyproj)
    return pyproject


def parse_project_metadata() -> Metadata:
    from packaging.metadata import _EMAIL_TO_RAW_MAPPING

    pyproject = parse_pyproject()
    project_info = pyproject["project"]

    if "metadata-version" not in project_info:
        project_info["metadata-version"] = METADATA_VERSION
    # TODO: Error handling in line with metadata
    project_info: RawMetadata = cast(
        RawMetadata, {_EMAIL_TO_RAW_MAPPING[k]: v for k, v in project_info.items()}
    )
    return Metadata.from_raw(project_info)


def parse_hanzo_settings(config_settings: dict[str, str] | None = None) -> HanzoSettings:
    pyproject = parse_pyproject()
    # TODO: Convert this into a typed settings class
    hanzo_info = pyproject.get("tool", {}).get("hanzo", {})
    hanzo_info |= config_settings or {}
    return HanzoSettings.from_dict(hanzo_info)


@functools.lru_cache(maxsize=1)
def load_extensions() -> Mapping[str, "Target"]:
    pyproject = parse_pyproject()
    # TODO: Should this move into the settings?
    exts: dict[str, dict[str, Any]] = pyproject.get("tool", {}).get("hanzo", {}).get("targets", {})

    from hanzo.targets import _BUILTIN_TARGETS

    for name, config in exts.items():
        config["name"] = name
        target_type: str = config.pop("type")
        _build_graph[name] = _BUILTIN_TARGETS[target_type].from_toml(config)

    return get_build_graph()

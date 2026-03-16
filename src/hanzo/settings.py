import functools
import tomllib
from collections.abc import Mapping
from dataclasses import MISSING, dataclass, field, fields, is_dataclass, replace
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Self, cast

from packaging.metadata import Metadata, RawMetadata

from hanzo.constants import DEFAULT_CC_TOOLCHAIN_NAME, DEFAULT_PY_TOOLCHAIN_NAME, METADATA_VERSION
from hanzo.features import Feature, get_feature
from hanzo.toolchains import (
    CcToolchain,
    PythonToolchain,
    ToolchainType,
    get_toolchain,
)
from hanzo.utils import to_snakecase

if TYPE_CHECKING:
    from hanzo.targets import Target

_build_graph: dict[str, "Target"] = {}


def get_build_graph() -> Mapping[str, "Target"]:
    return MappingProxyType(_build_graph)


@dataclass
class SdistSettings:
    pass


@dataclass
class WheelSettings:
    stable_abi: str | None = None


@dataclass
class PythonSettings:
    pass


@dataclass
class CcSettings:
    export_compile_commands: bool = False


@dataclass
class HanzoSettings:
    sdist: SdistSettings = field(default_factory=SdistSettings)
    wheel: WheelSettings = field(default_factory=WheelSettings)
    python: PythonSettings = field(default_factory=PythonSettings)
    cc: CcSettings = field(default_factory=CcSettings)


class BuildConfig:
    _cc: CcToolchain
    _python: PythonToolchain
    _features: set[Feature]

    @classmethod
    def from_settings(cls, config_settings: dict[str, Any]) -> Self:
        """Hydrates the class with PEP517 config settings."""
        ins = cls()
        # TODO: Parse these config settings with argparse or similar
        cc_toolchain_name: str = config_settings.get("--cc-toolchain", DEFAULT_CC_TOOLCHAIN_NAME)
        py_toolchain_name: str = config_settings.get(
            "--python-toolchain", DEFAULT_PY_TOOLCHAIN_NAME
        )

        features: set[Feature] = {
            get_feature(name)(name) for name in config_settings.get("--features", [])
        }

        # assigns private instance variables with parsed values.
        ins._cc = get_toolchain(cc_toolchain_name, ToolchainType.CC)
        ins._python = get_toolchain(py_toolchain_name, ToolchainType.PYTHON)
        ins._features = features
        return ins

    @property
    def cc(self) -> CcToolchain:
        return self._cc

    @property
    def python(self) -> PythonToolchain:
        return self._python

    @property
    def features(self) -> set[Feature]:
        return self._features

    def add_builtin_features(settings: HanzoSettings) -> None:
        pass


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


def parse_hanzo_settings() -> HanzoSettings:
    pyproject = parse_pyproject()
    hanzo_info = pyproject.get("tool", {}).get("hanzo", {})

    for field_ in fields(HanzoSettings):
        block = hanzo_info.pop(field_.name, {})
        cfg = block
        if is_dataclass(field_.type):
            if field_.default_factory is not MISSING:
                cfg = field_.default_factory()
                if is_dataclass(cfg):
                    cfg = replace(cfg, **block)
                continue
        elif isinstance(field_.type, type):
            _normblock = {to_snakecase(k): v for k, v in block.items()}
            cfg = field_.type(**_normblock)

        hanzo_info[field_.name] = cfg

    return HanzoSettings(hanzo_info)


@functools.lru_cache(maxsize=1)
def load_extensions(config: BuildConfig) -> Mapping[str, "Target"]:
    pyproject = parse_pyproject()
    # TODO: Should this move into the settings?
    exts: dict[str, dict[str, Any]] = pyproject.get("tool", {}).get("hanzo", {}).get("targets", {})

    from hanzo.targets import _BUILTIN_TARGETS

    for name, _struct in exts.items():
        _struct["name"] = name
        target_type: str = _struct.pop("type")
        _struct["config"] = config
        _build_graph[name] = _BUILTIN_TARGETS[target_type].from_toml(_struct)

    return get_build_graph()

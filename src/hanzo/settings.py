import functools
import tomllib
from collections.abc import Mapping
from dataclasses import MISSING, dataclass, field, fields, is_dataclass, replace
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Literal, Self, overload

from pyproject_metadata import StandardMetadata

from hanzo.constants import (
    DEFAULT_BUILD_DIR,
    DEFAULT_CC_TOOLCHAIN_NAME,
    DEFAULT_PY_TOOLCHAIN_NAME,
    DEFAULT_SOURCE_EXTENSIONS,
    METADATA_VERSION,
)
from hanzo.features import Feature, get_feature
from hanzo.platform import Platform
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


@overload
def ensure_scalar_setting(settings: dict[str, str | list[str]], key: str, default: str) -> str: ...


@overload
def ensure_scalar_setting(
    settings: dict[str, str | list[str]], key: str, default: Literal[None] = None
) -> str | None: ...


def ensure_scalar_setting(
    settings: dict[str, str | list[str]], key: str, default: str | None = None
) -> str | None:
    """Return a scalar value for a given key in PEP517 config settings."""
    val = settings.get(key, default)
    if isinstance(val, list):
        raise ValueError(f"got multiple values for {key!r}")
    return val


@dataclass
class SdistSettings:
    pass


@dataclass
class WheelSettings:
    stable_abi: str | None = None
    sources: frozenset[str] = field(default_factory=lambda: DEFAULT_SOURCE_EXTENSIONS)
    data: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        if not isinstance(self.sources, frozenset):
            self.sources = frozenset(self.sources)
        if not isinstance(self.data, frozenset):
            self.data = frozenset(self.data)


@dataclass
class PythonSettings:
    pass


@dataclass
class CcSettings:
    standard: str = "c++17"
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
    _platform: Platform
    _features: dict[str, Feature]
    _build_dir: Path
    _clean: bool

    @classmethod
    def from_settings(cls, config_settings: dict[str, str | list[str]]) -> Self:
        """Hydrates the class with PEP517 config settings."""
        ins = cls()
        # TODO: Parse these config settings with argparse or similar
        cc_toolchain_name: str = ensure_scalar_setting(
            config_settings, "--cc-toolchain", DEFAULT_CC_TOOLCHAIN_NAME
        )
        py_toolchain_name: str = ensure_scalar_setting(
            config_settings, "--python-toolchain", DEFAULT_PY_TOOLCHAIN_NAME
        )

        # assigns private instance variables with parsed values.
        ins._cc = get_toolchain(cc_toolchain_name, ToolchainType.CC)
        ins._python = get_toolchain(py_toolchain_name, ToolchainType.PYTHON)

        features: dict[str, Feature] = {
            name: get_feature(name)(name) for name in config_settings.get("--enable-feature", [])
        }

        # and build features.
        ins._features = features

        # platform selection by parsing the input string.
        platform_str = ensure_scalar_setting(config_settings, "--platform")
        if platform_str is None:
            ins._platform = Platform.host()
        else:
            ins._platform = Platform.parse(platform_str)

        build_dir = ensure_scalar_setting(config_settings, "--build-dir", DEFAULT_BUILD_DIR)
        ins._build_dir = Path(build_dir)

        # run a ninja -t clean before building.
        ins._clean = "--clean" in config_settings

        return ins

    @property
    def clean(self) -> bool:
        return self._clean

    @property
    def build_dir(self) -> Path:
        return self._build_dir

    @property
    def cc(self) -> CcToolchain:
        return self._cc

    @property
    def python(self) -> PythonToolchain:
        return self._python

    @property
    def platform(self) -> Platform:
        return self._platform

    @property
    def features(self) -> Mapping[str, Feature]:
        return MappingProxyType(self._features)

    def add_builtin_features(self, settings: HanzoSettings) -> None:
        from hanzo.features import CcStandard

        standard_feature = CcStandard(settings.cc.standard)
        self._features[standard_feature.name] = standard_feature

        if settings.wheel.stable_abi is not None:
            from hanzo.features import StableABI

            sabi_feature = StableABI(settings.wheel.stable_abi)
            if self.python.version in sabi_feature.version_range:
                self._features[sabi_feature.name] = sabi_feature


@functools.lru_cache(maxsize=1)
def parse_pyproject() -> dict[str, Any]:
    # in a wheel build, cwd is the project root.
    pyproject_path = Path("pyproject.toml")
    with open(pyproject_path, "rb") as pyproj:
        pyproject = tomllib.load(pyproj)
    return pyproject


def parse_project_metadata() -> StandardMetadata:
    pyproject = parse_pyproject()
    metadata = StandardMetadata.from_pyproject(
        pyproject, allow_extra_keys=False, all_errors=True, metadata_version=METADATA_VERSION
    )
    return metadata


def parse_hanzo_settings() -> HanzoSettings:
    pyproject = parse_pyproject()
    hanzo_info = pyproject.get("tool", {}).get("hanzo", {})

    parsed_settings: dict[str, Any] = {}

    for field_ in fields(HanzoSettings):
        block = {to_snakecase(k): v for k, v in hanzo_info.pop(field_.name, {}).items()}
        cfg = block
        if is_dataclass(field_.type):
            if field_.default_factory is not MISSING:
                cfg = field_.default_factory()
                if is_dataclass(cfg):
                    cfg = replace(cfg, **block)
        elif isinstance(field_.type, type):
            cfg = field_.type(**block)

        parsed_settings[field_.name] = cfg

    return HanzoSettings(**parsed_settings)


@functools.lru_cache(maxsize=1)
def load_extensions(config: BuildConfig) -> Mapping[str, "Target"]:
    pyproject = parse_pyproject()
    exts: dict[str, dict[str, Any]] = pyproject.get("tool", {}).get("hanzo", {}).get("targets", {})

    from hanzo.targets import _BUILTIN_TARGETS

    for name, _struct in exts.items():
        _struct["name"] = name
        # remove pyproject keys responsible for build graph construction...
        target_type: str = _struct.pop("type")
        deps: list[str] = _struct.pop("dependencies", [])
        feature_names: list[str] = _struct.pop("features", [])

        target = _BUILTIN_TARGETS[target_type].from_toml(_struct, config)
        for dep in deps:
            target.add_dependency(_build_graph[dep])

        for fname in feature_names:
            if fname in config.features:
                print(f"hanzo: Adding feature {fname!r} to target {target.name!r}.")
                feature = config.features[fname]
                target.add_feature(feature)

        for fname in target.COMPATIBLE_FEATURES:
            if fname in config.features:
                print(f"hanzo: Adding feature {fname!r} to target {target.name!r}.")
                target.add_feature(config.features[fname])

        _build_graph[name] = target

    return get_build_graph()

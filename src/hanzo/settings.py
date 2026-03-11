import functools
import tomllib
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, cast

from packaging.metadata import Metadata, RawMetadata

from hanzo.constants import METADATA_VERSION

if TYPE_CHECKING:
    from hanzo.targets import Target

_build_graph: dict[str, "Target"] = {}


def get_build_graph() -> Mapping[str, "Target"]:
    return MappingProxyType(_build_graph)


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


def parse_hanzo_settings() -> dict[str, Any]:
    pyproject = parse_pyproject()
    # TODO: Convert this into a typed settings class
    hanzo_info = pyproject.get("tool", {}).get("hanzo", {})
    return hanzo_info


@functools.lru_cache(maxsize=1)
def load_extensions() -> Mapping[str, "Target"]:
    hanzo_settings = parse_hanzo_settings()
    exts: dict[str, dict[str, Any]] = hanzo_settings.get("targets", {})

    from hanzo.targets import _BUILTIN_TARGETS

    for name, config in exts.items():
        config["name"] = name
        target_type: str = config.pop("type")
        _build_graph[name] = _BUILTIN_TARGETS[target_type].from_toml(config)

    return get_build_graph()

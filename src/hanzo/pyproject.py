import functools
import tomllib
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

from packaging.metadata import Metadata

if TYPE_CHECKING:
    from hanzo.targets import Target

_METADATA_VERSION = "2.5"

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
    pyproject = parse_pyproject()
    project_info = pyproject["project"]
    project_info["metadata_version"] = _METADATA_VERSION
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

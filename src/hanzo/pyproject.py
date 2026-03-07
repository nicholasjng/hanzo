import functools
import tomllib
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType
from typing import Any, TypedDict

from packaging.utils import NormalizedName, canonicalize_name
from packaging.version import Version

from hanzo.build_graph import get_build_graph
from hanzo.targets import _BUILTIN_TARGETS, Target


class ProjectSettings(TypedDict):
    name: NormalizedName
    version: Version


@functools.lru_cache(maxsize=1)
def parse_pyproject() -> dict[str, Any]:
    # in a wheel build, cwd is the project root.
    pyproject_path = Path("pyproject.toml")
    with open(pyproject_path, "rb") as pyproj:
        pyproject = tomllib.load(pyproj)
    return pyproject


def parse_project_settings() -> ProjectSettings:
    pyproject = parse_pyproject()
    project_info = pyproject["project"]
    project_settings: ProjectSettings = {
        "name": canonicalize_name(project_info["name"], validate=True),
        "version": Version(project_info["version"]),
    }
    return project_settings


def parse_hanzo_settings() -> dict[str, Any]:
    pyproject = parse_pyproject()
    hanzo_info = pyproject.get("tool", {}).get("hanzo", {})
    return hanzo_info


@functools.lru_cache(maxsize=1)
def load_extensions() -> Mapping[str, Target]:
    hanzo_settings = parse_hanzo_settings()
    exts: dict[str, dict[str, Any]] = hanzo_settings.get("targets", {})

    build_graph = get_build_graph()
    for name, config in exts.items():
        config["name"] = name
        target_type: str = config.pop("type")
        build_graph[name] = _BUILTIN_TARGETS[target_type].from_toml(config)

    return MappingProxyType(build_graph)

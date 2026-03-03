import functools
import tomllib
from pathlib import Path
from typing import TypedDict, Any

from packaging.utils import NormalizedName, canonicalize_name
from packaging.version import Version


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


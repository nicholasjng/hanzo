import os
import sysconfig
from pathlib import Path

from packaging.tags import Tag

from .pyproject import parse_project_settings
from .wheelfile import WheelWriter

BUILD_DIRNAME = "build"
WHEEL_FILENAME = "{name}-{version}-{tag}.whl"


def get_extension_modules() -> list[str]:
    return []


# PEP 517 hooks


def build_wheel(
    wheel_directory: str | os.PathLike[str],
    config_settings: dict[str, str] | None = None,
    metadata_directory: str | os.PathLike[str] | None = None,
) -> str:
    print(f"{wheel_directory = }")
    print(f"{config_settings = }")
    print(f"{metadata_directory = }")
    settings = parse_project_settings()
    print(f"{settings = }")

    ext_modules = get_extension_modules()
    root_is_purelib = len(ext_modules) == 0

    if not root_is_purelib:
        # TODO: Support pypy and other flavors
        interpreter = "cp" + sysconfig.get_config_var("py_version_nodot")
        abi = "abi3"  # TODO: Calculate instead of hardcoding
        _platform = sysconfig.get_platform()
        _platform = _platform.replace(".", "_").replace("-", "_")
    else:
        interpreter = "py3"
        abi = "none"
        _platform = "any"

    tag = Tag(interpreter, abi, _platform)

    wheel_directory = Path(wheel_directory)
    build_dir = Path.cwd() / BUILD_DIRNAME
    wheel_file = wheel_directory / WHEEL_FILENAME.format(
        name=settings["name"],
        version=settings["version"],
        tag=tag,
    )

    build_dir.mkdir(exist_ok=True)
    with WheelWriter(wheel_file, generator="hanzo", root_is_purelib=root_is_purelib) as wheel:
        project_name = Path(settings["name"])
        # step 1: write dist-info
        wheel.write_metadata([])
        for dirpath, dirnames, files in os.walk("src"):
            for f in files:
                wheel.write_file(project_name / f, Path(dirpath) / f)

    return wheel_file.name


def build_sdist(
    sdist_directory: str | os.PathLike[str],
    config_settings: dict[str, str] | None = None,
) -> str: ...


def get_requires_for_build_wheel(
    config_settings: dict[str, str] | None = None,
) -> list[str]:
    return []


def get_requires_for_build_sdist(
    config_settings: dict[str, str] | None = None,
) -> list[str]:
    return []


def prepare_metadata_for_build_wheel(
    metadata_directory: str | os.PathLike[str],
    config_settings: dict[str, str] | None = None,
) -> None: ...


# PEP 660 editable hooks


def build_editable(
    wheel_directory: str | os.PathLike[str],
    config_settings: dict[str, str] | None = None,
    metadata_directory: str | os.PathLike[str] | None = None,
) -> str: ...


def get_requires_for_build_editable(
    config_settings: dict[str, str] | None = None,
) -> list[str]: ...


def prepare_metadata_for_build_editable(
    metadata_directory: str | os.PathLike[str],
    config_settings: dict[str, str] | None = None,
) -> None: ...

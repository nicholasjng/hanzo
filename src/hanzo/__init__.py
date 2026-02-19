import os
from pathlib import Path

BUILD_DIRNAME = "build"
WHEEL_FILENAME = "{project_name}-0.1.0-py3-none-any.whl"

# PEP 517 hooks


def build_wheel(
    wheel_directory: str | os.PathLike[str],
    config_settings: dict[str, str] | None = None,
    metadata_directory: str | os.PathLike[str] | None = None,
) -> str:
    project_name: str = (config_settings or {}).get("project_name", "hello")
    wheel_directory = Path(wheel_directory)
    project_dir = wheel_directory.parent
    build_dir = project_dir / BUILD_DIRNAME
    wheel_file = wheel_directory / WHEEL_FILENAME.format(project_name=project_name)

    from .wheelfile import WheelWriter

    build_dir.mkdir(exist_ok=True)
    with WheelWriter(wheel_file, generator="hanzo") as wheel:
        # step 1: write dist-info
        wheel.write_metadata([])
        for dirpath, dirnames, files in (project_dir / "src").walk():
            for f in files:
                print(dirpath / f)
                wheel.write_file(Path(project_name) / f, dirpath / f)

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

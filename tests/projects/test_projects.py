"""Integration tests: build each sub-project with the build API, then run its
entrypoint and check the captured output against expectations."""

import os
import subprocess
import sys
from pathlib import Path

import build
import build.env
import pytest

PROJECTS_DIR = Path(__file__).parent
HANZO_DIR: Path = PROJECTS_DIR.parents[1]

# Maps project directory name -> (module, callable, expected stdout)
PROJECT_EXPECTATIONS: dict[str, tuple[str, str, str]] = {
    "hello": ("hello", "say_hello", "Hello world!"),
    "hello_cc": ("hello_cc", "say_hello", "Hello from C++!"),
}

_PYTHON_BIN = "Scripts/python.exe" if sys.platform == "win32" else "bin/python"


def _build_wheel(project_dir: Path, dist_dir: Path) -> Path:
    """Build a wheel for *project_dir* using a uv-backed isolated environment.

    Prints return code and stderr on build failure.
    """
    dist_dir.mkdir(parents=True, exist_ok=True)
    try:
        with build.env.DefaultIsolatedEnv(installer="uv") as env:
            builder = build.ProjectBuilder.from_isolated_env(env, project_dir)
            env.install([f"hanzo @ file:///{HANZO_DIR}"])
            # hanzo is a local dep, so we don't install it again.
            env.install(builder.get_requires_for_build("wheel") - {"hanzo"})
            wheel_name = builder.build("wheel", dist_dir)
    except build.BuildBackendException as exc:
        rc = getattr(exc, "return_code", "unknown")
        stderr = getattr(exc, "stderr", str(exc))
        pytest.fail(
            f"Build of {project_dir.name!r} failed\n"
            f"  return code : {rc}\n"
            f"  stderr      :\n{stderr}"
        )

    return Path(wheel_name)


def _install_wheel(wheel_path: Path, venv_dir: Path) -> Path:
    """Create a uv venv and install *wheel_path* into it.

    Returns the path to the venv's Python interpreter.
    """
    result = subprocess.run(
        ["uv", "venv", str(venv_dir)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.fail(
            f"uv venv creation failed\n"
            f"  return code : {result.returncode}\n"
            f"  stderr      :\n{result.stderr}"
        )

    result = subprocess.run(
        ["uv", "pip", "install", str(wheel_path)],
        env=os.environ | {"VIRTUAL_ENV": str(venv_dir)},
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.fail(
            f"uv pip install of {wheel_path.name!r} failed\n"
            f"  return code : {result.returncode}\n"
            f"  stderr      :\n{result.stderr}"
        )

    return venv_dir / _PYTHON_BIN


def _run_entrypoint(module: str, func: str, python: Path) -> str:
    """Call *module*.*func*() using *python* and return the captured stdout."""
    script = f"import {module}; {module}.{func}()"
    result = subprocess.run(
        [str(python), "-c", script],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.fail(
            f"Entrypoint {module}.{func} failed\n"
            f"  return code : {result.returncode}\n"
            f"  stderr      :\n{result.stderr}"
        )
    return result.stdout.strip()  # we don't care about trailing newlines.


@pytest.mark.parametrize("project_name", sorted(PROJECT_EXPECTATIONS))
def test_project_build_and_run(project_name: str, tmp_path: Path) -> None:
    project_dir = PROJECTS_DIR / project_name
    if not project_dir.is_dir():
        pytest.skip(f"Project directory not found: {project_dir}")

    module, func, expected_output = PROJECT_EXPECTATIONS[project_name]

    wheel_path = _build_wheel(project_dir, dist_dir=tmp_path / "dist")
    python = _install_wheel(wheel_path, venv_dir=tmp_path / "install-venv")
    actual_output = _run_entrypoint(module, func, python)

    assert actual_output == expected_output

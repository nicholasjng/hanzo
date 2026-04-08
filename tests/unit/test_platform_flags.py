"""Tests for platform-keyed flags/linkflags/defines in CCLibraryTarget.from_toml()."""

import tomllib
from unittest.mock import MagicMock

import pytest

from hanzo.platform import Platform
from hanzo.targets import CCLibraryTarget


@pytest.fixture
def macos_config():
    config = MagicMock()
    config.platform = Platform(system="macosx", os_version="13", arch="arm64")
    return config


@pytest.fixture
def linux_config():
    config = MagicMock()
    config.platform = Platform(system="linux", os_version=None, arch="x86_64")
    return config


PLATFORM_SPECIFIC_TOML = """
[targets.mylib]
name = "mylib"
sources = []

flags.macos = ["-fPIC", "-fvisibility=hidden"]
flags.linux = ["-fno-pie"]

linkflags.macos = ["-Wl,-dead_strip"]
linkflags.linux = ["-Wl,--gc-sections"]

defines.macos = ["NDEBUG"]
defines.linux = ["_GNU_SOURCE"]
"""

CROSS_PLATFORM_TOML = """
[targets.mylib]
name = "mylib"
sources = []

flags = ["-fPIC", "-Wall"]
linkflags = ["-Wl,--gc-sections"]
defines = ["NDEBUG", "MY_DEFINE=1"]
"""


def test_macos_platform_pickups(macos_config):
    toml = tomllib.loads(PLATFORM_SPECIFIC_TOML)["targets"]["mylib"]
    target = CCLibraryTarget.from_toml(toml, macos_config)
    assert target.flags == ["-fPIC", "-fvisibility=hidden"]
    assert target.linkflags == ["-Wl,-dead_strip"]
    assert len(target.defines) == 1
    assert target.defines[0].name == "NDEBUG"


def test_linux_platform_pickups(linux_config):
    toml = tomllib.loads(PLATFORM_SPECIFIC_TOML)["targets"]["mylib"]
    target = CCLibraryTarget.from_toml(toml, linux_config)
    assert target.flags == ["-fno-pie"]
    assert target.linkflags == ["-Wl,--gc-sections"]
    assert len(target.defines) == 1
    assert target.defines[0].name == "_GNU_SOURCE"


def test_cross_platform_config(linux_config):
    toml = tomllib.loads(CROSS_PLATFORM_TOML)["targets"]["mylib"]
    target = CCLibraryTarget.from_toml(toml, linux_config)
    assert target.flags == ["-fPIC", "-Wall"]
    assert target.linkflags == ["-Wl,--gc-sections"]
    assert len(target.defines) == 2
    assert target.defines[0].name == "NDEBUG"
    assert target.defines[1].name == "MY_DEFINE"
    assert target.defines[1].value == "1"

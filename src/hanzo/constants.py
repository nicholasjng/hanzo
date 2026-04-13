METADATA_VERSION: str = "2.5"
WHEEL_FILENAME = "{name}-{version}-{tag}.whl"
SDIST_FILENAME = "{name}-{version}.tar.gz"

# Default toolchain names for different languages
DEFAULT_CC_TOOLCHAIN_NAME: str = "host"
DEFAULT_PY_TOOLCHAIN_NAME: str = "current"

# default build directory for C/C++ extensions
DEFAULT_BUILD_DIR = "build"

# default source and data file extensions
DEFAULT_SOURCE_EXTENSIONS: frozenset[str] = frozenset({".py", ".pyi"})
DEFAULT_DATA_EXTENSIONS: frozenset[str] = frozenset()

# default source directories. Hanzo searches for packages in each of these directories.
DEFAULT_PACKAGE_DIRS: list[str] = ["src", "."]

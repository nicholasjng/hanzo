from packaging.specifiers import Specifier

from hanzo.types import Define

_SABI_MAP: dict[str, str] = {
    f"3.{minor}": f"0x{(3 << 24) + (minor << 16):08X}" for minor in range(1, 16)
}


class Feature:
    """A class representing a feature for a specific build target.

    A feature groups different attributes together, such as build flags,
    defines, and other configuration. Its main use is to toggle specific
    build parameters.
    """

    def __init__(self, name: str):
        self._name = name

    @property
    def name(self) -> str:
        return self._name


class CcFeature(Feature):
    def __init__(self, name: str):
        super().__init__(name=name)

        self._flags: list[str] = []
        self._linkflags: list[str] = []
        self._defines: list[Define] = []

    @property
    def flags(self) -> list[str]:
        return self._flags

    @property
    def linkflags(self) -> list[str]:
        return self._linkflags

    @property
    def defines(self) -> list[Define]:
        return self._defines


class StableABI(CcFeature):
    """A feature adding the stable ABI macro to a target and its dependents."""

    def __init__(self, abi_spec: str):
        super().__init__(name="stable-abi")

        abi_specifier = Specifier(abi_spec)
        abi_version = abi_specifier.version
        if abi_specifier.operator != ">=" or not abi_version.startswith("3"):
            raise ValueError(f"stable ABI specifier should be given as '>=3.x', got {abi_spec!r}")

        self._version_range = abi_specifier
        try:
            abi_hex = _SABI_MAP[abi_version]
        except KeyError:
            raise ValueError(f"unsupported stable ABI version {abi_version!r}")

        self._defines.append(Define(name="Py_LIMITED_API", value=abi_hex))

    @property
    def version_range(self) -> Specifier:
        return self._version_range


_FEATURE_MAPPING: dict[str, type[Feature]] = {
    "stable-abi": StableABI,
}


def get_feature(name: str) -> type[Feature]:
    try:
        return _FEATURE_MAPPING[name]
    except KeyError:
        raise ValueError(f"unknown feature {name!r}") from None


def register_feature(name: str, feature: type[Feature], force: bool = False) -> None:
    if name in _FEATURE_MAPPING and not force:
        raise ValueError(f"feature {name!r} already registered, force registration with force=True")

    _FEATURE_MAPPING[name] = feature


__all__ = [
    "Feature",
    "CcFeature",
    "StableABI",
    "get_feature",
    "register_feature",
]

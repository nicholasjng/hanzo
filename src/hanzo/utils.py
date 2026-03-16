import sysconfig

from packaging.specifiers import SpecifierSet


def to_snakecase(s: str) -> str:
    return s.replace("-", "_").replace(".", "_")


def calculate_wheel_abi(stable_abi: str | None, pure: bool) -> tuple[str, str]:
    if pure:
        return "py3", "none"

    current_interpreter = "cp" + sysconfig.get_config_var("py_version_nodot")
    current_python_version = sysconfig.get_config_var("py_version")
    if stable_abi is not None:
        stable_abi_spec = SpecifierSet(stable_abi)
        if current_python_version in stable_abi_spec:
            min_python = current_interpreter
            # TODO: Maybe disallow weird ABI3 specs (e.g. those with !=)
            for spec in stable_abi_spec:
                if spec.operator in ("==", ">="):
                    # TODO: Clean this up to allow prereleases
                    min_python = "cp" + spec.version.replace(".", "")
                return min_python, "abi3"

    return current_interpreter, current_interpreter


__all__ = ["calculate_wheel_abi", "to_snakecase"]

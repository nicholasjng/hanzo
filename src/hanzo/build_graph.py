from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hanzo.targets import Target


_build_graph: dict[str, "Target"] = {}


def get_build_graph():
    return _build_graph

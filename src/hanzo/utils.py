def to_snakecase(s: str) -> str:
    return s.replace("-", "_").replace(".", "_")


__all__ = ["to_snakecase"]

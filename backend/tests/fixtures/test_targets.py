from pathlib import Path


def add(left: int, right: int) -> int:
    return left + right


def clamp(value: int, low: int, high: int) -> int:
    return max(low, min(value, high))


def parse_count(value: str) -> int:
    if not value.isdecimal():
        raise ValueError("count must be a nonnegative integer")
    return int(value)


def read_text(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def buggy_average(values: list[int]) -> float:
    """Regression fixture: uses floor division by mistake."""
    return sum(values) // len(values)


def load_with(fetch):
    return fetch()

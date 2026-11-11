from dataclasses import dataclass


@dataclass(frozen=True)
class Framework:
    language: str
    name: str
    executable: str


FRAMEWORKS = {"pytest": Framework("python", "pytest", "python -m pytest")}


def resolve_framework(language: str, framework: str) -> Framework | None:
    item = FRAMEWORKS.get(framework.lower())
    return item if item and item.language == language else None

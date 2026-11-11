from app.code_review.schemas import Language

ANALYZERS_BY_LANGUAGE: dict[Language, tuple[str, ...]] = {
    "python": ("ruff", "bandit", "pylint"),
    "javascript": ("eslint",),
    "typescript": ("eslint", "tsc"),
    "java": ("checkstyle",),
    "c": ("clang",),
    "cpp": ("clang",),
}
DEFAULT_ANALYZERS: dict[Language, tuple[str, ...]] = {
    "python": ("ruff", "bandit"),
    "javascript": ("eslint",),
    "typescript": ("eslint", "tsc"),
    "java": ("checkstyle",),
    "c": ("clang",),
    "cpp": ("clang",),
}


def analyzer_names(language: Language) -> tuple[str, ...]:
    return ANALYZERS_BY_LANGUAGE[language]


def default_analyzers(language: Language) -> list[str]:
    return list(DEFAULT_ANALYZERS[language])

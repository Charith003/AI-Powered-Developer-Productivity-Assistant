from pathlib import PurePosixPath

from app.code_review.schemas import Language

EXTENSIONS: dict[str, Language] = {
    ".py": "python",
    ".pyi": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".java": "java",
    ".c": "c",
    ".h": "c",
    ".cc": "cpp",
    ".cpp": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".hh": "cpp",
}


def detect_language(path: str, content: str) -> Language | None:
    language = EXTENSIONS.get(PurePosixPath(path).suffix.lower())
    if language:
        return language
    first_line = content.splitlines()[0] if content.splitlines() else ""
    if first_line.startswith("#!") and "python" in first_line.lower():
        return "python"
    if first_line.startswith("#!") and any(
        name in first_line.lower() for name in ("node", "deno", "bun")
    ):
        return "javascript"
    return None

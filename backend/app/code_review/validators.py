import hashlib
import re
from pathlib import PurePosixPath

from fastapi import HTTPException

from app.code_review.language_detector import detect_language
from app.code_review.schemas import CreateReviewRequest, Language

MAX_FILES = 10
MAX_FILE_BYTES = 65_536
MAX_TOTAL_BYTES = 262_144
MAX_PATH_LENGTH = 160
BLOCKED_NAMES = {".env", ".env.local", ".npmrc", ".pypirc", "id_rsa", "id_ed25519"}
BLOCKED_WINDOWS_STEMS = {
    "con",
    "prn",
    "aux",
    "nul",
    *(f"com{index}" for index in range(1, 10)),
    *(f"lpt{index}" for index in range(1, 10)),
}
SECRET_PATTERNS = [
    re.compile(
        r"(?i)\b(api[_-]?key|secret|password|access[_-]?token|token)\b\s*[:=]\s*(['\"]?)([^\s,'\";]{8,})\2"
    ),
    re.compile(r"\b(?:sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|AKIA[A-Z0-9]{16})\b"),
    re.compile(
        r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----[\s\S]*?-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
    ),
]


def validate_source(payload: CreateReviewRequest) -> tuple[Language, list[dict[str, str]]]:
    if payload.analyzers == []:
        raise HTTPException(422, "Select at least one static analyzer")
    if not payload.files or len(payload.files) > MAX_FILES:
        raise HTTPException(422, "Submit between 1 and 10 source files")
    total = 0
    seen: set[str] = set()
    validated: list[dict[str, str]] = []
    languages: set[Language] = set()
    for source in payload.files:
        path = source.path.replace("\\", "/")
        parsed = PurePosixPath(path)
        windows_stem = parsed.name.split(".", 1)[0].casefold()
        if (
            parsed.is_absolute()
            or re.match(r"^[A-Za-z]:", path) is not None
            or not path
            or any(part in {"", ".", ".."} for part in path.split("/"))
            or "\x00" in path
            or any(ord(char) < 32 or char in '<>:"|?*' for char in path)
            or len(path) > MAX_PATH_LENGTH
            or windows_stem in BLOCKED_WINDOWS_STEMS
        ):
            raise HTTPException(422, "Invalid source file path")
        if parsed.name.lower() in BLOCKED_NAMES or parsed.name.lower().startswith(".env."):
            raise HTTPException(422, "Credential and environment files cannot be reviewed")
        if path.casefold() in seen:
            raise HTTPException(422, "Source file paths must be unique")
        seen.add(path.casefold())
        try:
            size = len(source.content.encode("utf-8", errors="strict"))
        except UnicodeError as exc:
            raise HTTPException(422, "Source file must be valid UTF-8 text") from exc
        if size > MAX_FILE_BYTES:
            raise HTTPException(413, "Each source file is limited to 64 KiB")
        if "\x00" in source.content:
            raise HTTPException(422, "Binary content is not supported")
        total += size
        detected = detect_language(path, source.content)
        if detected is None:
            raise HTTPException(
                422, f"Unsupported source file type: {parsed.suffix or '(no extension)'}"
            )
        languages.add(detected)
        validated.append({"path": path, "content": source.content})
    if total > MAX_TOTAL_BYTES:
        raise HTTPException(413, "The combined source limit is 256 KiB")
    selected = payload.language
    if selected != "auto":
        if languages != {selected}:
            raise HTTPException(422, "Selected language does not match every submitted source file")
        language: Language = selected
    else:
        if len(languages) != 1:
            raise HTTPException(422, "One review must contain files from a single language")
        language = next(iter(languages))
    return language, validated


def sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def redact_secrets(content: str) -> str:
    redacted = content
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub("[REDACTED_SECRET]", redacted)
    return redacted


def valid_evidence(content: str, start: int | None, end: int | None, evidence: str) -> bool:
    lines = content.splitlines()
    if not evidence.strip() or not start or not end or start > end or end > len(lines):
        return False
    excerpt = "\n".join(lines[start - 1 : end])
    return evidence.strip() in excerpt

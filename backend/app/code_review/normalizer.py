from uuid import uuid4

from app.code_review.schemas import Language
from app.code_review.validators import redact_secrets

SEVERITIES = {"critical", "high", "medium", "low", "informational"}
CATEGORIES = {
    "security",
    "bug",
    "performance",
    "reliability",
    "maintainability",
    "code_style",
    "best_practice",
    "type_error",
}


def normalize_findings(
    rows: list[dict], files: list[dict[str, str]], language: Language
) -> list[dict]:
    del language
    source_files = {item["path"]: item["content"] for item in files}
    normalized: list[dict] = []
    seen: set[tuple] = set()
    for row in rows:
        path = str(row.get("file_path", "")).replace("\\", "/")
        while path.startswith("./"):
            path = path[2:]
        if path not in source_files:
            candidate = next((known for known in source_files if path.endswith("/" + known)), None)
            if candidate is None:
                continue
            path = candidate
        start, end = row.get("line_start"), row.get("line_end")
        safe_content = redact_secrets(source_files[path])
        lines = safe_content.splitlines()
        if start is not None and (start < 1 or start > len(lines)):
            continue
        if end is not None and (end < (start or 1) or end > len(lines)):
            continue
        evidence = redact_secrets(str(row.get("evidence") or ""))
        if not evidence and start:
            evidence = "\n".join(lines[start - 1 : min(end or start, start + 4)])[:1200]
        if evidence and start:
            excerpt = "\n".join(lines[start - 1 : end or start])
            if evidence.strip() not in excerpt.strip():
                continue
        source = "ai" if row.get("source") == "ai" else "static"
        rule = row.get("rule_id")
        key = (source, path, start, rule, row.get("title"))
        if key in seen:
            continue
        seen.add(key)
        severity = row.get("severity", "informational")
        category = row.get("category", "best_practice")
        normalized.append(
            {
                "id": str(uuid4()),
                "file_path": path,
                "line_start": start,
                "line_end": end,
                "column_start": row.get("column_start"),
                "title": redact_secrets(str(row.get("title", "Review finding")))[:200],
                "description": redact_secrets(str(row.get("description", "")))[:3000],
                "reasoning": redact_secrets(str(row.get("reasoning", "")))[:2000],
                "severity": severity if severity in SEVERITIES else "informational",
                "category": category if category in CATEGORIES else "best_practice",
                "evidence": evidence[:1200],
                "recommendation": redact_secrets(str(row.get("recommendation", "")))[:2000],
                "source": source,
                "analyzer": str(row.get("analyzer") or ("ai" if source == "ai" else "static"))[:40],
                "rule_id": str(rule)[:80] if rule else None,
                "confidence": row.get("confidence") if source == "ai" else None,
            }
        )
    return normalized

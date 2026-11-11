import json
import xml.etree.ElementTree as ET
from pathlib import Path


def parse_junit(xml_text: str) -> list[dict]:
    if not xml_text:
        return []
    root = ET.fromstring(xml_text)
    rows = []
    for case in root.iter("testcase"):
        failure = case.find("failure")
        error = case.find("error")
        skipped = case.find("skipped")
        result = failure if failure is not None else error
        rows.append(
            {
                "test_name": f"{case.get('classname', '')}::{case.get('name', 'unknown')}",
                "test_file": case.get("file", "test_generated.py")[:240],
                "status": "failed"
                if failure is not None
                else "error"
                if error is not None
                else "skipped"
                if skipped is not None
                else "passed",
                "duration": float(case.get("time", "0")),
                "error_message": (result.get("message") or "")[:4000]
                if result is not None
                else None,
                "traceback": (result.text or "")[:12_000] if result is not None else None,
            }
        )
    return rows


def parse_coverage(path: Path) -> dict:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"line_coverage": None, "branch_coverage": None, "uncovered_lines": {}}
    files = raw.get("files", {})
    uncovered = {
        name.removeprefix("/workspace/"): data.get("missing_lines", [])
        for name, data in files.items()
        if data.get("missing_lines")
    }
    totals = raw.get("totals", {})
    line = totals.get("percent_covered")
    branches = totals.get("num_branches", 0)
    branch_cov = (
        round((totals.get("covered_branches", 0) / branches) * 100, 2) if branches else None
    )
    return {
        "line_coverage": round(float(line), 2) if line is not None else None,
        "branch_coverage": branch_cov,
        "uncovered_lines": uncovered,
    }

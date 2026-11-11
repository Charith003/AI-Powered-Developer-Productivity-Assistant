import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.code_review.schemas import AnalyzerStatus, Language
from app.config import Settings, settings

OUTPUT_LIMIT = 64 * 1024
TIMEOUT_SECONDS = 10


@dataclass
class Execution:
    status: str
    exit_code: int | None
    duration_ms: int
    stdout: str
    stderr: str
    message: str | None = None


def run_command(args: list[str], cwd: Path) -> Execution:
    started = time.monotonic()
    try:
        process = subprocess.Popen(
            args,
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            env={
                "PATH": os.environ.get("PATH", ""),
                "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
            },
        )
    except FileNotFoundError:
        return Execution("unavailable", None, 0, "", "", "Analyzer executable is unavailable")
    except OSError:
        return Execution("failed", None, 0, "", "", "Analyzer could not be started")

    buffers: dict[str, bytearray] = {"stdout": bytearray(), "stderr": bytearray()}
    total_read = 0
    lock = threading.Lock()
    overflow = threading.Event()

    def drain(name: str, stream):
        nonlocal total_read
        while True:
            chunk = stream.read(4096)
            if not chunk:
                return
            with lock:
                remaining = max(0, OUTPUT_LIMIT - total_read)
                buffers[name].extend(chunk[:remaining])
                total_read += len(chunk)
                if total_read > OUTPUT_LIMIT:
                    overflow.set()
                    try:
                        process.kill()
                    except OSError:
                        pass

    readers = [
        threading.Thread(target=drain, args=("stdout", process.stdout), daemon=True),
        threading.Thread(target=drain, args=("stderr", process.stderr), daemon=True),
    ]
    for reader in readers:
        reader.start()
    try:
        process.wait(timeout=TIMEOUT_SECONDS)
        status = "failed" if overflow.is_set() else "completed"
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
        status = "timeout"
    for reader in readers:
        reader.join(timeout=1)
    elapsed = int((time.monotonic() - started) * 1000)
    stdout = bytes(buffers["stdout"]).decode("utf-8", errors="replace")
    stderr = bytes(buffers["stderr"]).decode("utf-8", errors="replace")
    message = "Analyzer output exceeded the 64 KiB limit" if overflow.is_set() else None
    if status == "timeout":
        message = f"Analyzer exceeded the {TIMEOUT_SECONDS} second timeout"
    return Execution(status, process.returncode, elapsed, stdout, stderr, message)


def normalized_status(name: str, execution: Execution) -> AnalyzerStatus:
    return AnalyzerStatus(
        analyzer=name,
        status=execution.status,
        exit_code=execution.exit_code,
        duration_ms=execution.duration_ms,
        message=execution.message,
    )


def json_output(execution: Execution, analyzer: str) -> list[dict[str, Any]]:
    if execution.status != "completed" or not execution.stdout.strip():
        return []
    try:
        value = json.loads(execution.stdout)
    except json.JSONDecodeError:
        return []
    if analyzer == "ruff":
        return value if isinstance(value, list) else []
    if analyzer == "bandit":
        return value.get("results", []) if isinstance(value, dict) else []
    if analyzer == "pylint":
        return value if isinstance(value, list) else []
    return []


def analyzer_workspace(files: list[dict[str, str]]):
    directory = tempfile.TemporaryDirectory(prefix="devpilot-review-")
    root = Path(directory.name).resolve()
    paths: dict[str, Path] = {}
    for source in files:
        target = (root / source["path"]).resolve()
        if root not in target.parents:
            directory.cleanup()
            raise ValueError("Source path escaped isolated review directory")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source["content"], encoding="utf-8", newline="")
        paths[source["path"]] = target
    return directory, root, paths


def command_for_python(name: str, args: list[str], root: Path) -> Execution:
    if name in {"ruff", "bandit", "pylint"}:
        import importlib.util

        module = {"ruff": "ruff", "bandit": "bandit", "pylint": "pylint"}[name]
        if importlib.util.find_spec(module) is None:
            return Execution("unavailable", None, 0, "", "", f"Install the '{module}' analyzer")
        return run_command([sys.executable, "-m", module, *args], root)
    return Execution("unavailable", None, 0, "", "", "Analyzer is not configured")


def python_analyzers(root: Path, paths: dict[str, Path], requested: list[str]):
    results = []
    findings: list[dict[str, Any]] = []
    names = requested or ["ruff"]
    for name in names:
        if name not in {"ruff", "bandit", "pylint"}:
            results.append(
                AnalyzerStatus(
                    analyzer=name, status="unsupported", message="Analyzer does not support Python"
                )
            )
            continue
        relative = [path for path in paths]
        if name == "ruff":
            args = ["check", "--isolated", "--output-format=json", *relative]
        elif name == "bandit":
            args = ["-q", "-f", "json", *relative]
        else:
            args = ["--score=n", "--output-format=json", *relative]
        execution = command_for_python(name, args, root)
        results.append(normalized_status(name, execution))
        for item in json_output(execution, name):
            finding = parse_python_finding(name, item)
            if finding:
                findings.append(finding)
        if execution.status == "completed" and execution.exit_code == 2 and name != "pylint":
            results[-1].status = "failed"
            results[-1].message = "Analyzer returned an unexpected exit code"
    return results, findings


def parse_python_finding(name: str, item: dict[str, Any]) -> dict[str, Any] | None:
    if name == "ruff":
        code = str(item.get("code") or "")
        location = item.get("location") or {}
        severity = (
            "high"
            if code.startswith(("S", "B"))
            else "medium"
            if code.startswith(("E", "F"))
            else "low"
        )
        category = (
            "security"
            if code.startswith(("S", "B"))
            else "bug"
            if code.startswith(("E", "F"))
            else "code_style"
        )
        return {
            "file_path": str(item.get("filename", "")),
            "analyzer": name,
            "line_start": (location.get("row")),
            "line_end": (item.get("end_location") or {}).get("row") or location.get("row"),
            "column_start": location.get("column"),
            "title": f"{code}: {item.get('message', 'Static analysis finding')}",
            "description": str(item.get("message", ""))[:3000],
            "severity": severity,
            "category": category,
            "evidence": "",
            "recommendation": str(
                (item.get("fix") or {}).get("message")
                or "Review this finding and apply the appropriate fix."
            ),
            "source": "static",
            "rule_id": code or None,
            "confidence": None,
        }
    if name == "bandit":
        severity = {"HIGH": "high", "MEDIUM": "medium", "LOW": "low"}.get(
            item.get("issue_severity"), "informational"
        )
        return {
            "file_path": str(item.get("filename", "")),
            "analyzer": name,
            "line_start": item.get("line_number"),
            "line_end": item.get("line_number"),
            "column_start": None,
            "title": f"{item.get('test_id', 'Bandit')}: {item.get('issue_text', 'Security finding')}",
            "description": str(item.get("issue_text", ""))[:3000],
            "severity": severity,
            "category": "security",
            "evidence": "",
            "recommendation": "Review the analyzer guidance and verify the context before changing this code.",
            "source": "static",
            "rule_id": str(item.get("test_id", "")) or None,
            "confidence": None,
        }
    msg_id = str(item.get("message-id", ""))
    category = "type_error" if msg_id.startswith("E") else "maintainability"
    return {
        "file_path": str(item.get("path", "")),
        "analyzer": name,
        "line_start": item.get("line"),
        "line_end": item.get("endLine") or item.get("line"),
        "column_start": item.get("column"),
        "title": f"{msg_id}: {item.get('message', 'Pylint finding')}",
        "description": str(item.get("message", ""))[:3000],
        "severity": "medium" if item.get("type") == "error" else "low",
        "category": category,
        "evidence": "",
        "recommendation": "Review the analyzer guidance and verify the context before changing this code.",
        "source": "static",
        "rule_id": msg_id or None,
        "confidence": None,
    }


def run_non_python(
    language: Language,
    root: Path,
    paths: dict[str, Path],
    requested: list[str],
    configured_settings: Settings,
):

    findings: list[dict[str, Any]] = []
    statuses: list[AnalyzerStatus] = []
    if language in {"javascript", "typescript"}:
        eslint_js = (
            Path(__file__).resolve().parents[4]
            / "frontend"
            / "node_modules"
            / "eslint"
            / "bin"
            / "eslint.js"
        )
        node = shutil.which("node")
        eslint_requested = [name for name in requested if name == "eslint"]
        for name in requested:
            if name not in {"eslint", "tsc"} or (language == "javascript" and name == "tsc"):
                statuses.append(
                    AnalyzerStatus(
                        analyzer=name,
                        status="unsupported",
                        message=f"Analyzer does not support {language}",
                    )
                )
        for name in eslint_requested:
            if not node or not eslint_js.is_file():
                statuses.append(
                    AnalyzerStatus(
                        analyzer=name,
                        status="unavailable",
                        message="Node.js and the project ESLint dependency are required",
                    )
                )
                continue
            for relpath, filepath in paths.items():
                ts_parser = (
                    Path(__file__).resolve().parents[4]
                    / "frontend"
                    / "node_modules"
                    / "@typescript-eslint"
                    / "parser"
                    / "dist"
                    / "index.js"
                )
                if language == "typescript" and not ts_parser.is_file():
                    statuses.append(
                        AnalyzerStatus(
                            analyzer=name,
                            status="unavailable",
                            message="ESLint TypeScript parser is not installed",
                        )
                    )
                    break
                parser_args = ["--parser", str(ts_parser)] if language == "typescript" else []
                execution = run_command(
                    [
                        node,
                        str(eslint_js),
                        "--no-config-lookup",
                        "--no-ignore",
                        *parser_args,
                        "--format",
                        "json",
                        "--rule",
                        '{"no-eval":"error","no-debugger":"warn","eqeqeq":"warn","no-unused-vars":"warn"}',
                        str(filepath),
                    ],
                    root,
                )
                statuses.append(normalized_status(name, execution))
                if execution.status == "completed":
                    try:
                        for item in json.loads(execution.stdout):
                            for message in item.get("messages", []):
                                findings.append(
                                    {
                                        "file_path": relpath,
                                        "analyzer": name,
                                        "line_start": message.get("line"),
                                        "line_end": message.get("endLine") or message.get("line"),
                                        "column_start": message.get("column"),
                                        "title": f"{message.get('ruleId') or 'ESLint'}: {message.get('message', 'Lint finding')}",
                                        "description": str(message.get("message", ""))[:3000],
                                        "severity": "high"
                                        if message.get("severity") == 2
                                        and message.get("ruleId") == "no-eval"
                                        else "low"
                                        if message.get("severity") == 1
                                        else "medium",
                                        "category": "security"
                                        if message.get("ruleId") == "no-eval"
                                        else "code_style",
                                        "evidence": "",
                                        "recommendation": "Review and correct the reported lint rule.",
                                        "source": "static",
                                        "rule_id": message.get("ruleId"),
                                        "confidence": None,
                                    }
                                )
                    except (json.JSONDecodeError, TypeError):
                        statuses[-1].status = "failed"
                        statuses[-1].message = "ESLint returned invalid structured output"
        if language == "typescript":
            run_tsc = "tsc" in requested
            if run_tsc:
                tsc = (
                    Path(__file__).resolve().parents[4]
                    / "frontend"
                    / "node_modules"
                    / "typescript"
                    / "bin"
                    / "tsc"
                )
                if not node or not tsc.is_file():
                    statuses.append(
                        AnalyzerStatus(
                            analyzer="tsc",
                            status="unavailable",
                            message="TypeScript compiler is not installed",
                        )
                    )
                else:
                    for relpath, filepath in paths.items():
                        execution = run_command(
                            [
                                node,
                                str(tsc),
                                "--noEmit",
                                "--skipLibCheck",
                                "--target",
                                "ES2022",
                                "--pretty",
                                "false",
                                str(filepath),
                            ],
                            root,
                        )
                        statuses.append(normalized_status("tsc", execution))
                        for line in (execution.stdout + execution.stderr).splitlines():
                            match = re.search(r"\((\d+),(\d+)\): error (TS\d+): (.*)$", line)
                            if match:
                                findings.append(
                                    {
                                        "file_path": relpath,
                                        "analyzer": "tsc",
                                        "line_start": int(match.group(1)),
                                        "line_end": int(match.group(1)),
                                        "column_start": int(match.group(2)),
                                        "title": "TypeScript compiler diagnostic",
                                        "description": match.group(4)[:3000],
                                        "severity": "medium",
                                        "category": "type_error",
                                        "evidence": "",
                                        "recommendation": "Resolve the TypeScript compiler diagnostic.",
                                        "source": "static",
                                        "rule_id": match.group(3),
                                        "confidence": None,
                                    }
                                )
    elif language in {"c", "cpp"}:
        for name in requested:
            if name != "clang":
                statuses.append(
                    AnalyzerStatus(
                        analyzer=name,
                        status="unsupported",
                        message=f"Analyzer does not support {language}",
                    )
                )
        if "clang" not in requested:
            return statuses, findings
        compiler = shutil.which("clang") or shutil.which("gcc" if language == "c" else "g++")
        requested_name = Path(compiler).name if compiler else "clang"
        if not compiler:
            statuses.append(
                AnalyzerStatus(
                    analyzer=requested_name,
                    status="unavailable",
                    message="Install clang or the corresponding GCC compiler to run compile-only diagnostics",
                )
            )
        else:
            for relpath, filepath in paths.items():
                include_pattern = re.compile(
                    r"(?im)^\s*#\s*(?:include|include_next|import)\s*[<\"]([^>\"]+)[>\"]"
                )
                unsafe_include = False
                for source_file in paths.values():
                    for match in include_pattern.finditer(source_file.read_text(encoding="utf-8")):
                        include_path = match.group(1).replace("\\", "/")
                        if (
                            include_path.startswith("/")
                            or re.match(r"^[A-Za-z]:", include_path)
                            or ".." in include_path.split("/")
                        ):
                            unsafe_include = True
                if unsafe_include:
                    statuses.append(
                        AnalyzerStatus(
                            analyzer=requested_name,
                            status="failed",
                            message="Absolute and parent-traversal C/C++ include paths are blocked",
                        )
                    )
                    break
                execution = run_command(
                    [compiler, "-fsyntax-only", "-Wall", "-Wextra", str(filepath)],
                    root,
                )
                statuses.append(normalized_status(requested_name, execution))
                for line in (execution.stdout + execution.stderr).splitlines():
                    match = re.search(r":(\d+):(\d+): (warning|error): (.*)$", line)
                    if match:
                        findings.append(
                            {
                                "file_path": relpath,
                                "analyzer": requested_name,
                                "line_start": int(match.group(1)),
                                "line_end": int(match.group(1)),
                                "column_start": int(match.group(2)),
                                "title": match.group(4)[:200],
                                "description": match.group(4)[:3000],
                                "severity": "medium" if match.group(3) == "error" else "low",
                                "category": "bug",
                                "evidence": "",
                                "recommendation": "Review this compiler diagnostic.",
                                "source": "static",
                                "rule_id": match.group(3),
                                "confidence": None,
                            }
                        )
    elif language == "java":
        for name in requested:
            if name != "checkstyle":
                statuses.append(
                    AnalyzerStatus(
                        analyzer=name,
                        status="unsupported",
                        message="Analyzer does not support Java",
                    )
                )
        if "checkstyle" not in requested:
            return statuses, findings
        jar = configured_settings.checkstyle_jar
        checkstyle_config = configured_settings.checkstyle_config
        java = shutil.which("java")
        if (
            not jar
            or not Path(jar).is_file()
            or not checkstyle_config
            or not Path(checkstyle_config).is_file()
            or not java
        ):
            statuses.append(
                AnalyzerStatus(
                    analyzer="checkstyle",
                    status="unavailable",
                    message="Java runtime, CHECKSTYLE_JAR, and CHECKSTYLE_CONFIG are required",
                )
            )
        else:
            execution = run_command(
                [
                    java,
                    "-jar",
                    jar,
                    "-c",
                    checkstyle_config,
                    *[str(path) for path in paths.values()],
                ],
                root,
            )
            statuses.append(normalized_status("checkstyle", execution))
            for line in execution.stdout.splitlines():
                match = re.search(
                    r"\[(?:ERROR|WARN)\]\s+(.+?):(\d+):(\d+):\s+(.*?)(?:\s+\[([^]]+)\])?$", line
                )
                if match:
                    actual = Path(match.group(1)).name
                    relpath = next((p for p in paths if Path(p).name == actual), None)
                    if relpath:
                        findings.append(
                            {
                                "file_path": relpath,
                                "analyzer": "checkstyle",
                                "line_start": int(match.group(2)),
                                "line_end": int(match.group(2)),
                                "column_start": int(match.group(3)),
                                "title": (match.group(5) or "Checkstyle")[:200],
                                "description": match.group(4)[:3000],
                                "severity": "medium",
                                "category": "maintainability",
                                "evidence": "",
                                "recommendation": "Review and correct the Checkstyle diagnostic.",
                                "source": "static",
                                "rule_id": match.group(5),
                                "confidence": None,
                            }
                        )
    return statuses, findings


def analyze(
    files: list[dict[str, str]],
    language: Language,
    requested: list[str] | None,
    configured_settings: Settings = settings,
):
    from app.code_review.registry import analyzer_names, default_analyzers

    directory, root, paths = analyzer_workspace(files)
    try:
        requested_names = default_analyzers(language) if requested is None else requested
        valid_names = set(analyzer_names(language))
        unsupported = [name for name in requested_names if name not in valid_names]
        requested_names = [name for name in requested_names if name in valid_names]
        if language == "python":
            statuses, findings = python_analyzers(root, paths, requested_names)
        else:
            statuses, findings = run_non_python(
                language, root, paths, requested_names, configured_settings
            )
        statuses.extend(
            AnalyzerStatus(
                analyzer=name,
                status="unsupported",
                message=f"Analyzer is not registered for {language}",
            )
            for name in unsupported
        )
        return statuses, findings
    finally:
        directory.cleanup()

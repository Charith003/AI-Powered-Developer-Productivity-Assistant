"""Fixed container entrypoint: copy read-only inputs to bounded tmpfs and run Pytest."""

import argparse
import os
import re
import signal
import shutil
import subprocess
import sys
import time
from pathlib import Path


def drop_test_privileges():
    os.setgroups([])
    os.setgid(10001)
    os.setuid(10001)


def kill_leftover_test_processes():
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            status = (entry / "status").read_text(encoding="utf-8")
            uid_line = next(line for line in status.splitlines() if line.startswith("Uid:"))
            if int(uid_line.split()[1]) == 10001:
                os.kill(int(entry.name), signal.SIGKILL)
        except (OSError, StopIteration, ValueError, ProcessLookupError):
            continue


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--module", required=True)
    parser.add_argument("--collect-only", action="store_true")
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", args.module):
        return 64
    source = Path(args.source)
    if source.is_absolute() or ".." in source.parts:
        return 64
    source_in = (Path("/inputs") / source).resolve()
    input_root = Path("/inputs").resolve()
    if input_root not in source_in.parents or not source_in.is_file():
        return 64
    work = Path("/workspace")
    (work / source.parent).mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source_in, work / source)
    shutil.copyfile("/inputs/test_generated.py", work / "test_generated.py")
    # Docker's tmpfs mount hides the image's ownership. Pytest and coverage run
    # after dropping to uid 10001, so give that uid the bounded workspace.
    os.chown(work, 10001, 10001)
    work.chmod(0o700)
    results = Path("/results")
    results.chmod(0o700)
    source_parent = "." if source.parent == Path(".") else str(source.parent)
    command = [sys.executable, "-m", "pytest", "-q"]
    if args.collect_only:
        command.extend(["--collect-only", str(work / "test_generated.py")])
    else:
        command.extend([
            "--junitxml=/tmp/results.xml",
            "--cov-branch",
            f"--cov={args.module}",
            "--cov-report=json:/tmp/coverage.json",
            str(work / "test_generated.py"),
        ])
    env = {"PATH": os.environ.get("PATH", ""), "HOME": "/tmp", "PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": f"/workspace/{source_parent}"}
    result = subprocess.run(command, cwd=work, env=env, stdin=subprocess.DEVNULL, shell=False, check=False, preexec_fn=drop_test_privileges)
    if not args.collect_only:
        kill_leftover_test_processes()
        shutil.copyfile("/tmp/results.xml", results / "results.xml")
        shutil.copyfile("/tmp/coverage.json", results / "coverage.json")
        # Keep the bounded result tmpfs mounted while the worker copies the artifacts.
        time.sleep(8)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())


"""Live Docker checks. CI sets DEVPILOT_SANDBOX_RUNTIME=1; local unit runs skip them."""

import json
import os
import subprocess
import time
import uuid
from pathlib import Path

import pytest

from app.config import Settings
from app.test_generation.sandbox.results import parse_junit
from app.test_generation.sandbox.runner import DockerSandbox
from app.test_generation.sandbox.worker import parse_coverage_from_text

pytestmark = pytest.mark.skipif(
    os.getenv("DEVPILOT_SANDBOX_RUNTIME") != "1",
    reason="Requires Docker-enabled sandbox verification workflow",
)


def make_runner(*, timeout=30, memory="256m", output_bytes=65_536, pids=64):
    image = os.getenv("TEST_SANDBOX_IMAGE", "")
    assert "@sha256:" in image, "CI must provide a digest-pinned sandbox image"
    runner = DockerSandbox(
        Settings(
            test_sandbox_image=image,
            test_sandbox_timeout_seconds=timeout,
            test_sandbox_memory=memory,
            test_sandbox_output_bytes=output_bytes,
            test_sandbox_pids=pids,
        )
    )
    assert runner.docker_path and runner.verify_image_digest()
    return runner


def run_case(source, test_code, *, timeout=30, memory="256m", output_bytes=65_536, pids=64):
    runner = make_runner(timeout=timeout, memory=memory, output_bytes=output_bytes, pids=pids)
    run_id = str(uuid.uuid4())
    collection = runner.run(
        source_path="math_ops.py",
        source=source,
        test_code=test_code,
        collect_only=True,
        run_id=run_id,
    )
    assert collection.status == "completed", collection.message
    result = runner.run(
        source_path="math_ops.py",
        source=source,
        test_code=test_code,
        run_id=run_id,
    )
    evidence = {
        "execution_id": run_id,
        "fixture_id": test_code.splitlines()[0][:100],
        "container_id": result.container_id,
        "image_digest": os.environ["TEST_SANDBOX_IMAGE"].rsplit("@", 1)[1],
        "exit_code": result.exit_code,
        "status": result.status,
        "duration_ms": result.duration_ms,
        "cleanup_confirmed": result.cleanup_confirmed,
    }
    print("SANDBOX_EVIDENCE " + json.dumps(evidence, sort_keys=True))
    assert result.container_id and result.cleanup_confirmed is True
    return runner, result


def test_real_pytest_counts_failures_skips_coverage_and_nonroot():
    source = "def choose(value):\n    if value > 0:\n        return 'up'\n    return 'down'\n"
    tests = """# fixture: pass-fail-skip-coverage
import os
import math_ops
import pytest

def test_positive_branch_runs_as_unprivileged_user():
    assert os.getuid() == 10001
    assert math_ops.choose(2) == "up"

def test_negative_branch():
    assert math_ops.choose(0) == "down"

@pytest.mark.skip(reason="controlled skip fixture")
def test_skipped():
    assert False
"""
    _runner, result = run_case(source, tests)
    assert result.status == "completed", (
        f"{result.message}; stdout={result.stdout[-1000:]!r}; stderr={result.stderr[-1000:]!r}"
    )
    cases = parse_junit(result.junit_xml)
    assert [row["status"] for row in cases] == ["passed", "passed", "skipped"]
    coverage = parse_coverage_from_text(result.coverage_json)
    raw = json.loads(result.coverage_json)
    expected_raw_percent = raw["totals"]["percent_covered"]
    assert coverage["line_coverage"] == round(expected_raw_percent, 2)
    assert coverage["line_coverage"] is not None
    assert "math_ops.py" in coverage["file_coverage"]
    assert result.exit_code == 0


@pytest.mark.parametrize(
    "tests,expected_exit",
    [
        ("# fixture: syntax-error\ndef test_broken(:\n    pass\n", 2),
        (
            "# fixture: import-error\nimport module_that_does_not_exist\ndef test_missing():\n    assert True\n",
            2,
        ),
        ("# fixture: empty-suite\nvalue = 1\n", 5),
    ],
)
def test_real_collection_errors_and_empty_suite_are_not_success(tests, expected_exit):
    runner = make_runner()
    result = runner.run(
        source_path="math_ops.py",
        source="def choose(value): return value\n",
        test_code=tests,
        collect_only=True,
        run_id=str(uuid.uuid4()),
    )
    print(
        "COLLECTION_EVIDENCE "
        + json.dumps(
            {
                "fixture": tests.splitlines()[0],
                "exit_code": result.exit_code,
                "status": result.status,
                "container_id": result.container_id,
                "cleanup_confirmed": result.cleanup_confirmed,
            }
        )
    )
    assert result.status == "completed"
    assert result.exit_code == expected_exit
    assert result.cleanup_confirmed is True
    assert "::test_" not in result.stdout


def test_real_assertion_failure_has_traceback_and_nonzero_exit():
    _, result = run_case(
        "def choose(value): return value\n",
        "# fixture: assertion-failure\nimport math_ops\ndef test_wrong_expected_value():\n    assert math_ops.choose(2) == 99\n",
    )
    cases = parse_junit(result.junit_xml)
    assert result.status == "completed" and result.exit_code != 0
    assert len(cases) == 1 and cases[0]["status"] == "failed"
    assert cases[0]["traceback"] and "AssertionError" in cases[0]["traceback"]


def test_real_timeout_terminates_and_cleans_container():
    runner = make_runner(timeout=2)
    run_id = str(uuid.uuid4())
    result = runner.run(
        source_path="math_ops.py",
        source="def choose(value): return value\n",
        test_code="""# fixture: timeout
import time
def test_wait_forever():
    while True:
        time.sleep(0.1)
""",
        run_id=run_id,
    )
    print(
        "TIMEOUT_EVIDENCE "
        + json.dumps(
            {
                "execution_id": run_id,
                "container_id": result.container_id,
                "status": result.status,
                "cleanup_confirmed": result.cleanup_confirmed,
            }
        )
    )
    assert result.status == "timed_out"
    assert result.cleanup_confirmed is True


def test_real_cancellation_terminates_the_container():
    runner = make_runner(timeout=20)
    run_id = str(uuid.uuid4())
    started = time.monotonic()
    result = runner.run(
        source_path="math_ops.py",
        source="def choose(value): return value\n",
        test_code="""# fixture: live-cancellation
import time
def test_wait_for_cancellation():
    while True:
        time.sleep(0.1)
""",
        run_id=run_id,
        cancel_check=lambda: time.monotonic() - started > 3,
    )
    print(
        "CANCELLATION_EVIDENCE "
        + json.dumps(
            {
                "execution_id": run_id,
                "container_id": result.container_id,
                "status": result.status,
                "cleanup_confirmed": result.cleanup_confirmed,
            }
        )
    )
    assert result.status == "cancelled"
    assert result.container_id and result.cleanup_confirmed is True


def test_container_name_collision_does_not_delete_unowned_container():
    runner = make_runner()
    run_id = str(uuid.uuid4())
    name = f"devpilot-tests-{run_id.replace('-', '')}"
    subprocess.run(
        [
            runner.docker_path,
            "run",
            "--detach",
            "--name",
            name,
            "--label",
            "devpilot.execution-id=another-execution",
            "--network",
            "none",
            "--read-only",
            os.environ["TEST_SANDBOX_IMAGE"],
            "python",
            "-c",
            "import time; time.sleep(60)",
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    try:
        result = runner.run(
            source_path="math_ops.py",
            source="def choose(value): return value\n",
            test_code="def test_simple(): assert True\n",
            run_id=run_id,
        )
        assert result.status == "infrastructure_failure"
        assert result.cleanup_confirmed is False
        assert (
            subprocess.run(
                [runner.docker_path, "inspect", name], capture_output=True, check=False
            ).returncode
            == 0
        )
    finally:
        subprocess.run(
            [runner.docker_path, "rm", "--force", name], capture_output=True, check=False
        )


def test_real_output_limit_terminates_and_cleans_container():
    _, result = run_case(
        "def choose(value): return value\n",
        "# fixture: output-limit\ndef test_large_output():\n    print('X' * 120000)\n    assert False\n",
        output_bytes=4096,
    )
    assert result.status == "error"
    assert "output exceeded" in (result.message or "")


def test_real_memory_limit_is_enforced():
    _, result = run_case(
        "def choose(value): return value\n",
        "# fixture: memory-limit\ndef test_memory_limit():\n    payload = bytearray(256 * 1024 * 1024)\n    assert len(payload) > 0\n",
        memory="128m",
        timeout=15,
    )
    assert result.status == "infrastructure_failure"
    assert result.cleanup_confirmed is True


def test_real_process_limit_is_enforced():
    _, result = run_case(
        "def choose(value): return value\n",
        """# fixture: process-limit
import errno
import os
import signal
import time

def test_process_limit():
    children = []
    try:
        for _ in range(100):
            try:
                pid = os.fork()
            except OSError as exc:
                assert exc.errno == errno.EAGAIN
                assert 0 < len(children) < 100
                return
            if pid == 0:
                time.sleep(30)
                os._exit(0)
            children.append(pid)
        raise AssertionError("process limit was not enforced")
    finally:
        for pid in children:
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        for pid in children:
            try:
                os.waitpid(pid, 0)
            except ChildProcessError:
                pass
""",
        pids=32,
        timeout=15,
    )
    assert result.status == "completed" and result.exit_code == 0, (
        result.status,
        result.message,
        result.stdout[-1000:],
        result.stderr[-1000:],
    )
    assert parse_junit(result.junit_xml)[0]["status"] == "passed"


def test_real_network_filesystem_and_environment_isolation(tmp_path):
    marker = Path("/tmp/devpilot-sandbox-host-marker")
    marker.write_text("host-only", encoding="utf-8")
    try:
        tests = f'''# fixture: network-filesystem-environment-isolation
import os
import socket
from pathlib import Path

def test_container_boundaries():
    assert os.getuid() == 10001
    assert not any(key in os.environ for key in ("OPENAI_API_KEY", "DATABASE_URL", "JWT_SECRET", "POSTGRES_PASSWORD"))
    assert any(line.startswith("Seccomp:\\t2") for line in Path("/proc/self/status").read_text().splitlines())
    assert not Path("/var/run/docker.sock").exists()
    assert not Path("{marker.as_posix()}").exists()
    try:
        Path("/inputs/test_generated.py").write_text("changed", encoding="utf-8")
    except OSError:
        pass
    else:
        raise AssertionError("input bind mount was writable")
    link = Path("/workspace/input-link")
    link.symlink_to("/inputs", target_is_directory=True)
    try:
        (link / "test_generated.py").write_text("changed", encoding="utf-8")
    except OSError:
        pass
    else:
        raise AssertionError("symlink escaped the writable workspace")
    for host, port in (("1.1.1.1", 443), ("172.17.0.1", 5432), ("10.0.0.1", 6379), ("192.168.0.1", 5432), ("host.docker.internal", 5432)):
        try:
            socket.create_connection((host, port), timeout=0.5)
        except OSError:
            continue
        raise AssertionError(f"unexpected network access to {{host}}:{{port}}")
'''
        _, result = run_case("def choose(value): return value\n", tests, timeout=15)
        assert result.status == "completed" and result.exit_code == 0, (
            result.status,
            result.message,
            result.stdout[-1000:],
            result.stderr[-1000:],
        )
        assert parse_junit(result.junit_xml)[0]["status"] == "passed"
    finally:
        marker.unlink(missing_ok=True)


def test_container_uses_private_pid_and_ipc_and_default_seccomp():
    runner = make_runner()
    argv = runner.command(
        Path("/tmp/inputs"), "devpilot-tests-policy", "math_ops.py", "math_ops", True
    )
    # Docker's default is a private PID namespace; `--pid private` is invalid.
    assert "--pid" not in argv
    assert "--pid=host" not in argv
    assert argv[argv.index("--ipc") + 1] == "private"
    assert "--privileged" not in argv and "--network=host" not in argv
    assert "seccomp=unconfined" not in argv

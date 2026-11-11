import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from fastapi import HTTPException

from app.code_review.schemas import CreateReviewRequest, SourceFileInput
from app.code_review.validators import validate_source
from app.config import Settings

logger = logging.getLogger(__name__)


@dataclass
class SandboxResult:
    status: str
    exit_code: int | None = None
    duration_ms: int = 0
    stdout: str = ""
    stderr: str = ""
    junit_xml: str = ""
    coverage_json: str = ""
    message: str | None = None
    container_id: str | None = None
    cleanup_confirmed: bool | None = None


@dataclass
class DockerSandbox:
    settings: Settings
    docker_path: str | None = field(default_factory=lambda: shutil.which("docker"))

    @property
    def ready(self) -> bool:
        image = self.settings.test_sandbox_image or ""
        return bool(
            self.docker_path
            and re.fullmatch(r"[A-Za-z0-9./:_-]+@sha256:[a-f0-9]{64}", image)
            and re.fullmatch(r"\d+(?:[kmg])?", self.settings.test_sandbox_memory.lower())
            and re.fullmatch(r"(?:\d+\.?\d*|\.\d+)", self.settings.test_sandbox_cpus)
        )

    def run(
        self,
        *,
        source_path: str,
        source: str,
        test_code: str,
        collect_only: bool = False,
        run_id: str | None = None,
        cancel_check=None,
    ) -> SandboxResult:
        if not self.docker_path:
            return SandboxResult(
                "infrastructure_failure", message="Docker is unavailable; tests were not executed"
            )
        if not self.ready:
            return SandboxResult(
                "infrastructure_failure",
                message="Configure a digest-pinned TEST_SANDBOX_IMAGE before execution",
            )
        if not self.verify_image_digest():
            return SandboxResult(
                "infrastructure_failure",
                message="Configured sandbox image digest is unavailable or does not match the local image",
            )
        try:
            language, files = validate_source(
                CreateReviewRequest(
                    language="python",
                    files=[SourceFileInput(path=source_path, content=source)],
                    ai_enabled=False,
                )
            )
            if language != "python":
                raise ValueError("Only Python source is supported by this sandbox")
        except (HTTPException, ValueError) as exc:
            return SandboxResult("error", message=f"Invalid sandbox input: {str(exc)[:240]}")

        if run_id is not None and not re.fullmatch(r"[0-9a-fA-F-]{16,64}", run_id):
            return SandboxResult("error", message="Invalid execution identifier")
        safe_run_id = run_id.replace("-", "").lower() if run_id else uuid.uuid4().hex
        container_name = f"devpilot-tests-{safe_run_id}"
        with tempfile.TemporaryDirectory(prefix="devpilot-test-") as temp:
            root = Path(temp).resolve()
            input_root = root / "inputs"
            artifacts_root = root / "artifacts"
            input_root.mkdir()
            artifacts_root.mkdir()
            source_target = (input_root / files[0]["path"]).resolve()
            if input_root not in source_target.parents:
                return SandboxResult("error", message="Source path escaped temporary workspace")
            source_target.parent.mkdir(parents=True, exist_ok=True)
            source_target.write_text(files[0]["content"], encoding="utf-8", newline="")
            (input_root / "test_generated.py").write_text(test_code, encoding="utf-8", newline="")
            cidfile = root / "container.cid"
            command = self.command(
                input_root,
                container_name,
                files[0]["path"],
                Path(files[0]["path"]).stem,
                collect_only,
                cidfile=cidfile,
            )
            started = time.monotonic()
            execution = self._run(command, artifacts_root, cancel_check=cancel_check)
            execution.duration_ms = int((time.monotonic() - started) * 1000)
            if execution.status != "completed" or collect_only:
                return execution
            try:
                execution.junit_xml = self._read_artifact(artifacts_root / "results.xml")
                execution.coverage_json = self._read_artifact(artifacts_root / "coverage.json")
            except OSError:
                execution.status = "infrastructure_failure"
                execution.message = "Sandbox completed without required result artifacts"
            return execution

    def verify_image_digest(self) -> bool:
        image = self.settings.test_sandbox_image or ""
        if not self.docker_path or not re.fullmatch(
            r"[A-Za-z0-9./:_-]+@sha256:[a-f0-9]{64}", image
        ):
            return False
        try:
            inspected = subprocess.run(
                [self.docker_path, "image", "inspect", "--format", "{{json .RepoDigests}}", image],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
                shell=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return False
        if inspected.returncode != 0:
            return False
        try:
            repo_digests = json.loads(inspected.stdout)
        except (TypeError, json.JSONDecodeError):
            return False
        repository, digest = image.rsplit("@", 1)
        last_colon = repository.rfind(":")
        last_slash = repository.rfind("/")
        repository = repository[:last_colon] if last_colon > last_slash else repository
        expected = f"{repository}@{digest}"
        return expected in repo_digests if isinstance(repo_digests, list) else False

    def command(
        self,
        workspace: Path,
        container_name: str,
        source_path: str,
        module_name: str,
        collect_only: bool,
        *,
        cidfile: Path | None = None,
    ) -> list[str]:
        argv = [
            self.docker_path or "docker",
            "run",
            "--name",
            container_name,
            "--pull=never",
            "--init",
            "--network",
            "none",
            "--memory",
            self.settings.test_sandbox_memory,
            "--ipc",
            "private",
            "--memory-swap",
            self.settings.test_sandbox_memory,
            "--cpus",
            self.settings.test_sandbox_cpus,
            "--pids-limit",
            str(self.settings.test_sandbox_pids),
            "--ulimit",
            "nofile=256:256",
            "--ulimit",
            "core=0:0",
            "--ulimit",
            "fsize=16777216:16777216",
            "--read-only",
            "--cap-drop=ALL",
            "--cap-add=SETUID",
            "--cap-add=SETGID",
            "--cap-add=KILL",
            "--security-opt=no-new-privileges",
            "--user",
            "0:0",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,nodev,size=32m,nr_inodes=2048",
            "--tmpfs",
            "/workspace:rw,noexec,nosuid,nodev,size=64m,nr_inodes=4096,mode=1777",
            "--tmpfs",
            "/results:rw,noexec,nosuid,nodev,size=16m,nr_inodes=2048",
            "--mount",
            f"type=bind,src={workspace},dst=/inputs,readonly",
            "--workdir",
            "/workspace",
        ]
        if cidfile is not None:
            argv.extend(["--cidfile", str(cidfile)])
        execution_id = container_name.removeprefix("devpilot-tests-")
        argv.extend(
            ["--label", "devpilot.managed=true", "--label", f"devpilot.execution-id={execution_id}"]
        )
        argv.extend(
            [
                self.settings.test_sandbox_image or "",
                "python",
                "/opt/devpilot/runner.py",
                "--source",
                source_path,
                "--module",
                module_name,
            ]
        )
        if collect_only:
            argv.append("--collect-only")
        return argv

    def remove_execution(self, run_id: str) -> bool:
        if not self.docker_path or not re.fullmatch(r"[0-9a-fA-F-]{16,64}", run_id):
            return False
        name = f"devpilot-tests-{run_id.replace('-', '').lower()}"
        return self._remove_owned_container(name, run_id.replace("-", "").lower())

    def _remove_owned_container(self, container_name: str, execution_id: str) -> bool:
        if not self.docker_path:
            return False
        try:
            inspected = subprocess.run(
                [
                    self.docker_path,
                    "inspect",
                    "--format",
                    '{{index .Config.Labels "devpilot.execution-id"}}',
                    container_name,
                ],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
                shell=False,
            )
            if inspected.returncode != 0:
                return True
            if inspected.stdout.strip() != execution_id:
                return False
            removed = subprocess.run(
                [self.docker_path, "rm", "--force", container_name],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
                check=False,
                shell=False,
            )
            if removed.returncode == 0:
                return True
            inspected = subprocess.run(
                [self.docker_path, "inspect", container_name],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
                check=False,
                shell=False,
            )
            return inspected.returncode != 0
        except (OSError, subprocess.TimeoutExpired):
            return False

    def _run(self, argv: list[str], artifacts_root: Path, cancel_check=None) -> SandboxResult:
        started = time.monotonic()
        try:
            process = subprocess.Popen(
                argv,
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
            return SandboxResult(
                "infrastructure_failure", message="Docker executable is unavailable"
            )
        output_limit = self.settings.test_sandbox_output_bytes
        stdout = bytearray()
        stderr = bytearray()
        lock = threading.Lock()
        overflow = threading.Event()

        def drain(stream, destination):
            while chunk := stream.read(4096):
                with lock:
                    remaining = output_limit - len(stdout) - len(stderr)
                    if remaining > 0:
                        destination.extend(chunk[:remaining])
                    if len(chunk) > remaining:
                        overflow.set()
                        try:
                            process.kill()
                        except ProcessLookupError:
                            pass

        threads = [
            threading.Thread(target=drain, args=(process.stdout, stdout), daemon=True),
            threading.Thread(target=drain, args=(process.stderr, stderr), daemon=True),
        ]
        for thread in threads:
            thread.start()
        artifact_done = threading.Event()
        artifact_thread = None
        if "--collect-only" not in argv:
            artifact_thread = threading.Thread(
                target=self._copy_artifacts_while_running,
                args=(argv, artifacts_root, artifact_done),
                daemon=True,
            )
            artifact_thread.start()
        outcome = None
        deadline = started + self.settings.test_sandbox_timeout_seconds
        result = SandboxResult(
            "infrastructure_failure", message="Sandbox process did not report a result"
        )
        try:
            while process.poll() is None:
                if cancel_check and cancel_check():
                    outcome = "cancelled"
                    process.kill()
                    break
                if time.monotonic() >= deadline:
                    outcome = "timed_out"
                    process.kill()
                    break
                time.sleep(0.2)
            process.wait()
            for thread in threads:
                thread.join(timeout=1)
            out = bytes(stdout).decode("utf-8", errors="replace")
            err = bytes(stderr).decode("utf-8", errors="replace")
            if outcome == "cancelled":
                result = SandboxResult(
                    "cancelled",
                    process.returncode,
                    int((time.monotonic() - started) * 1000),
                    stdout=out,
                    stderr=err,
                    message="Execution was cancelled",
                )
            elif outcome == "timed_out":
                result = SandboxResult(
                    "timed_out",
                    process.returncode,
                    int((time.monotonic() - started) * 1000),
                    stdout=out,
                    stderr=err,
                    message="Sandbox execution exceeded the configured timeout",
                )
            else:
                if overflow.is_set():
                    result = SandboxResult(
                        "error",
                        process.returncode,
                        stdout=out,
                        stderr=err,
                        message="Sandbox output exceeded the configured limit",
                    )
                elif (
                    process.returncode == 125
                    or "Unable to find image" in err
                    or "Cannot connect to the Docker daemon" in err
                ):
                    logger.warning(
                        "Docker sandbox launch failed with exit %s: %s",
                        process.returncode,
                        err.strip()[:500],
                    )
                    result = SandboxResult(
                        "infrastructure_failure",
                        process.returncode,
                        message="Docker could not start the configured test sandbox",
                    )
                else:
                    result = SandboxResult("completed", process.returncode, stdout=out, stderr=err)
        except Exception as exc:  # noqa: BLE001 - supervisor failures must terminate and clean the container
            try:
                process.kill()
            except ProcessLookupError:
                pass
            process.wait()
            result = SandboxResult(
                "infrastructure_failure",
                process.returncode,
                int((time.monotonic() - started) * 1000),
                message=f"Sandbox supervisor failed: {type(exc).__name__}",
            )
        finally:
            artifact_done.set()
            if artifact_thread:
                artifact_thread.join(timeout=5)
            for thread in threads:
                thread.join(timeout=1)
            container_name = argv[argv.index("--name") + 1]
            execution_id = container_name.removeprefix("devpilot-tests-")
            cleanup_confirmed = self._remove_owned_container(container_name, execution_id)
        try:
            cidfile_index = argv.index("--cidfile") + 1
            container_id = Path(argv[cidfile_index]).read_text(encoding="ascii").strip()
        except (ValueError, OSError):
            container_id = None
        result.container_id = container_id
        result.cleanup_confirmed = cleanup_confirmed
        logger.info(
            json.dumps(
                {
                    "event": "sandbox_container_finished",
                    "container_name": container_name,
                    "container_id": container_id,
                    "execution_status": result.status,
                    "cleanup_confirmed": cleanup_confirmed,
                },
                sort_keys=True,
            )
        )
        if not cleanup_confirmed:
            return SandboxResult(
                "infrastructure_failure",
                result.exit_code,
                result.duration_ms,
                result.stdout,
                result.stderr,
                message="Sandbox container cleanup could not be confirmed",
                container_id=container_id,
                cleanup_confirmed=False,
            )
        return result

    def _copy_artifacts_while_running(
        self, argv: list[str], target: Path, done: threading.Event
    ) -> None:
        name = argv[argv.index("--name") + 1]
        pending = {"results.xml", "coverage.json"}
        last_errors = {}
        while pending and not done.is_set():
            for filename in tuple(pending):
                try:
                    copied = subprocess.run(
                        [
                            self.docker_path or "docker",
                            "cp",
                            f"{name}:/results/{filename}",
                            str(target / filename),
                        ],
                        stdin=subprocess.DEVNULL,
                        capture_output=True,
                        text=True,
                        timeout=2,
                        check=False,
                        shell=False,
                    )
                    if copied.returncode == 0 and (target / filename).is_file():
                        pending.remove(filename)
                    else:
                        last_errors[filename] = copied.stderr.strip()[:300]
                except (OSError, subprocess.TimeoutExpired) as exc:
                    last_errors[filename] = str(exc)[:300]
            if pending:
                time.sleep(0.25)
        for filename in pending:
            logger.warning(
                "Could not retrieve sandbox artifact %s before container cleanup: %s",
                filename,
                last_errors.get(filename, "artifact was not available"),
            )

    def _read_artifact(self, path: Path) -> str:
        resolved = path.resolve()
        if path.is_symlink() or resolved.parent != path.parent.resolve() or not path.is_file():
            raise OSError("Unsafe or unavailable sandbox artifact")
        if path.stat().st_size > self.settings.test_sandbox_output_bytes:
            raise OSError("Sandbox artifact exceeded the configured output limit")
        return path.read_text(encoding="utf-8")

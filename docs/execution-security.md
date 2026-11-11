# Test execution security

## Threat model

Submitted source and generated/edited tests may be malicious. They may attempt process creation, resource exhaustion, filesystem access, secret discovery, network exfiltration, fake result output, or exploit the runtime. AI output is untrusted too. The API database and backend credentials must never enter a test container.

## Implemented controls

- Authentication and project/review-finding ownership checks precede persistence and access. Source paths/extensions, UTF-8 text and a 64 KiB input limit are validated; recognizable credentials cause rejection before persistence or AI use.
- Generated code is statically validated. Validation does not make code safe; execution is only dispatched to the separate worker and then to a configured immutable container image.
- Original source and generated test text are stored in the relational database for review/history. Treat database rows/backups as sensitive source code; at-rest encryption and retention are deployment responsibilities.
- Fixed `docker run`/`docker cp` argument arrays use `shell=False`. Requests cannot specify images, commands, dependencies, mounts, or resource limits. Before each launch, the worker checks that Docker's local repository digests contain the exact configured `tag@sha256:...` reference; execution uses `--pull=never`.
- The test subprocess has UID 10001 with no capabilities. A fixed trusted container bootstrap uses UID 0 and only `SETUID`, `SETGID`, and `KILL` capabilities to drop into that account, kill leftover test processes, and copy reports into a root-only bounded results tmpfs. The container uses private PID/IPC namespaces, Docker's default seccomp profile, no network, read-only image filesystem, `no-new-privileges`, process/memory/CPU limits, and bounded tmpfs directories. Only validated source/test input is mounted read-only; no credentials, host paths beyond that temporary input directory, Docker socket, or backend files are mounted.
- Worker wall timeout and combined output/artifact sizes are bounded. Timeouts trigger container removal. Test output cannot decide pass status: parsed JUnit testcase records and actual exit status are required; no collection or result artifacts yields error/infrastructure failure.
- Coverage uses pytest-cov output. Missing/unparseable coverage is null/unavailable. AI failure analysis is allowed only for actual persisted failure/error cases and cannot mutate execution results.
- Execution submissions are idempotent while a generation already has an active job; a database partial unique index protects concurrent submissions. Queued jobs cancel immediately. Running jobs persist a cancellation request that the worker polls while the Docker CLI is active, then kills the CLI and force-removes the deterministic execution container.
- The `test_execution_events` audit stream records queue, claim, container ID, immutable image digest, result metadata, cancellation and stale-recovery outcomes without storing submitted source or test contents. Cleanup is confirmed via Docker removal/inspection and included in the event details.

## Residual risk and deployment requirements

Docker containers share a host kernel and are not by themselves a complete hostile-code boundary. Docker was unavailable during this implementation run. Live checks are authored in `.github/workflows/sandbox-verification.yml`, but the workflow has not run; all runtime isolation, limits, cancellation and cleanup remain unverified. Do not enable production execution until that workflow passes on a trusted image build and the worker is deployed on a dedicated restricted host. Prefer gVisor/Firecracker for hostile multi-tenant workloads. The Docker daemon is privileged infrastructure; worker access to it must be restricted. Resource controls and no-network behavior must be integration-tested on the deployment runtime.

No Node/Jest/Vitest execution, arbitrary dependency installation, JS/TS sandbox, artifact object storage, or hostile-runtime escape testing is implemented. Cancellation and stale-worker recovery are implemented in code but not verified against a live runtime. PostgreSQL remains the production database; SQLite is only for explicit local tests/development.

# Deployment and sandbox verification

## Production targets

- PostgreSQL is required for production. Configure `DATABASE_URL` as `postgresql+psycopg://...`; production rejects SQLite.
- Keep `OPENAI_API_KEY`, `JWT_SECRET`, and PostgreSQL credentials in the deployment secret store. Do not pass them to the test worker's Docker CLI environment.
- Run the API and the separate test worker on a dedicated restricted host. Give the worker access only to the Docker daemon and PostgreSQL permissions it needs. Treat Docker daemon access as privileged host access.

## Sandbox image

The sandbox image is built from `infra/test-sandbox-python/Dockerfile`; the Dockerfile uses a versioned Python slim Debian base and fully pinned Python test dependencies. Build from the repository root:

```sh
docker build --pull -f infra/test-sandbox-python/Dockerfile \
  -t devpilot/test-sandbox-python:0.1 infra/test-sandbox-python
```

Push the image to an approved registry and retain the registry's immutable repository digest. Configure the worker with the full reference:

```text
TEST_SANDBOX_IMAGE=registry.example/devpilot/test-sandbox-python:0.1@sha256:<verified-repository-digest>
```

The worker checks Docker's local `RepoDigests` for that repository digest and starts containers with `--pull=never`. A mutable tag alone is rejected. The successful [verification run #24](https://github.com/Charith003/AI-Powered-Developer-Productivity-Assistant/actions/runs/43042010217) produced separate runtime and worker image digests: `sha256:a2a9ca4cad5445c79f21ca9120e43ee1617b72213abec037d10accf32f885bd9` and `sha256:28eb4073bfdf1ee0400dc66a363314cff20d3a933666dd05eea0ec265e4ed454`. Both belong to temporary job-local registries and are verification evidence only. Release deployment requires rebuilding/pushing to an approved persistent registry and reviewing that registry's immutable RepoDigest.

## Docker-enabled verification

The `Sandbox verification` workflow runs on pull requests and manual dispatch. It separates PostgreSQL migration checks, live Docker sandbox checks, PostgreSQL worker integration, and backend/frontend checks into independent jobs. The two Docker jobs each rebuild the image, push to a temporary local registry, verify the immutable RepoDigest and run their live test suite. A final aggregation job requires every suite to succeed. Sanitized JUnit, runtime logs, image configuration and digest evidence are uploaded for 14 days. A failure in one suite does not prevent the other independent suites from producing evidence.

Manual equivalent after configuring Docker, PostgreSQL and the digest:

```sh
cd backend
python -m pip install -e '.[dev]'
python -m alembic upgrade head
DEVPILOT_SANDBOX_RUNTIME=1 DEVPILOT_POSTGRES_INTEGRATION=1 \
  TEST_SANDBOX_IMAGE='registry.example/devpilot/test-sandbox-python:0.1@sha256:<verified-repository-digest>' \
  python -m pytest -q -s tests/test_sandbox_runtime.py tests/test_postgres_worker_integration.py
```

Run #24 passed all 13 actual Docker runtime scenarios and all 4 PostgreSQL worker integration tests. The runtime probes cover Pytest pass/fail/skip/collection behavior, coverage, timeout, output and resource limits, network/filesystem/environment isolation, non-root test execution, cancellation, cleanup, concurrent worker claims and stale-container recovery. Review the evidence and residual Docker host-kernel risk; ordinary Docker containers are not equivalent to a dedicated VM or Firecracker. gVisor is not configured by this project and is not claimed as verified.

## Local development

Docker is optional for the API and frontend. Use an installed local PostgreSQL service for production-like development; explicitly configured SQLite is only for unit tests/local development. Test execution without Docker or without a valid digest returns an infrastructure failure and never falls back to host execution.

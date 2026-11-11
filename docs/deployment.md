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

The worker checks Docker's local `RepoDigests` for that repository digest and starts containers with `--pull=never`. A mutable tag alone is rejected. Do not promote an image until `.github/workflows/sandbox-verification.yml` passes and its uploaded image digest and test artifacts have been reviewed. The current development environment cannot build the image; this document intentionally contains no invented digest. Each CI run currently uses an ephemeral local registry and uploads that run's image reference/digest as evidence; release deployment should use a trusted persistent registry.

## Docker-enabled verification

The `Sandbox verification` workflow runs on pull requests and manual dispatch using an Ubuntu runner with Docker Engine and a PostgreSQL 16 service. It builds the image, pushes it to a temporary local registry to obtain a real immutable repository digest, verifies image metadata, applies the complete migration chain and an upgrade from revision `0004_test_generation`, then runs backend regression tests, live container probes and real PostgreSQL worker tests. Sanitized JUnit, lifecycle logs, image configuration and digest evidence are uploaded for 14 days. Mandatory integration test failures fail the workflow; the tests are not silently skipped in this job.

Manual equivalent after configuring Docker, PostgreSQL and the digest:

```sh
cd backend
python -m pip install -e '.[dev]'
python -m alembic upgrade head
DEVPILOT_SANDBOX_RUNTIME=1 DEVPILOT_POSTGRES_INTEGRATION=1 \
  TEST_SANDBOX_IMAGE='registry.example/devpilot/test-sandbox-python:0.1@sha256:<verified-repository-digest>' \
  python -m pytest -q -s tests/test_sandbox_runtime.py tests/test_postgres_worker_integration.py
```

The runtime probes cover actual Pytest pass/fail/skip/collection behavior, coverage, timeout, output and resource limits, network/filesystem/environment isolation, non-root test execution, cancellation, cleanup, concurrent worker claims and stale-container recovery. Review the evidence and residual Docker host-kernel risk; ordinary Docker containers are not equivalent to a dedicated VM or Firecracker. gVisor is not configured by this project and is not claimed as verified.

## Local development

Docker is optional for the API and frontend. Use an installed local PostgreSQL service for production-like development; explicitly configured SQLite is only for unit tests/local development. Test execution without Docker or without a valid digest returns an infrastructure failure and never falls back to host execution.

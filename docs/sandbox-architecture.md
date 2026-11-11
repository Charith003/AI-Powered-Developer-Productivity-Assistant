# Test sandbox architecture

```mermaid
sequenceDiagram
  participant UI as Next.js workspace
  participant API as FastAPI
  participant DB as PostgreSQL
  participant Worker as Separate test worker process
  participant Runtime as Docker runtime
  UI->>API: Submit source / edit tests / queue execution
  API->>DB: Persist generation and queued job
  API-->>UI: Job ID (202)
  Worker->>DB: Claim queued job with row lock
  Worker->>Runtime: Fixed Docker argv; no shell
  Runtime->>Runtime: Collect tests, then run Pytest in disposable container
  Runtime-->>Worker: Bounded JUnit/coverage artifacts and output
  Worker->>DB: Persist truthful status, testcase results and coverage
  UI->>API: Poll persisted execution state
```

The API never imports or executes generated test modules. Only the separate worker claims execution jobs. Before each launch, the worker inspects the configured `tag@sha256:...` reference and requires the exact repository digest in Docker's local `RepoDigests`; it uses `--pull=never`. The image defaults to UID 10001 and includes pinned Python/Pytest dependencies. The fixed trusted bootstrap runs as UID 0 with only `SETUID`, `SETGID`, and `KILL` capabilities, then drops supplementary groups and capabilities before collection and test code run as UID 10001. It kills remaining test processes and copies result files into a root-only results tmpfs before the worker retrieves them. Containers use private PID and IPC namespaces, no network, a read-only image root, `no-new-privileges`, Docker's default seccomp filter, CPU/memory/PID limits, bounded tmpfs mounts, no Docker socket mounts, no user-controlled images, and fixed argv. Source files enter only through a temporary read-only bind mount and are copied into bounded ephemeral workspace storage. The test process cannot write the protected result directory. Container IDs, digest, lifecycle status, and cleanup confirmation are logged and stored as sanitized execution events.

Current defaults: 30-second wall timeout; 256 MiB memory with swap capped to the same value; 1 CPU; 64 processes; 256 file descriptors; core dumps disabled; 16 MiB max file size; 64 KiB combined process output; at most 100 discovered tests; 64 MiB workspace tmpfs (4,096 inodes), 32 MiB `/tmp` (2,048 inodes), and 16 MiB result tmpfs (2,048 inodes). Values are administrator configuration, not request parameters. Docker image must match `<registry/name:tag>@sha256:<64 lowercase hex>`.

Docker and PostgreSQL are not installed in the local Windows development environment. The successful [workflow run #24](https://github.com/Charith003/AI-Powered-Developer-Productivity-Assistant/actions/runs/43042010217) passed PostgreSQL migrations, 13 real Docker runtime scenarios, 4 PostgreSQL worker integration tests, backend/frontend checks, and final evidence aggregation. Each Docker job rebuilt the image, pushed to a temporary job-local registry, pulled the immutable digest reference, and verified `RepoDigests`. Runtime digest: `sha256:a2a9ca4cad5445c79f21ca9120e43ee1617b72213abec037d10accf32f885bd9`; worker digest: `sha256:28eb4073bfdf1ee0400dc66a363314cff20d3a933666dd05eea0ec265e4ed454`. The localhost references are temporary evidence only and must not be used for production. Container isolation is not a complete boundary against hostile code or kernel/runtime vulnerabilities. Production should use patched runtimes and consider gVisor/Firecracker, separate worker hosts, quotas, queue monitoring, and a restrictive host policy. Do not configure the worker on a host whose Docker daemon or image supply chain is not trusted.

## Enabling an execution worker

Build the image from the repository root using `docker build -f infra/test-sandbox-python/Dockerfile -t devpilot/test-sandbox-python:0.1 infra/test-sandbox-python`. Push it to an approved registry, record the returned repository digest, and configure `TEST_SANDBOX_IMAGE=registry.example/devpilot/test-sandbox-python:0.1@sha256:<verified-digest>` in the worker environment. Pre-pull the exact digest on the worker host (execution uses `--pull=never` and verifies local RepoDigests). Run `python -m app.test_generation.worker` from `backend/` with the production PostgreSQL URL and a restricted Docker daemon connection. Do not enable the API or worker until the Docker-enabled workflow has passed and the digest has been reviewed.

No local-process execution fallback exists. Missing Docker/image produces `infrastructure_failure`, never a passing result. JavaScript/Vitest/Jest and other languages are not yet enabled.

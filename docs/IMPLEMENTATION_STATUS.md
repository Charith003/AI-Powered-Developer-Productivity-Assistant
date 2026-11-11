# DevPilot AI implementation status

## Repository state
- The existing Next.js App Router frontend and FastAPI backend are extended in place; the established architecture, authentication and project workflows remain intact.
- PostgreSQL remains the production database. Docker is unavailable here. For local development, use an installed PostgreSQL server with `DATABASE_URL=postgresql+psycopg://...`, or explicitly select SQLite with `DATABASE_URL=sqlite+pysqlite:///./devpilot-local.db`. Production startup rejects SQLite.
- AI provider configuration is explicit. No live provider key or local PostgreSQL server was available for this verification.

## Phase 1 — Foundation: complete
- Frontend and backend dependencies are defined; Next.js build and FastAPI startup/test configuration are verified.
- Health/status endpoints, SQLAlchemy database health check, and Alembic migration framework are implemented.
- Alembic upgrades a fresh local SQLite test database through the current head (`0007_raw_coverage_artifact`); PostgreSQL remains the production target and needs the new Docker-enabled CI run before verification.

## Phase 2 — Authentication and project management: complete
- Registration, login, profile read/update, refresh rotation, logout, Argon2id password hashing, and signed access tokens are implemented.
- Refresh tokens are persisted/revocable. Project CRUD, review association and access are scoped to the owner.
- The frontend uses a same-origin API proxy, HttpOnly session cookies, and protected workspace routes.

## Phase 3 — AI provider integration: complete
- OpenAI Responses API integration uses a provider interface, structured output, timeout, bounded retries, and safe error normalization.
- Missing keys are reported as configuration errors; no fake authentication or fallback mock is used in production.
- Token usage metadata is persisted without prompts/completions. Cost estimates appear only when explicit model pricing is configured.
- Authenticated status, generation, paginated history, and aggregate usage endpoints enforce user and project ownership.

## Phase 4 — AI-powered code review engine: implemented
- Authenticated users can submit bounded source files for static analysis and optional structured AI review. Reviews, source hashes, analyzer execution statuses, findings, feedback, and patch audit events are persisted.
- Language detection and validation cover Python, JavaScript, TypeScript, Java, C, and C++; review paths and credentials are validated/redacted. Analyzer subprocesses use fixed argument arrays, temporary source copies, time/output limits, and never execute reviewed application code.
- Static and AI findings share a normalized model; AI observations require source evidence. History, persisted dashboard metrics, analyzer/category/status filters, owner-scoped project association, and finding status transitions are implemented.
- AI-generated patch previews require explicit approval to update only the stored uploaded-source snapshot. Rollback is explicit and hash-checked. No repository or working-tree files are modified by review patching.
- MCP is not implemented. Code review service methods provide a transport-independent foundation for a later adapter.

## Verification performed
- Backend: `python -m pytest -q` — **26 passed** after the rollback regression test was strengthened. Ruff lint/format passed earlier in the implementation; the final shell's Windows Python launcher pointed to a missing interpreter, so Ruff could not be rerun after the last small edits.
- Frontend: `npm run lint` and `npm run build` passed for the implemented review and dashboard screens.
- Analyzer integration tests execute Ruff, ESLint, and the TypeScript compiler in this environment. Other tools report per-review availability; Java/Checkstyle and C/C++ compiler availability are environment-dependent.
- Migration test upgrades a fresh SQLite database to Alembic head and verifies review schema columns/tables. This confirms local migration behavior, not PostgreSQL connectivity.
- No live PostgreSQL, Docker, or OpenAI API key was available. Live database/provider integration remains unverified. Analyzer subprocesses have time and output limits, but are not isolated with OS-level CPU/memory/network sandboxing.
- A non-blocking Starlette/httpx TestClient deprecation warning may be emitted.

## Phase 5 — Automated test generation and isolated execution: in progress
- Implemented Python/Pytest test generation through the existing structured AI provider, AST-based target/case planning, optional linked Phase 4 regression context, persisted AI usage, safe-input checks, test editing, static syntax/import/assertion/duplicate checks, and authenticated owner-scoped APIs.
- Added database-backed execution queue and separate worker module. The worker performs Pytest collection and then actual test execution only in a configured digest-pinned container. Container command policy includes no network, non-root UID, read-only base filesystem, dropped capabilities, `no-new-privileges`, CPU/memory/PID/wall-time/output limits, bounded tmpfs and read-only source input. Missing Docker/image is saved as infrastructure failure with zero results; no local execution fallback exists.
- Added JUnit test parsing, actual pytest-cov JSON parsing, failure records/tracebacks, coverage/uncovered line results, optional AI failure recommendations based on persisted failures, cancellation for queued jobs, and actual aggregate dashboard metrics.
- Frontend `/test-generator` supports source submission, project selection, generated test editing, validation, queued execution polling, result and coverage display, failure explanation requests, and generation history.
- Scope is currently Python/Pytest. JS/TS/Jest/Vitest and Java/C/C++ testing are explicitly unsupported. Project-file browsing, artifact object storage, and richer file-level coverage UI remain future work.

## Phase 5.1 — Sandbox verification, hardening and execution completion: in progress
- Added migration `0005_execution_reliability`: idempotent active execution per generation enforced in API and by a partial unique index; running jobs expose a persisted cancellation request. Migration `0006_execution_audit_events` stores sanitized queue, claim, container, cancellation and recovery lifecycle evidence. Migration `0007_raw_coverage_artifact` retains bounded raw coverage JSON for owner-scoped comparison with parsed results.
- The worker verifies the configured tag plus immutable digest against the image's local repository digests before running. Container names are derived from validated execution IDs; cancellation removes the live container and records cleanup confirmation, and stale jobs attempt deterministic orphan removal.
- Frontend exposes cancellation requests while work is queued/running and shows the pending cancellation state.
- Added opt-in live Docker scenario tests, PostgreSQL worker integration tests, and `.github/workflows/sandbox-verification.yml`. The workflow builds the image, pushes it to an ephemeral local registry to obtain an immutable repository digest, verifies it, then runs Docker scenarios and PostgreSQL worker tests. It also performs a PostgreSQL upgrade from revision `0004_test_generation`.
- Docker, Podman, nerdctl, runsc and Firecracker are unavailable locally. The image has not been built here, the CI workflow has not been run, and no sandbox scenario or generated test body has been executed in this environment. Runtime isolation, actual cancellation, timeout/resource enforcement, PostgreSQL worker behavior and recovery therefore remain unverified. No digest or CI result is claimed.

## Verification and remaining Phase 5 gate
- Backend: `python -m pytest -q` — **35 passed, 17 skipped**, with one non-blocking Starlette/httpx deprecation warning. The skips are all Docker/PostgreSQL live integration scenarios because the local runtime flags/services are unavailable; they are mandatory and explicitly enabled in the new CI job. SQLite migrations and lifecycle APIs include revision `0007`.
- Backend Ruff: `ruff check app tests migrations scripts` and `ruff format --check app tests migrations scripts` — passed after formatting the checked Python files.
- Frontend `npm run lint` and `npm run build` passed. The production build completed compilation, type checking, static generation, and build traces.
- Docker is not installed and no digest-pinned sandbox image is configured. The sandbox image was not built or run; **zero submitted/generated test cases were actually executed** in this environment. Successful execution, actual worker test counts/coverage, network isolation, quotas, timeout cleanup, and runtime security are **not verified**. Runtime tests are authored but remain unexecuted locally. No live PostgreSQL or OpenAI call was available either; the AI generation test uses a mocked provider and does not claim a live AI response.
- This phase is not complete until the new Docker-enabled workflow has actually passed and produced a digest and evidence artifacts. Its test code is not verification evidence by itself.

## Exact next development milestone
Run `.github/workflows/sandbox-verification.yml` on GitHub Actions and fix any real failures. Review the attached digest and evidence artifacts, then configure deployment `TEST_SANDBOX_IMAGE` with a trusted registry image and its verified immutable repository digest. Confirm production PostgreSQL and worker operation before marking Phase 5.1 complete. Only then begin **Phase 6 — repository integration and pull-request workflows**, with authorized Git connections and read-only diff review/test generation.

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
- Added opt-in live Docker scenario tests, PostgreSQL worker integration tests, and `.github/workflows/sandbox-verification.yml`. Migration checks, runtime checks, worker integration, and backend/frontend checks now run as independent jobs; an aggregate job fails if any mandatory suite fails. Each Docker job independently rebuilds, pushes to a per-job ephemeral local registry, records the returned digest, pulls the immutable RepoDigest reference, verifies that reference, and passes that exact reference to the tests.
- Expanded PostgreSQL worker integration coverage to submit through the protected FastAPI queue endpoint, verify a repeat request reuses the same active execution, reject a different user's request for the generation, and confirm the queue audit event before real worker execution.
- Fixed the legacy migration verifier's psycopg connection parsing by converting SQLAlchemy `postgresql+psycopg` URLs to psycopg-compatible `postgresql` URIs through `make_url`, without logging credentials. The verifier now drops its temporary database from a `finally` block and asserts the duplicate-job reconciliation, active-generation index, audit table, and raw coverage column.
- Replaced the Node 20 based checkout/setup-python/upload-artifact actions with reviewed, commit-pinned Node 24 compatible releases. The workflow's Node setup action is also pinned to a reviewed commit.
- This Windows environment has no Docker CLI or PostgreSQL client/server. The installed Python launcher points to an inaccessible Windows Store interpreter, so backend pytest, Ruff, and PostgreSQL verification could not be executed locally. The updated workflow has not yet run against this revision; therefore the live image build, sandbox scenarios, migrations, and worker integration remain unverified here. No new image digest or passing CI result is claimed. The previous workflow run stopped at the PostgreSQL URL parsing error before reaching any live test.

## Verification and remaining Phase 5 gate
- Previous backend run: `python -m pytest -q` — **35 passed, 17 skipped**. Those skips were the 13 live Docker sandbox cases and 4 Docker/PostgreSQL worker cases; none are counted as successful runtime evidence.
- Current frontend `npm run lint` and a subsequent clean `npm run build` pass. The first production-build attempt hit a transient Windows `EPERM` while Next.js copied standalone build traces, but rerunning the build completed successfully.
- Frontend `npm ls --depth=0` verified the existing dependency tree. `npm ci` could not complete in this restricted environment, so dependency installation from the lockfile remains unverified. Backend pytest and Ruff commands could not start because the configured Python launcher resolves to an inaccessible Windows Store interpreter.
- Docker and PostgreSQL are unavailable locally and the updated workflow has not yet run. The sandbox image was not rebuilt here; **zero Docker-submitted cases have been executed here**, and no new digest, CI test count, coverage result, isolation result, or worker result is claimed. The old digest is stale for deployment decisions. A separate trusted persistent registry must be approved and configured for production; the workflow's temporary localhost registry is CI-only.
- This phase is not complete until the new Docker-enabled workflow has actually passed and produced a digest and evidence artifacts. Its test code is not verification evidence by itself.

## Exact next development milestone
Run the updated `.github/workflows/sandbox-verification.yml` on GitHub Actions, fix all failures, and review the attached migration, JUnit, runtime, worker, and RepoDigest evidence. Do not mark Phase 5.1 complete until all four required jobs pass and the aggregate job succeeds. Then configure deployment `TEST_SANDBOX_IMAGE` from a trusted persistent registry (never the temporary localhost registry), and confirm production PostgreSQL and worker operation. Only then begin **Phase 6 — repository integration and pull-request workflows**, with authorized Git connections and read-only diff review/test generation.

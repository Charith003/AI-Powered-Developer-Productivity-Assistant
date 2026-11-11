# Test plan

## Automated backend
Run from `backend/`: `python -m pytest -q`, `python -m ruff check app tests migrations`, and `python -m ruff format --check app tests migrations`.

Coverage includes auth/project regression, provider construction and missing-key behavior, structured output, timeout/rate-limit/API failures, bounded retries, safe error handling, cost estimates, usage persistence and user/project authorization, and Alembic upgrade/schema checks.

Phase 4 review coverage adds actual Ruff and ESLint/TypeScript compiler runs when installed, extension/shebang detection, path traversal and credential-file rejection, secret redaction and evidence checks, persisted findings and review analytics, user/project isolation, missing analyzer reporting, mocked structured AI with usage tracking, finding status transitions, patch diff preview, explicit approval, and rollback.

Phase 5 adds AST planning, invalid source handling, static Pytest validation and tautology detection, structured generation through a mocked provider, edit/validate/queue APIs, owner isolation, JUnit and coverage parsing, sandbox command policy assertions, migration schema checks, idempotent active-job submission, cancellation and stale recovery. `test_sandbox_runtime.py` contains actual Docker scenarios for pass/skip, assertion failure, syntax/import/empty collection, timeout, output/memory/process limits, network/filesystem/environment isolation, non-root execution, seccomp, digest, and cleanup. `test_postgres_worker_integration.py` exercises actual worker execution, result/coverage persistence, active-job uniqueness, competing workers, cancellation and orphan recovery using PostgreSQL and Docker.

Latest successful backend unit job in [workflow run #24](https://github.com/Charith003/AI-Powered-Developer-Productivity-Assistant/actions/runs/43042010217): **35 passed, 19 skipped**. The opt-in live suites were executed separately in that workflow: **13 Docker runtime cases passed** and **4 PostgreSQL worker integration tests passed**. Ruff lint/format, frontend `npm ci`, lint and production build all passed. The local Windows Python launcher still resolves to an inaccessible Store interpreter, and Docker/PostgreSQL are unavailable locally; local frontend lint/build passed but local lockfile installation could not run in the restricted network environment.

The PostgreSQL migration job passed fresh-head migration, downgrade/upgrade from `0004_test_generation`, and populated legacy duplicate-job reconciliation. The live runtime job passed `tests/test_sandbox_runtime.py`; the worker job passed `tests/test_postgres_worker_integration.py` against a real PostgreSQL service and Docker. Worker integration submits jobs through the authenticated HTTP queue route, checks duplicate submissions and ownership, then verifies real execution, cancellation, stale recovery, result and coverage persistence. Both Docker jobs rebuilt and verified immutable image digests against RepoDigests. CI's temporary localhost registry must never be used as a production image reference.

## Frontend
Run from `frontend/`: `npm run lint` and `npm run build`. Verify the AI settings screen reads real status, summary, and history endpoints and renders empty/configuration states.

## Environment integration
With local PostgreSQL: configure a PostgreSQL `DATABASE_URL`, apply migrations, call `/api/v1/health/database`, then exercise auth, project CRUD, and AI status/usage. With an authorized OpenAI key, perform a live structured generation smoke test and confirm token usage is recorded without prompt content. The `sandbox-verification` workflow supplies Docker and PostgreSQL and runs all live mandatory scenarios; a skipped local integration module is not a pass. SQLite is suitable for local unit tests but does not validate PostgreSQL connectivity or production-specific behavior.

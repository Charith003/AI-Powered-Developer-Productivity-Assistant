# Database design

SQLAlchemy models and Alembic migrations define `users`, `projects`, `refresh_tokens`, and `ai_usage`. PostgreSQL is required in production. SQLite is an explicit local development/test option and is never an implicit production fallback.

`ai_usage` fields: UUID id, user FK, nullable project FK, provider, model, feature, nonnegative input/output/total token counts, nullable decimal USD estimate, status, nonnegative duration in milliseconds, and timestamp. Constraints enforce token arithmetic and known status values. Indexes support user/project history and provider/model reporting. Deleting the associated user or project cascades usage records. The model intentionally has no prompt or answer column.

Apply schema changes with `alembic upgrade head`. The migration test runs Alembic against an isolated temporary SQLite database; PostgreSQL migration execution is still required in a PostgreSQL-enabled environment before release.

## Code review tables (revision `0003_code_reviews`)
- `code_reviews`: owner and optional project references, language, status, analyzer configuration/status JSON, summary, severity counters, timing, and lifecycle timestamps. User deletion cascades; project deletion detaches a review.
- `review_files`: validated relative path, uploaded source snapshot, SHA-256, and timestamp. Review deletion cascades. Snapshots support hash-checked preview/application and remain private to the owning review.
- `review_findings`: review FK, line/column, evidence, recommendation, severity/category, source origin (`static`/`ai`), specific analyzer name, rule ID, confidence, lifecycle status, and timestamps. Constraints validate enums, line ranges, and confidence.
- `review_feedback`: owner-scoped 1–5 rating and comment.
- `review_patch_events`: audit trail for preview, approved apply-to-upload, and rollback events. Patch events are private to findings in an owned review.

Indexes cover review history per user/project and finding filters per review. All five tables and constraints are created by Alembic revision `0003_code_reviews`; no `create_all` production shortcut is used.

## Test generation and execution (revision `0004_test_generation`)
- `test_generations`: owner, optional project and Phase 4 review-finding link, source path/content, language/framework, structured plan, generated test content, validation errors/status, model/token metadata and timestamps. Current constraints permit Python/Pytest only. User deletion cascades; project/finding deletion detaches the optional relation.
- `test_executions`: generation and owner, an immutable generated-test content snapshot plus source/test SHA-256 fingerprints, queued/running/terminal status, real testcase counts, nullable actual total/file line and branch coverage, uncovered lines JSON, bounded stdout/stderr, exit code, timing, infrastructure details and AI failure recommendations. The worker checks the fingerprints before running so later edits cannot change a queued job. Null coverage means unavailable, never zero by default. Execution history is append-only per run.
- `test_case_results`: per-run JUnit result name/file/status/duration and bounded error/traceback. Large raw artifact blobs are not stored in indexed columns.

Alembic revision `0004_test_generation` creates these tables and owner/generation/status indexes. Execution is an asynchronous database queue consumed by the separate worker. PostgreSQL is required in production; the test suite exercises schema upgrades on a temporary SQLite database only.

## Execution reliability and audit events (revisions `0005_execution_reliability` and `0006_execution_audit_events`)
- Revision `0005` adds `cancel_requested` and a partial unique index allowing one queued/running execution per generation. The API also returns an already-active execution for duplicate submissions.
- Revision `0006` adds `test_execution_events`, a sanitized lifecycle audit stream keyed to an execution and ordered by timestamp. It records queue, worker claim, container completion (container ID, image digest, exit/status and cleanup confirmation), cancellation and stale recovery metadata. It does not store source or generated test contents.
- Revision `0007` adds nullable bounded `coverage_artifact` text so the original pytest-cov JSON can be compared with parsed coverage; the owner-scoped raw coverage endpoint exposes it only for its execution.
- PostgreSQL enforcement and concurrent worker behavior are exercised in the Docker-enabled CI workflow; local SQLite migration coverage alone is not evidence for PostgreSQL semantics.

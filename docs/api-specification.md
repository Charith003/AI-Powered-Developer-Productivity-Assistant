# API specification

All application routes use `/api/v1`. Protected routes require the backend bearer access token; browser use is through the same-origin frontend proxy and HttpOnly session cookies. AI errors use `{ "error": { "code": "...", "message": "..." } }`.

## Authentication and projects
Existing auth routes: `POST /auth/register`, `/auth/login`, `/auth/refresh`, `/auth/logout`; `GET/PATCH /auth/me`. Existing project routes: `GET/POST /projects`, `GET/PATCH/DELETE /projects/{project_id}`. Project data is owner-scoped.

## AI routes
- `GET /ai/status`: provider, configured model, embedding model, readiness flag, and safe configuration message. Requires authentication.
- `POST /ai/generate`: body `{ "prompt": "...", "project_id": "optional UUID" }`; returns `{ "answer": "...", "key_points": [] }`. Persists usage metadata only.
- `GET /ai/usage?limit=20&offset=0&project_id=...`: authenticated user's newest usage rows, limit 1–100, optionally restricted to an owned project.
- `GET /ai/usage/summary?project_id=...`: request/success/failure counts, token totals, and optional configured-price estimate.

Generation errors include `ai_not_configured` (503), `ai_rate_limited` (429), `ai_timeout` (504), `ai_provider_error` (502), and `ai_invalid_output` (502). Project references not owned by the caller return 404. No prompt or completion is returned in usage records.

## Code review routes
- `POST /reviews`: JSON `{ "title": "Review", "project_id": null, "language": "auto", "files": [{"path":"src/example.py","content":"..."}], "analyzers": null, "ai_enabled": true }`. Returns a persisted review with analyzer execution statuses and normalized findings. Source limits: 1–10 files, 160-character paths, 64 KiB per file, 256 KiB total. `analyzers: null` chooses language defaults; empty analyzer lists are rejected.
- `GET /reviews`: pagination (`limit`, `offset`), `search`, `project_id`, `language`, `review_status`, `severity`, `created_from`, and `created_to` filters.
- `GET /reviews/summary`: owner-scoped counts by severity, open findings, recent reviews, and daily counts for the last seven days.
- `GET /reviews/{review_id}`: authorized metadata, tool statuses, file paths and hashes, and findings.
- `GET /reviews/{review_id}/findings`: optional `severity`, `category`, `file_path`, `analyzer` (for example `ruff`, `eslint`, `tsc`, or `ai`), and `status` filters. The `source` field separately identifies `static` versus `ai` origin.
- `PATCH /reviews/{review_id}/findings/{finding_id}`: `{ "status": "accepted|dismissed|fixed" }`, with validated transitions.
- `POST /reviews/{review_id}/findings/{finding_id}/patch`: generate a unified-diff preview; no write is performed.
- `POST /reviews/{review_id}/findings/{finding_id}/patch/apply`: requires `{ "approved": true }`, rechecks source hash and changes only the database copy of uploaded source.
- `POST /reviews/{review_id}/findings/{finding_id}/patch/rollback`: requires explicit `{ "approved": true }` and restores the prior uploaded-source snapshot if its hash is unchanged.
- `POST /reviews/{review_id}/feedback`: `{ "rating": 1, "comment": "..." }`.

Review creation is synchronous for the deliberately bounded file count, source size, analyzer timeout and AI input budget. Individual analyzers report `completed`, `failed`, `timeout`, `unavailable`, or `unsupported`; a diagnostic exit code is preserved and does not by itself mean tool execution failed.

## Test generation routes (Phase 5)
- `POST /tests/generate`: authenticated JSON includes optional `project_id`, optional owned `review_finding_id`, `source_path`, `source_content`, `language` (`auto` or `python`), `framework` (`pytest` only), requested categories, and title. Reuses Phase 3 provider and usage records. Currently supports Python/Pytest only; unsupported frameworks return 422.
- `GET /tests`: owner-scoped pagination (`limit`, `offset`) with optional project/language/framework/date filters. `GET /tests/summary` returns persisted generation/execution counts, completed test totals, actual average coverage (null if unavailable), and recent executions.
- `GET /tests/{generation_id}` returns generated test and plan, never source content. `POST /tests/{generation_id}/validate` performs static syntax/import/target/test/unsafe-pattern checks. `PATCH /tests/{generation_id}` saves user-edited test code and revalidates it.
- `POST /tests/{generation_id}/execute` requires valid static validation and returns HTTP 202 with a queued execution ID. A separate `python -m app.test_generation.worker` process claims jobs; it verifies the configured immutable image digest and runs collection/execution in Docker. Duplicate submissions return the active job. `GET /tests/executions/{execution_id}` polls persisted status; `GET /tests/{generation_id}/executions` returns history; `/cases` and `/coverage` return normalized actual results; `/coverage/raw` returns retained raw coverage JSON; `/events` exposes the owner's sanitized lifecycle audit. `POST /tests/executions/{execution_id}/cancel` cancels queued jobs or requests live worker/container cancellation.
- `POST /tests/executions/{execution_id}/analyze-failures` requires persisted actual failed/error test cases, calls the existing structured AI provider, tracks usage, and returns recommendations labeled unverified.

All test routes enforce user ownership; project and linked review findings are checked before generation. Sandbox absence/image configuration failure is persisted as `infrastructure_failure`, with no pass or coverage claim. The endpoint never falls back to in-process or local execution.

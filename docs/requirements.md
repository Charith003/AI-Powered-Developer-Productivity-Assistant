# Requirements

## Implemented scope
- Browser clients register and sign in through the backend; credentials are hashed using Argon2id. Access and rotating refresh tokens support protected routes and logout.
- Users can create, list, read, update, and delete their own projects. Cross-user access is denied.
- An authenticated user can inspect AI provider readiness, submit an engineering prompt for a structured response, and review their own persisted request usage.
- AI usage includes provider/model/feature, token counts, estimated cost when configured, status, duration, timestamps, user and optional project association. Prompt and response content are excluded.

## Runtime configuration
- Required auth: `JWT_SECRET` (at least 32 characters).
- Database: PostgreSQL URL for production; explicitly selected SQLite may be used in local development/tests only.
- AI: `AI_PROVIDER=openai`, `OPENAI_API_KEY`, `OPENAI_MODEL`, `OPENAI_EMBEDDING_MODEL`, `AI_REQUEST_TIMEOUT`, `AI_MAX_RETRIES`, `AI_MAX_OUTPUT_TOKENS`, and optional per-model `AI_MODEL_PRICING_JSON`.
- Missing AI credentials produce a clear configuration status and structured API error. They are not replaced with fake authentication or a fabricated answer.

## Out of scope
Repository ingestion, RAG, broad security scanners, and multi-provider support remain future workflows. Code execution is limited to the Python/Pytest Phase 5 workflow and must be enabled only through the documented isolated worker/sandbox.

## Phase 4 code review
- Authenticated users submit one to ten UTF-8 source files (up to 64 KiB each, 256 KiB total), with one detected/confirmed language and optional owned project association.
- Reviews execute configured real static tools in a temporary directory and report per-tool availability, status, exit code, and duration. Requested tools are never silently omitted.
- AI review is optional and uses the existing provider; the source budget is bounded to 48,000 characters, likely credential strings are redacted, and each AI finding must quote matching source evidence and line range.
- Findings and review summaries persist. AI-originated observations remain distinct from analyzer findings.
- Suggested patches are diff previews. An explicit approval applies only to the stored uploaded-source snapshot, with source-hash checking, audit events, and rollback.
# Phase 5 automated test generation
- Authenticated generation currently supports Python/Pytest, AST test planning, linked Phase 4 regression context, structured AI generation, code editing and static validation. Unsupported languages/frameworks fail explicitly.
- Execution is asynchronous through a separate worker; only configured digest-pinned sandbox images and fixed commands are allowed. Missing sandbox infrastructure is reported without local execution fallback.
- Persist generations, source, validation, run history, testcase outcomes and actual coverage. Failure explanations use actual persisted failures and remain advisory.

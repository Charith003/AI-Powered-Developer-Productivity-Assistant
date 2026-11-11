# Code review engine

## Workflow
1. `POST /api/v1/reviews` validates source paths (160 characters maximum), UTF-8 text, supported extensions, a single selected/detected language, file count and size. Credential/environment files, path traversal, drive paths, Windows special characters/reserved names, case-insensitive duplicates, and binary NUL data are rejected.
2. Original source snapshots and SHA-256 hashes are stored in `review_files` for history and uploaded-copy patching. Files are copied to a fresh temporary directory for tool execution; that directory is removed after analysis.
3. The registry selects the language's fixed analyzers. Subprocesses receive argument arrays, no shell, a 10-second timeout, 64 KiB aggregate output limit, no stdin, and only the selected temporary files. Source application code is never invoked.
4. Tool JSON/text output is parsed into findings. Exit code 1 from Ruff/Bandit/ESLint/compilers may indicate findings and is retained as a completed run; timeout, unavailable tool, invalid output, and execution failure are separate statuses.
5. Optional AI review uses the Phase 3 provider abstraction and structured Pydantic schema. It is bounded to 48,000 source characters, redacts likely credentials, treats files as untrusted data, and retains observations only when file path, line range, and quoted evidence match the redacted source.
6. Normalized findings persist separately with origin (`static`/`ai`) and analyzer name. Findings with invalid paths/lines/evidence are dropped. Summary counters and owner-scoped history are derived from persisted reviews.
7. AI patch previews are unified diffs. They validate the exact stored file and hash. Explicit approval updates only the database snapshot of uploaded content; an audit event is recorded and an explicit rollback restores the prior snapshot if the applied hash still matches.

## Language and tool matrix

| Language | Default tool selection | Behavior if missing |
|---|---|---|
| Python | Ruff and Bandit; Pylint can be explicitly requested | Report `unavailable`; Ruff/Bandit installed by `.[review]` |
| JavaScript | ESLint with bounded explicit core rules | Report `unavailable` if Node or project ESLint is not present |
| TypeScript | ESLint when TypeScript parser exists; `tsc --noEmit` | Each tool reports separately; parser absence does not hide compiler status |
| Java | Checkstyle only with Java, `CHECKSTYLE_JAR`, and `CHECKSTYLE_CONFIG` | Report configuration/runtime unavailable |
| C / C++ | `clang -fsyntax-only` with GCC fallback | Report compiler unavailable; no binary is linked or run |

The analyzer registry (`app/code_review/registry.py`) can add language/tool mappings without changing API routing. `analyzers/base.py` owns execution and parser adapters. Static severity mapping is conservative: security rules map high, syntax/type errors medium, style/maintainability rules low, and unknown values informational. AI severity and category use the validated shared enum. Findings are deduplicated only on same source, file, line, rule, and title; unrelated overlapping findings remain separate.

## Finding model
Every finding contains `id`, `review_id`, path, optional line range/column, title, description, reasoning, common severity/category, evidence, recommendation, source origin, analyzer, optional rule/confidence, status, and timestamp. Static findings have null confidence. AI observations include an estimate and require evidence validation; that estimate is not a correctness guarantee.

## MCP service methods
`CodeReviewService.analyze_code`, `get_review`, `list_findings`, and `generate_patch` are transport-independent entry points suitable for a later MCP adapter. This phase does not implement an MCP server/client.

## Availability verified in this workspace
Ruff is exercised by an actual analyzer integration test. ESLint and the TypeScript compiler are exercised when their checked-in frontend dependencies and Node runtime are present. Bandit/Pylint, Checkstyle, and C/C++ compiler availability is environment-dependent and returned per review; no results are fabricated to claim support execution.

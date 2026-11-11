# Architecture

The browser communicates with Next.js same-origin routes. The frontend BFF stores backend tokens in HttpOnly cookies and proxies requests to FastAPI. FastAPI authenticates the user, verifies project ownership, calls the provider abstraction, and records usage metadata through SQLAlchemy. Alembic owns schema evolution; PostgreSQL is the production database.

```mermaid
sequenceDiagram
  participant B as Browser
  participant N as Next.js BFF
  participant A as FastAPI
  participant P as OpenAI Responses API
  participant D as PostgreSQL
  B->>N: POST /api/v1/ai/generate (cookie)
  N->>A: Forward with access token
  A->>A: Authenticate and verify project owner
  A->>P: Structured response request (store=false)
  P-->>A: Parsed answer and token usage
  A->>D: Persist usage metadata only
  A-->>N: Structured answer
  N-->>B: JSON response
```

The OpenAI implementation conforms to the provider interface. Provider errors are normalized to safe structured errors; logs contain request metadata and exception class, not prompt content, API keys, or provider error bodies. Missing configuration is exposed in status and reported on generation. Cost estimates are calculated only from explicitly configured model pricing; they are not billing records.

## Code review flow

```mermaid
sequenceDiagram
  participant U as User
  participant A as FastAPI review API
  participant W as Isolated temporary workspace
  participant T as Static analyzer
  participant L as Existing AI provider
  participant D as PostgreSQL
  U->>A: Submit bounded source files and options
  A->>D: Persist review and source snapshots
  A->>W: Write validated relative paths
  A->>T: Fixed argv, shell disabled, timeout and output cap
  T-->>A: Structured diagnostics / execution status
  A->>L: Optional redacted source with untrusted-data instruction
  L-->>A: Structured observations
  A->>A: Validate line range and exact evidence, normalize
  A->>D: Persist analyzer status, findings and summary
  A-->>U: Review details and findings
  U->>A: Explicitly approve patch preview
  A->>D: Update uploaded snapshot only and audit approval
```

The backend analyzer registry maps language to fixed tools. Tool execution never invokes submitted code. Temporary workspaces isolate files from the application checkout, but the current subprocess implementation does not provide OS-level network, memory, or CPU sandboxing; production deployments should run analyzers in a restricted worker/container. Review source snapshots are retained in the database to support safe patch preview/application and are removed when their review is deleted.

## Test-generation and execution flow

```mermaid
sequenceDiagram
  participant U as Authenticated user
  participant A as FastAPI
  participant D as PostgreSQL
  participant W as Separate test worker
  participant C as Isolated Docker test container
  participant AI as Existing structured AI provider
  U->>A: Submit Python source / optional review finding
  A->>A: AST plan and validate bounded input
  A->>AI: Structured Pytest generation (untrusted source as data)
  AI-->>A: Test plan, test code, usage
  A->>D: Persist source, generated code, validation and token metadata
  U->>A: Review/edit tests and request execution
  A->>D: Persist queued execution (202)
  W->>D: Claim job
  W->>C: Collect then execute fixed Pytest command with resource policy
  C-->>W: JUnit, coverage JSON, bounded output
  W->>D: Persist actual status/results/coverage
  U->>A: Optional failure explanation
  A->>AI: Actual failure artifacts and redacted context
  AI-->>A: Recommendations only
```

Execution queue and sandbox controls are described in [sandbox architecture](sandbox-architecture.md) and [execution security](execution-security.md). Python/Pytest is the only enabled framework. Docker was not installed during this run: the worker therefore reports an infrastructure failure and does not execute submitted code on the host. Network/CPU/memory isolation is not live-verified here.

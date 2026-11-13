# Agentic AI Powered Developer Productivity and Code Engineering Platform

Engineering intelligence workspace for evidence-backed code review, tests, debugging and technical knowledge workflows.

## Local development without Docker

### Backend

1. Install Python 3.12+.
2. From `backend/`, create a virtual environment with `py -3.12 -m venv .venv`, then activate it using `.venv\\Scripts\\Activate.ps1` on Windows or `source .venv/bin/activate` on macOS/Linux.
3. Install dependencies with `python -m pip install -e ".[dev,review]"` to enable the Python Ruff and Bandit analyzer adapters. Additional tools such as Pylint, Checkstyle, or clang are optional; the API reports each unavailable tool rather than silently skipping it.
4. Copy `backend/.env.example` to `backend/.env`. A local-only SQLite database is available when explicitly configured as `DATABASE_URL=sqlite+pysqlite:///./devpilot.db`. For PostgreSQL, start a local PostgreSQL server and retain the PostgreSQL DSN. Set `JWT_SECRET` to a random value with at least 32 characters.
5. Run `alembic upgrade head`, then `uvicorn app.main:app --reload` from `backend/`.

SQLite is for explicitly selected development use only. Production requires PostgreSQL; startup rejects SQLite under `ENVIRONMENT=production`.

### Frontend

From `frontend/`, run `npm ci`, then `npm run dev`. Copy `frontend/.env.example` to `frontend/.env.local` and set the server-only `API_URL` if the API URL differs. Open http://localhost:3000.

## Docker Compose

Copy root `.env.example` to `.env`, replace `POSTGRES_PASSWORD` and `JWT_SECRET`, then run `docker compose up --build`. Compose starts PostgreSQL and the API applies Alembic migrations before serving. Docker is optional for local development.

## Verification commands

- Backend: `python -m pytest -q`, `python -m ruff check app tests migrations`, and `python -m ruff format --check app tests migrations` (from `backend/`).
- Frontend: `npm run lint` and `npm run build` (from `frontend/`).
- Database: `alembic upgrade head`; `GET /api/v1/health/database` runs `SELECT 1`.

## Implemented API

- `POST /api/v1/auth/register`, `/login`, `/refresh`, `/logout`
- `GET/PATCH /api/v1/auth/me`
- `GET/POST /api/v1/projects`
- `GET/PATCH/DELETE /api/v1/projects/{project_id}`
- `GET /api/v1/ai/status`, `POST /api/v1/ai/generate`
- `GET /api/v1/ai/usage`, `GET /api/v1/ai/usage/summary`
- `POST /api/v1/reviews`, `GET /api/v1/reviews`, `GET /api/v1/reviews/summary`
- `GET /api/v1/reviews/{review_id}`, `GET /api/v1/reviews/{review_id}/findings`
- `PATCH /api/v1/reviews/{review_id}/findings/{finding_id}`
- `POST /api/v1/reviews/{review_id}/findings/{finding_id}/patch`
- `POST .../patch/apply`, `POST .../patch/rollback`, `POST /api/v1/reviews/{review_id}/feedback`
- `GET /health`, `GET /api/v1/status`, `GET /api/v1/health/database`

AI configuration is backend-only: set `AI_PROVIDER=openai`, `OPENAI_API_KEY`, `OPENAI_MODEL`, `OPENAI_EMBEDDING_MODEL`, `AI_REQUEST_TIMEOUT`, and `AI_MAX_RETRIES` in `backend/.env` or deployment secrets. Optional `AI_MODEL_PRICING_JSON` maps model names to `input_per_million` and `output_per_million` USD values; without a matching entry estimated costs remain null. Missing credentials disable generation with a structured configuration error. AI request history stores token/provider/model/status metadata, not prompts or completions. See [AI requirements](docs/requirements.md), [API specification](docs/api-specification.md), and [implementation status](docs/IMPLEMENTATION_STATUS.md).

Code review submits UTF-8 source in bounded JSON payloads. Available tools run in temporary directories; unavailable tools are reported in the result. Review source snapshots are stored in the configured database for history and patch preview; approved patches update only the uploaded snapshot and can be rolled back. See [the code review engine](docs/code-review-engine.md) and [security limits](docs/security.md).

Passwords use Argon2id. Access JWTs expire in 15 minutes by default. Refresh JWTs are stored by token ID, rotated on use, and revocable. Project lookups are scoped to the authenticated owner. The same-origin Next.js API proxy holds browser tokens in HttpOnly, SameSite cookies and refreshes access tokens on 401 responses. Mutating proxy requests validate Origin, and protected screens require a valid API session.

The frontend can be deployed to Vercel with server-only `API_URL` set to the deployed API origin. Configure `FRONTEND_ORIGIN`, PostgreSQL `DATABASE_URL`, and a strong `JWT_SECRET` on the backend host.






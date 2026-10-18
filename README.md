# CCPA Dark Pattern Auto-Auditor

An AI web agent that browses an e-commerce site the way a shopper would, captures what the shopper sees, and flags possible **dark patterns** from the 13 categories in India's *Guidelines for Prevention and Regulation of Dark Patterns, 2023* (Central Consumer Protection Authority). Every finding is a **machine-generated hypothesis for human review, not a legal verdict**.

Built for AZINHACK 2026 with the **TinyFish** web agent.

## What it does

1. You submit a store URL.
2. A TinyFish agent browses it: product page, cart, checkout summary. It never pays, enters an OTP, logs in, or solves a CAPTCHA.
3. For each step, the screenshot and page HTML are stored (private bucket) and hashed with SHA-256.
4. Gemini analyses each step against the 13-category taxonomy and returns structured findings.
5. Deterministic checks verify each finding against the page text before it is saved.
6. Findings are stored as `PENDING_REVIEW`. Only a human changes that status.

## How the AI is kept honest

| Check | Behaviour |
|---|---|
| DOM quote grounding | A `DOM_TEXT` quote must appear in the captured page text, otherwise the finding is rejected |
| Visual-only findings | Confidence is capped at 0.60 |
| Legal references | Come from our taxonomy, never from the model |
| Prompt injection | Page text is untrusted data, wrapped in random per-call markers |
| Review status | Code never sets a finding to confirmed or rejected |

## Architecture

```
Next.js dashboard (planned) --> FastAPI (token auth, REST + WebSocket)
                                    |
                             Redis + Celery worker
                                    |
                               Audit runner
              +---------------------+---------------------+
        TinyFish Agent API        Gemini          Supabase (Postgres + private Storage)
```

- `backend/app/services/tinyfish.py`: TinyFish Agent API client (`POST /v1/automation/run-async`, `GET /v1/runs/{id}`, step screenshot and HTML downloads, cancel).
- `backend/app/services/evidence.py`: evidence capture, hashing, private storage.
- `backend/app/services/gemini.py` and `backend/app/schemas/compliance.py`: analysis and grounding.
- `backend/app/services/audit_runner.py`: claim, run, capture, analyse, save.
- `backend/app/api/`: REST routes and the progress WebSocket.
- `backend/app/workers/`: Celery app and task.
- `database/migrations/`: Postgres schema (Supabase).

## Safety design

- Target URLs must be public `http(s)` on ports 80 or 443; localhost and private IPs are refused; redirects are not followed.
- The agent goal forbids purchases, payment details, OTPs, logins and CAPTCHA bypass, and an action guard stops a run that attempts one.
- Evidence is stored in a private bucket; the database holds object paths and hashes only.
- All API routes need a bearer token (constant-time compare); the WebSocket authenticates with a first message, never a URL token, and checks the origin.
- Secrets live only in `backend/.env` (git-ignored). Nothing secret is ever sent to browser code.
- A session is claimed atomically (`QUEUED` to `RUNNING`), so a redelivered job never starts a second paid run.

## Setup

**Prerequisites:** Python 3.11+ (developed on 3.13), Redis, a Supabase project, a TinyFish API key, a Gemini API key.

```bash
git clone https://github.com/riyacore404/ccpa-dark-pattern-auditor.git
cd ccpa-dark-pattern-auditor/backend

python3.13 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

cp .env.example .env      # then edit .env by hand; never commit it
```

Fill in `backend/.env`:

- `API_ACCESS_TOKEN`: generate with `python -c "import secrets; print(secrets.token_urlsafe(32))"`
- `DATABASE_URL`: the Supabase **session pooler** connection string (port 5432, no `?pgbouncer=true`)
- `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`: server-side only
- `TINYFISH_API_KEY`
- `GEMINI_API_KEY` and `GEMINI_MODEL` (a vision-capable model of your choice)

Database and storage:

1. In the Supabase SQL editor run `database/migrations/001_initial_schema.sql`, then `002_audit_run_provenance.sql`.
2. Create a **private** storage bucket named `private-audit-evidence` (or set `SUPABASE_STORAGE_BUCKET`).
3. Record the Alembic baseline once: `alembic stamp head` (run from `backend/`).

Redis (macOS): `brew install redis && brew services start redis`.

## Run

Two terminals, both in `backend/` with the venv active:

```bash
# Terminal 1: API
uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000

# Terminal 2: worker
python -m app.workers.run_worker
```

Create an audit (use a site you are allowed to test; each run uses TinyFish and Gemini credits):

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/audits \
  -H "Authorization: Bearer $API_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com"}'
```

Then read results:

```
GET  /api/v1/audits                 list
GET  /api/v1/audits/{id}            status and counts
GET  /api/v1/audits/{id}/steps      captured steps
GET  /api/v1/audits/{id}/findings   findings (always PENDING_REVIEW)
POST /api/v1/audits/{id}/cancel     stop a queued or running audit
WS   /api/v1/ws/audits/{id}         live progress; first message {"type":"auth","token":"..."}
```

## Tests

```bash
cd backend && pytest -q          # 393 passed, 32 skipped without a database or Redis
```

The skipped tests run against a throwaway Postgres and Redis:

```bash
TEST_DATABASE_URL="postgresql://user@host/ccpa_test" 
TEST_REDIS_URL="redis://localhost:6379/9" pytest -q
```

(The database name must contain `test`; the suite drops and recreates its tables.)

## Status

| Area | State |
|---|---|
| Schema, taxonomy, security validation | Done |
| TinyFish, evidence storage, Gemini grounding | Done |
| Audit runner, repository | Done |
| REST API, WebSocket, Celery worker | Done |
| Reviewer dashboard (Next.js) | In progress |
| Real user accounts, rate limits, stuck-run sweeper | Planned |

Known limits: the agent goal and action guard are soft controls; flows behind login or CAPTCHA are out of scope by design; precision and recall have not yet been measured on a labelled set.

## Responsible use

Findings are hypotheses for a human reviewer, not legal conclusions. Only audit sites you are permitted to test, and respect each site's terms.
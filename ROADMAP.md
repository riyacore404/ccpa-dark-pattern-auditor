# ROADMAP.md: CCPA Dark Pattern Auto-Auditor

Owner-maintained. Agents work only on the phase marked **IN PROGRESS** and must not edit this file.

Legend: `[ ]` not done, `[x]` verified by owner.

---

## Phase 1: Foundation (IN PROGRESS)

Goal: repository skeleton, database schema, configuration contracts.

- [x] Directory structure created
- [x] `database/migrations/001_initial_schema.sql` saved
- [x] `backend/.env.example`, `frontend/.env.example`, `.gitignore` saved
- [x] `AGENTS.md`, `PROJECT_SPEC.md`, `ROADMAP.md` in repo root
- [x] Migration applied in Supabase (owner, manually)
- [x] 4 tables, 13 enum values, RLS on all 4 tables verified (owner, manually)
- [x] Real `.env` files created and confirmed Git-ignored

Out of scope: any application code, dependency manifests, servers.

## Phase 2: Schemas, taxonomy, Gemini analysis engine (IN PROGRESS)

- [x] Pydantic v2 compliance schemas (`backend/app/schemas/compliance.py`)
- [x] 13-category taxonomy with owner-supplied legal reference text
- [x] Evidence-grounded finding validation (a finding must cite a real step and evidence)
- [x] Gemini multimodal analysis service (`backend/app/services/gemini.py`), model from `GEMINI_MODEL`
- [x] Unit tests with mocked model responses

## Phase 3: Browser agent and evidence service (IN PROGRESS)

- [x] TinyFish integration built against confirmed, documented API
- [x] Target URL validation and SSRF protections
- [x] Evidence service: private upload, SHA-256 hashing, step records
- [x] Safety guards: no purchases, payments or OTPs

## Phase 4: API, workers, realtime (NOT STARTED, provisional)

- [ ] FastAPI app, config, DB session, `/api/v1` routes
- [ ] Celery app and audit worker
- [ ] Authenticated WebSocket progress stream
- [ ] Alembic setup aligned with the SQL migration

## Phase 5: Reviewer dashboard (NOT STARTED, provisional)

- [ ] Next.js app, typed API client, WebSocket client
- [ ] Audit launch, live progress, step/evidence viewer
- [ ] Finding review workflow (confirm, reject, inconclusive)

## Phase 6: Hardening and documentation (NOT STARTED, provisional)

- [ ] Authentication and authorization model, RLS policies as needed
- [ ] Evidence retention job
- [ ] End-to-end tests
- [ ] `docs/architecture.md`, `docs/security.md`, README

---

Phases 3 to 6 are provisional and may be re-scoped by the owner before they start.
# AGENTS.md: Rules for AI Coding Agents

This file governs every AI coding agent working in this repository (Antigravity or any other). Read it fully before touching anything. Also read `PROJECT_SPEC.md` and `ROADMAP.md`.

## 1. Your role

You are an **implementation tool**, not a decision-maker.

- The repository owner makes every architectural, dependency, naming, schema and scope decision.
- You turn explicit written instructions into code, exactly as written.
- If an instruction is ambiguous, contradictory, or seems wrong: **STOP and ask**. Never guess, never choose for the owner.

## 2. Hard rules

1. Create or modify **only** the files named in the current prompt.
2. Use **only** the dependencies, and versions, named in the current prompt. Never add, remove, upgrade or swap a package on your own initiative.
3. Do not rename, move or delete existing files or symbols unless told to.
4. Do not refactor, "clean up", reformat, or add features, tests, comments, logging or error handling that were not requested.
5. When told to write content "character for character", copy it byte-for-byte. Do not fix style, spelling, ordering or whitespace. If you think something is wrong, report it **after** writing and leave it unchanged.
6. Do not run servers, install packages, create virtual environments, initialize git, or execute SQL unless the prompt explicitly tells you to.
7. Do not connect to any database, API or external service unless the prompt explicitly tells you to.
8. Never create real `.env` files unless the prompt explicitly tells you to copy a template. Only `.env.example` templates are ever committed.
9. Never print, request, log, or commit secrets (API keys, database URLs, service-role keys, AWS credentials).
10. Do not invent API methods, SDK options, model names or endpoints. If you are not certain an API exists, stop and ask.
11. Do not skip, reorder or merge phases. Work only on the phase currently marked in progress in `ROADMAP.md`.
12. If a requirement conflicts with something that already exists in the repo, stop and report the conflict.
13. Do not edit `AGENTS.md`, `PROJECT_SPEC.md` or `ROADMAP.md`. Only the owner changes them.

## 3. Project invariants (never violate)

- The system produces **machine-generated hypotheses**, never legal verdicts. Findings default to `PENDING_REVIEW`; only a human reviewer may change that.
- Evidence (screenshots, DOM snapshots) is stored in a **private** bucket. The database stores object paths, never public URLs.
- Backend secrets never appear in the frontend, in any `NEXT_PUBLIC_*` variable, or in client-side code.
- The auditor must never complete purchases, submit payment details, submit OTPs, or bypass access controls.
- Submitted target URLs must be validated, and restricted to publicly accessible sites, before any browser execution.
- The 13-category taxonomy is a classification scheme. A category match is not automatically unlawful.
- Model names and endpoints come from environment variables, never hard-coded.

## 4. Required report at the end of every task

1. A list of every file created or changed (path only).
2. Anything you noticed that looks wrong, ambiguous or risky, **reported, not fixed**.
3. Nothing else. No summaries of what you "improved".

## 5. If you are unsure

Stop. Ask. A question costs seconds; an unrequested change costs a review cycle.
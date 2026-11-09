# Dashboard

The reviewer dashboard for the CCPA Dark Pattern Auto-Auditor (Next.js, TypeScript, Tailwind).

It lists audits, starts new ones, shows each finding with its evidence and screenshots, and lets a
person confirm, reject or mark a finding inconclusive. Findings are hypotheses for human review, not
legal verdicts.

## How it keeps the backend token safe

The browser never talks to the backend. It talks to this app's own server routes, which check a
signed login cookie and then call the backend with the access token. The token lives only in the
server's environment.

## Run it

```
cd frontend
npm ci
cp .env.example .env.local     # then fill in the values
npm run dev                    # http://127.0.0.1:3000
```

Needs Node 22.12 or newer and the backend API running (see the backend README).

## Checks

```
npm run typecheck
npm test
npm run build
```

#!/usr/bin/env bash
# Read-only. Shows HOW each frontend file differs from the specification.
cd "$(git rev-parse --show-toplevel)" || exit 1
echo "--- NEXT_PUBLIC_ occurrences (file:line only) ---"
grep -rln 'NEXT_PUBLIC_' frontend --exclude-dir=node_modules --exclude-dir=.next --exclude=package-lock.json | sed 's/^/  /'
echo "--- files whose size differs from the specification ---"
while read -r bytes lines f; do
  [ -f "$f" ] || { echo "  MISSING $f"; continue; }
  b=$(wc -c < "$f" | tr -d ' '); l=$(wc -l < "$f" | tr -d ' ')
  cr=$(grep -c $'\r' "$f"); last=$(tail -c1 "$f" | od -An -tx1 | tr -d " \n")
  [ "$b" = "$bytes" ] && [ "$l" = "$lines" ] || echo "  $f  have ${b}B/${l}L (CR lines: $cr, last byte: ${last:-none})  want ${bytes}B/${lines}L"
done <<'LIST'
565 15 frontend/.env.example
76 7 frontend/.gitignore
874 32 frontend/README.md
464 16 frontend/app/api/audits/[id]/cancel/route.ts
711 19 frontend/app/api/audits/[id]/findings/[findingId]/route.ts
511 18 frontend/app/api/audits/[id]/route.ts
969 29 frontend/app/api/audits/[id]/steps/[step]/screenshot/route.ts
811 21 frontend/app/api/audits/route.ts
1732 52 frontend/app/api/login/route.ts
626 18 frontend/app/api/logout/route.ts
870 27 frontend/app/audits/[id]/page.tsx
535 17 frontend/app/error.tsx
1618 73 frontend/app/globals.css
1109 33 frontend/app/layout.tsx
97 3 frontend/app/loading.tsx
1183 34 frontend/app/login/page.tsx
432 13 frontend/app/not-found.tsx
1300 43 frontend/app/page.tsx
1840 47 frontend/components/audit/AuditTable.tsx
5118 142 frontend/components/audit/AuditView.tsx
523 15 frontend/components/audit/AutoRefresh.tsx
1450 50 frontend/components/audit/CancelButton.tsx
4513 119 frontend/components/audit/FindingCard.tsx
2630 77 frontend/components/audit/FindingsPanel.tsx
1804 62 frontend/components/audit/LoginForm.tsx
504 24 frontend/components/audit/LogoutButton.tsx
2681 85 frontend/components/audit/NewAuditForm.tsx
4628 141 frontend/components/audit/ReviewForm.tsx
1401 48 frontend/components/audit/ScreenshotModal.tsx
2701 67 frontend/components/audit/StepGallery.tsx
566 21 frontend/components/ui/Badge.tsx
900 35 frontend/components/ui/StatusBadge.tsx
728 17 frontend/components/ui/styles.ts
1842 44 frontend/lib/apiRoute.ts
663 19 frontend/lib/auth.ts
4217 132 frontend/lib/backend.ts
795 22 frontend/lib/categories.ts
2367 68 frontend/lib/config.ts
659 17 frontend/lib/errors.ts
1718 44 frontend/lib/format.ts
510 12 frontend/lib/ids.ts
941 36 frontend/lib/loginLimiter.ts
486 15 frontend/lib/origin.ts
1617 39 frontend/lib/session.ts
2173 52 frontend/lib/validate.ts
651 22 frontend/next.config.ts
814 33 frontend/package.json
94 7 frontend/postcss.config.mjs
6118 157 frontend/tests/backend.test.ts
13604 303 frontend/tests/components.test.tsx
2608 60 frontend/tests/config.test.ts
2555 85 frontend/tests/helpers.ts
12116 275 frontend/tests/routes.test.ts
3533 98 frontend/tests/session.test.ts
4603 109 frontend/tests/validate.test.ts
737 42 frontend/tsconfig.json
2176 86 frontend/types/api.ts
372 14 frontend/vitest.config.mts
LIST
echo "--- done ---"

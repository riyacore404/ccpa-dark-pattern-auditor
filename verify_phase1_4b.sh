#!/usr/bin/env bash
# verify_phase1_4b.sh - owner-run verification for Phases 1, 2, 3, 4A, 4B, 5A and 5B.
# Run from the repository root:  bash verify_phase1_4b.sh
# Read-only: it changes nothing. Keep this file OUTSIDE the repo or untracked.

cd "$(git rev-parse --show-toplevel 2>/dev/null || pwd)" || exit 2
[ -f database/migrations/001_initial_schema.sql ] || { echo "Run this from the repository root."; exit 2; }

PASS=0; FAIL=0; WARN=0
ok()   { echo "PASS  $1"; PASS=$((PASS+1)); }
bad()  { echo "FAIL  $1"; FAIL=$((FAIL+1)); }
warn() { echo "WARN  $1"; WARN=$((WARN+1)); }
section() { echo; echo "== $1"; }

section "1. Files are byte-identical to what was specified"
while read -r want file; do
  [ -z "$file" ] && continue
  if [ ! -f "$file" ]; then bad "missing: $file"; continue; fi
  got=$(shasum -a 256 "$file" | awk '{print $1}')
  [ "$got" = "$want" ] && ok "$file" || bad "content differs: $file"
done <<'HASHES'
668ff677a9945c40205d695278f4bd7b3859e094ae06d7bbfb144d8f77302ee4  database/migrations/001_initial_schema.sql
799a987f1f053b068f13617e52dcf728eba54d6dcf93ad328ecd29754b803a0a  backend/.env.example
99475185e58194dd6c62d0e68f04a1b6d9e85a67412d0cdcc56f69d752b933d0  .gitignore
bbb7f9702ef48645b2f21727a1c86b740505c919e49f5b995583a4cb7dae2cdb  backend/pyproject.toml
9ca560b48aa3a85a03dfef6209c046a6d9556f4db4b0b42ba421f68bb70799de  backend/app/core/config.py
c2799fe219555de7d8a0581a9cfe9f94a467b8bd9afb1e6677658577186ff1ab  backend/app/core/security.py
3b5a043b779fbb25db3fb3b6d168edb4ce7b6849de26974d5f5fd3eee1f8cd50  backend/app/schemas/taxonomy.py
f520cb18912340e6fa5fbcc1610a77722bea44fff86a0d3eddaf8f14db60c900  backend/app/schemas/compliance.py
3e9ccdb6b60a0174f3c98ae2caf391e2639e17531bd44dd7a2ed0e36067f5930  backend/app/services/gemini.py
b25e444bfe784042aaf5e69d18796ac275eadfb1f185f26baf2fd3623aabf565  backend/app/services/tinyfish.py
0fa5a7021c1821f856ac1f3ba4520ca4fccefe8b59f0d9e307bbeab4c1702673  backend/app/services/evidence.py
2c4fe8530ce409517c2a3d56e44e361e2bfc4019e85b8db605f360b0de021f60  backend/tests/test_taxonomy.py
855d8b2ea189449f91ac4e92f8e3403ee134f39c1c252076f0256e3f17c7ea75  backend/tests/test_compliance.py
178c3da76ab20a4896d5caf16d72e1705b79c3cad7c7a05ea185b63e7e951c8f  backend/tests/test_gemini.py
223e4c18b44c5fbc42841bccdc4051eec4ecd914996a525f3a162be0426e17ab  backend/tests/test_config.py
58995f3bba59661771964d16365be908378bf16f63c32f3a766ae865413f06cc  backend/tests/test_security.py
b25bb3934ea39287a4732d45957ce47d331a2ca48c2a0814aec0e63f1f23cf05  backend/tests/test_tinyfish.py
3116a473a6059b4bdca74e961377154fb83096b801e6544613641f5809bdc84c  backend/tests/test_evidence.py
790a2c8fca6296e727d6751dbafc344459ff9d7fb4ad80a2c8d42bda9f4e4acd  backend/tests/conftest.py
9f0995847a7936c8492df854c8c39e4817c0b102a536c7f119147b5789bda181  database/migrations/002_audit_run_provenance.sql
2a71ac5fa093b6d3d2aae2592fccd9c951d35956a7b490dc17d1646849f11a59  backend/app/db/repository.py
33e98fe36b7385c424e3c1be41f4033f83bf918b2eff2a48f7d6eaef910fb687  backend/app/services/audit_intake.py
a0dd8a2ba9fd3350fe4f70008b0550835b1969701bb979bda09a9b2e84ab9880  backend/app/services/audit_runner.py
cf041441586bf8186e719233be170a358bf6d12101f035c006ec59f15c945d75  backend/tests/test_audit_intake.py
c11ea6ad931579eee61cc06a4b9ea94bb76be01b5f5943ae61a49b28c1528ae0  backend/tests/test_audit_runner.py
3b3efdb2d933cf171d4a612d1de5db9ced6f4e6536f1c0249c2912fe9af8e16a  backend/tests/test_repository.py
fd996cce2e33150801381ef7ef4b3c0158f8be1d22da6e2288eea50c9c0058a0  backend/app/services/progress.py
f64c8609ebbad164791f1591a62241a03e1c88b4c53d0b4364f071e757de2df1  backend/app/schemas/api.py
2647ec38a611948a95214864fed1f8db80436a90315f24b7996635b55b379a3a  backend/app/api/deps.py
6a99dc0eb2c2ac4dd5104f21881ffd3b89c5400077ae0a05da3f8aaa39f5123f  backend/app/api/v1/audits.py
691af409841d9598f9e0651e5167cc944a4b20c5a719911747eeab3c2fbdfedd  backend/app/main.py
ea049ad1ab51ea319cc1ced07eac9d26eda6919e0ef708527c30e21d0f75b130  backend/app/workers/celery_app.py
35a8b76285ca13e8d5d7aa873f3b266dd4a6284420c16c876b9b1391f9f54133  backend/app/workers/tasks.py
8b68f7794d0a80274f96ffd5e1b1cdcb028dae54a3444c139baa6c60ec7cc8de  backend/app/workers/run_worker.py
d38b84c0ea347c46639a2671e499b8bda30a3e18826e5f447195e76be763ec20  backend/alembic.ini
ad9f5cb9c7dad1f738045ed5a0d97bb77738868fa2a4c94c71f06a87956d6d33  backend/alembic/env.py
969a2de2c4edbc9af1bb6f64c3ca4d59beed4ab00fb1fde44b52e9e154ebc147  backend/alembic/script.py.mako
6574a54ff7be9c5a7936d2663860e9b161c73b329073b6114ff68e4298c82d4b  backend/alembic/versions/0001_baseline.py
c3c1708e6b44b6d77d6452d4d4702f3d4de84db41cae36b75f883181b2754820  backend/tests/test_alembic.py
20bbd60c4fa5e8a88c3c901b6e0a9c018ee71070035556efb824b4349d47b3b4  backend/tests/test_api.py
e72205225e13b08e6ea9c5a51fba85ea05f6ed46a33c27c161a18e207eb4a645  backend/tests/test_api_database.py
0f78f7b62131773a0228324cdc740615c76ecd64d92329345d3794cdaf5dc0b2  backend/tests/test_progress.py
042e0990a009c27465bc76271208c2de592646d6a1c1ac40144d87744fd56b60  backend/tests/test_worker.py
fb72138d9e308500cc4dcb5ea0bfd85132e0b7fcb387ef9d1714b1cf39a8f5b4  backend/tests/test_ws.py
4e491e4e7a9a0af9ed0f2aac0919f54a8b6c34707ea2c9674df5f512628d9166  frontend/.env.example
36ac793582622d9296aa247d8033eea00dcbdc1eac2cc6f0d2c11e6987a3b271  frontend/.gitignore
0f1026e9deb1f453d4dff3fa16d49f3ca3c259541922235c776d6c2e3cda1a63  frontend/README.md
93ccaaa61bca643828379a9826b015b2c0db0cddd66b421a4a5c73a62c36f966  frontend/app/api/audits/[id]/cancel/route.ts
6c159080ec6c2662a6fb7dba8e404d62815f2005a8017941517871f31529d8c3  frontend/app/api/audits/[id]/findings/[findingId]/route.ts
1f9f0fd884206ad9a11b59e5bb143f824214c3e7ddd112ab7259df350e8451b6  frontend/app/api/audits/[id]/route.ts
4d4cdf76851b9001e8cae4542813cbe79ade6c630a71414b2e445cddb52d0e1d  frontend/app/api/audits/[id]/steps/[step]/screenshot/route.ts
58d8991414d25596585c56ce8015e77cd81507692e06d0d900ff95e729444a7d  frontend/app/api/audits/route.ts
c2a40c38de36ce2c17a65610c26a0ca1a98996f7b2f5beb05a1dbb92d18ff4e1  frontend/app/api/login/route.ts
3c0f737912100b2422c849cf4abe660fdcb19b78105e0d12e5399f7972b144bf  frontend/app/api/logout/route.ts
8d2069c2d83958e000834d54ccf5297af798e4704bf0b55c0ed2b33fd1d12776  frontend/app/audits/[id]/page.tsx
af55358529be7545ad51d691073d286c454bf899a3bd344cd1ce2f068f425ddd  frontend/app/error.tsx
cb2f1abd592c76e3d83536e350a2ea37da4aa864e456c5c1544344c88b4d9157  frontend/app/globals.css
0835881731fdefe180d654f1aa9bee18ac66f3bd4520d0e6da790f72bd81cf96  frontend/app/layout.tsx
6c53371404e92452bb27ffa44153a846ef09d485bdc61827d158d8b7e66a4f35  frontend/app/loading.tsx
fdb49082c0ea05bc13856f2049dfefb23c37b3205fad694980fe24cecd145805  frontend/app/login/page.tsx
b4fe788c88e51df1f9c5171c843b891c0bd909f3ccb71cd0b31863cd2b03ea63  frontend/app/not-found.tsx
132c8cf0d8275175692d5db09aec38bf06b35e706a2b324ab5c75aa749a76331  frontend/app/page.tsx
62958186b5ceddfb5caa87eef5e3c04d82bef8264dd02e05bb575b256878ab81  frontend/components/audit/AuditTable.tsx
79f1cf835ef9d9517eb4f63ecbb249515c738f2e04a721345e147a50d61cdc3f  frontend/components/audit/AuditView.tsx
2efdf21962b0f179c1288c34a9f5c9777a647f7a1e6c6b5a30c1051859d60962  frontend/components/audit/AutoRefresh.tsx
9a3f788a12ea12410472473ad3b465c1a7b6294e3da81e91138d4ad57dbe7b38  frontend/components/audit/CancelButton.tsx
4e4d7883d6b698a5e8ecbcecd511e8905a2c726136c58002d29e1e0b08d5d9cb  frontend/components/audit/FindingCard.tsx
f628bc0029558653fa4a0146562b827d065ceefd6a74fd33a0b3a43bb80d2361  frontend/components/audit/FindingsPanel.tsx
871ab95cf5f6dc63ea9c95cd5bec0b6aa5ea630bbb600877aab7c81faa56424b  frontend/components/audit/LoginForm.tsx
5c8463914d22def65ba20d4615cb43cbad014c4d788107f2de9a58ccb2b2183a  frontend/components/audit/LogoutButton.tsx
c94381c6dc16c6c19a075658700fbc38d5ad3218201e65dc5a4bccd9ec1ad10f  frontend/components/audit/NewAuditForm.tsx
8491bfbfebea545d3360b74d2b06a5e31dd96a3a791d06b3c779acd61afe4587  frontend/components/audit/ReviewForm.tsx
348bba185db6032758f7aa1f6043d6e023f6ab299bc8dbef6733d4d346397cc3  frontend/components/audit/ScreenshotModal.tsx
cd919410a89fbab0a7edd987927033a1c36d9d88f279ac77dee06240bbc9fb36  frontend/components/audit/StepGallery.tsx
7ecec9013ca2ebea27c928a82d4b0eb5d28154333f7514a6d9e5796262ac427b  frontend/components/ui/Badge.tsx
3a6bc686ca9be26694d3f1f9e38cb9b2fbc377268aca063b1310279567844da3  frontend/components/ui/StatusBadge.tsx
86b26abe4a71f88a015bbb6311d66390ec3e6f7765d0034cbf61be0a63e989d0  frontend/components/ui/styles.ts
18375ea4555670aab1a4f72403ac704264f980395f6ff099d8c8e5a3de8fae83  frontend/lib/apiRoute.ts
6c4c903a3ee7476d9d84b25ca53679aadcefba8d83bb6c3546f6b4cdecbc2c8d  frontend/lib/auth.ts
02f2c7005d20593142b372c08f050620433459e6f913efd5d7c7673a32e9f051  frontend/lib/backend.ts
55da5ac9ba1d809775a751c03394518727a426cbbefd9b3e51a8cf3a58aa40a0  frontend/lib/categories.ts
cd47e5ffdbcd6efd8a91873056027c67ec18f2ced11851efafdc0fc9da53290d  frontend/lib/config.ts
6880ea987697cf4f318d566b2ff2c899d7dc3cb69f99c88ced098ce3a61e56eb  frontend/lib/errors.ts
a890ae7b90ceeeab4177660eb796860228446e312e56aec2f995e1fb78a4a80e  frontend/lib/format.ts
070b35750b7a4c6fef4c42df7901c769cf8f44c612dc0738c389e9e69a7fc12a  frontend/lib/ids.ts
5e0233fbe5724e0307a280d5996613bb99112589e979648819371a1f666328c3  frontend/lib/loginLimiter.ts
9c7c6a9bc4092a04d90e1360a2a1e0fd68b4d330b312e3d55345484bc3c4deb4  frontend/lib/origin.ts
895ea6b333a7a92ff3cb1e9012d786a89b5655b101e7beed736964f397f2ef37  frontend/lib/session.ts
9a5389839b42947b113838c4d0162c48644093d151e5ff4b25e7268eaab58295  frontend/lib/validate.ts
140fed5a7a109ab3d152e5c587ae9f54690474935fabc27d5904bdd2af57e1cf  frontend/next.config.ts
78a5989351f0ecf63e1a75bee6ef04fe7c2335bf90223f794832fb7492f6ffa8  frontend/package-lock.json
eaebf5ca2bc27971054055a8ae21afcad8591f6687e5b3bf9ba309848426cebf  frontend/package.json
dfac7ac2d86d326a0e5adb024e7943c181393ed17a5fcb8f0315b24c7da6ddde  frontend/postcss.config.mjs
763465cc5220f9e554c54b2098a5b7601bf6cc823692889a626b86f11f97a8ce  frontend/tests/backend.test.ts
44abff09aa063cc385c0225265232c32ad145214cde7bc29d31ddbff1e55ed5c  frontend/tests/components.test.tsx
f75f04ec6ef7efc660fde429f63703542f6bcdb4e9743ec1258ca557336532ba  frontend/tests/config.test.ts
d1ac0c7b6aca29089988517d77ad2393442d73635e050238272195616ad11080  frontend/tests/helpers.ts
8d8a1d18f11da29c5bcf3fec2aa970c75aa5afcefdff40ac617335fa6a9a3b86  frontend/tests/routes.test.ts
0c3483918058c3afcf46b9f71dc5ddb54540b9c4a338edd7be6730f852c0511d  frontend/tests/session.test.ts
02e32a2ecf4f4bea61ae170f70484785065275d40ec44a4c7479c90fb8287c4c  frontend/tests/validate.test.ts
bb1402ab7bcf48607e7b4d7db6aa2c5559ef7a2a9c99f2f71b5f63a3e39d8aa0  frontend/tsconfig.json
41c61fd12d0e226e2e6cd94d13fd48489549d94591069aeb56bb2cbe67de98cb  frontend/types/api.ts
e20f24861115328be14d7855b849368146c7ab17d405dc243b955556e0cd96a8  frontend/vitest.config.mts
HASHES

section "2. Structure"
for d in backend/app/core backend/app/api/v1 backend/app/schemas backend/app/services \
         backend/app/workers backend/app/db backend/tests backend/alembic/versions \
         frontend/app frontend/components/audit frontend/components/ui frontend/lib \
         frontend/types database/migrations docs; do
  [ -d "$d" ] && ok "dir $d" || bad "missing dir $d"
done
for f in AGENTS.md ROADMAP.md README.md backend/app/__init__.py backend/tests/__init__.py; do
  [ -f "$f" ] && ok "$f" || bad "missing $f"
done
{ [ -f PROJECT_SPEC.md ] || [ -f docs/PROJECT_SPEC.md ]; } && ok "PROJECT_SPEC.md" || bad "missing PROJECT_SPEC.md"
for f in backend/app/schemas/__init__.py backend/app/core/__init__.py backend/app/services/__init__.py; do
  [ -f "$f" ] && warn "$f exists (spec said create no __init__.py here; harmless, but not requested)"
done

section "3. Nothing beyond Phases 1-5B was created"
EXPECTED=$(cat <<'LIST'
.gitignore
AGENTS.md
ROADMAP.md
README.md
PROJECT_SPEC.md
docs/PROJECT_SPEC.md
backend/.env.example
backend/pyproject.toml
backend/app/__init__.py
backend/app/core/config.py
backend/app/core/security.py
backend/app/db/repository.py
backend/app/schemas/taxonomy.py
backend/app/schemas/compliance.py
backend/app/services/gemini.py
backend/app/services/tinyfish.py
backend/app/services/evidence.py
backend/app/services/audit_intake.py
backend/app/services/audit_runner.py
backend/tests/__init__.py
backend/tests/test_taxonomy.py
backend/tests/test_compliance.py
backend/tests/test_gemini.py
backend/tests/conftest.py
backend/tests/test_config.py
backend/tests/test_security.py
backend/tests/test_tinyfish.py
backend/tests/test_evidence.py
backend/tests/test_audit_intake.py
backend/tests/test_audit_runner.py
backend/tests/test_repository.py
frontend/.env.example
frontend/.gitignore
frontend/README.md
frontend/app/api/audits/[id]/cancel/route.ts
frontend/app/api/audits/[id]/findings/[findingId]/route.ts
frontend/app/api/audits/[id]/route.ts
frontend/app/api/audits/[id]/steps/[step]/screenshot/route.ts
frontend/app/api/audits/route.ts
frontend/app/api/login/route.ts
frontend/app/api/logout/route.ts
frontend/app/audits/[id]/page.tsx
frontend/app/error.tsx
frontend/app/globals.css
frontend/app/layout.tsx
frontend/app/loading.tsx
frontend/app/login/page.tsx
frontend/app/not-found.tsx
frontend/app/page.tsx
frontend/components/audit/AuditTable.tsx
frontend/components/audit/AuditView.tsx
frontend/components/audit/AutoRefresh.tsx
frontend/components/audit/CancelButton.tsx
frontend/components/audit/FindingCard.tsx
frontend/components/audit/FindingsPanel.tsx
frontend/components/audit/LoginForm.tsx
frontend/components/audit/LogoutButton.tsx
frontend/components/audit/NewAuditForm.tsx
frontend/components/audit/ReviewForm.tsx
frontend/components/audit/ScreenshotModal.tsx
frontend/components/audit/StepGallery.tsx
frontend/components/ui/Badge.tsx
frontend/components/ui/StatusBadge.tsx
frontend/components/ui/styles.ts
frontend/lib/apiRoute.ts
frontend/lib/auth.ts
frontend/lib/backend.ts
frontend/lib/categories.ts
frontend/lib/config.ts
frontend/lib/errors.ts
frontend/lib/format.ts
frontend/lib/ids.ts
frontend/lib/loginLimiter.ts
frontend/lib/origin.ts
frontend/lib/session.ts
frontend/lib/validate.ts
frontend/next.config.ts
frontend/package-lock.json
frontend/package.json
frontend/postcss.config.mjs
frontend/tests/backend.test.ts
frontend/tests/components.test.tsx
frontend/tests/config.test.ts
frontend/tests/helpers.ts
frontend/tests/routes.test.ts
frontend/tests/session.test.ts
frontend/tests/validate.test.ts
frontend/tsconfig.json
frontend/types/api.ts
frontend/vitest.config.mts
database/migrations/001_initial_schema.sql
database/migrations/002_audit_run_provenance.sql
backend/app/services/progress.py
backend/app/schemas/api.py
backend/app/api/deps.py
backend/app/api/v1/audits.py
backend/app/main.py
backend/app/workers/celery_app.py
backend/app/workers/tasks.py
backend/app/workers/run_worker.py
backend/alembic.ini
backend/alembic/env.py
backend/alembic/script.py.mako
backend/alembic/versions/0001_baseline.py
backend/tests/test_alembic.py
backend/tests/test_api.py
backend/tests/test_api_database.py
backend/tests/test_progress.py
backend/tests/test_worker.py
backend/tests/test_ws.py
LIST
)
EXTRA=$(git ls-files -co --exclude-standard 2>/dev/null | grep -vxF "$EXPECTED" | grep -v '__init__\.py$')
if [ -z "$EXTRA" ]; then ok "no unexpected files"; else
  warn "files not in the Phase 1-5B spec (fine if you added them yourself):"; echo "$EXTRA" | sed 's/^/        /'; fi

section "4. Secrets and git hygiene"
for f in backend/.env frontend/.env.local; do
  if [ -f "$f" ]; then git check-ignore -q "$f" && ok "$f is git-ignored" || bad "$f is NOT git-ignored"; fi
done
for f in backend/.env.example frontend/.env.example; do
  git check-ignore -q "$f" && bad "$f is wrongly ignored" || ok "$f is trackable"
done
if git ls-files 2>/dev/null | grep -E '(^|/)\.env($|\.)' | grep -v '\.example$' | grep -q .; then
  bad "a real .env file is tracked by git"; else ok "no real .env file is tracked"; fi
v=$(grep -E "^API_ACCESS_TOKEN=" backend/.env.example | cut -d= -f2-)
[ -z "$v" ] && ok "API_ACCESS_TOKEN is empty in the template" || bad "API_ACCESS_TOKEN has a value in backend/.env.example"
for k in TINYFISH_API_KEY GEMINI_API_KEY SUPABASE_SERVICE_ROLE_KEY AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY; do
  v=$(grep -E "^$k=" backend/.env.example | cut -d= -f2-)
  [ -z "$v" ] && ok "$k is empty in the template" || bad "$k has a value in backend/.env.example"
done
grep -q '^DATABASE_URL=.*YOUR_PASSWORD' backend/.env.example && ok "DATABASE_URL is a placeholder" || bad "DATABASE_URL in the template may hold a real password"
if grep -E '^[A-Z_]*(GEMINI|TINYFISH|SERVICE_ROLE|AWS|DATABASE)[A-Z_]*=' frontend/.env.example | grep -q .; then
  bad "backend-only secret name found in frontend/.env.example"; else ok "frontend env holds public config only"; fi
HITS=$(git ls-files -co --exclude-standard 2>/dev/null | xargs grep -InE \
  'AIza[0-9A-Za-z_-]{35}|AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY|postgres(ql)?://[^:/ ]+:[^@ ]{3,}@' 2>/dev/null \
  | grep -v 'YOUR_PASSWORD')
if [ -z "$HITS" ]; then ok "no key-shaped strings in any file git would commit"
else bad "possible secret in a committable file:"; echo "$HITS" | cut -c1-120 | sed 's/^/        /'; fi

section "5. Code invariants"
if grep -rnE 'gemini-[0-9a-z.-]+|models/gemini' backend/app 2>/dev/null | grep -q .; then
  bad "a Gemini model name is hard-coded in backend/app"; else ok "no hard-coded model names"; fi
if grep -rnE 'review_status *= *"?(CONFIRMED|REJECTED)' backend/app 2>/dev/null | grep -q .; then
  bad "code sets a finding to CONFIRMED/REJECTED"; else ok "code never confirms or rejects findings itself"; fi

if grep -rnE 'verify *= *False' backend/app 2>/dev/null | grep -q .; then
  bad "TLS verification is disabled somewhere in backend/app"; else ok "TLS verification is never disabled"; fi
if grep -rnE 'follow_redirects *= *True' backend/app 2>/dev/null | grep -q .; then
  bad "an HTTP call follows redirects (could leak API keys)"; else ok "no HTTP call follows redirects"; fi
if grep -rnE '"use_vault"|"use_profile"|credential_item_ids' backend/app 2>/dev/null | grep -q .; then
  bad "code sends vault or profile settings to TinyFish"; else ok "no vault or browser-profile credentials are ever sent"; fi
if grep -rn 'audit_allow_purchases' backend/app 2>/dev/null | grep -qE 'True|true'; then
  bad "purchases appear to be enabled in code"; else ok "purchases are not enabled anywhere in code"; fi

if grep -rnE "'(CONFIRMED|REJECTED|INCONCLUSIVE)'" backend/app 2>/dev/null | grep -q .; then
  bad "backend code writes a human review status"; else ok "backend code never writes a human review status"; fi
if grep -rnE --include='*.py' 'review_finding' backend/app 2>/dev/null | grep -vE '^backend/app/(db/repository|api/v1/audits)\.py:' | grep -q .; then
  bad "review_finding is used outside the repository and the review endpoint"; else ok "only the review endpoint can change a review status"; fi
if grep -rnE --include='*.py' 'UPDATE +public\.dark_pattern_violations' backend/app 2>/dev/null | grep -vE '^backend/app/db/repository\.py:' | grep -q .; then
  bad "findings are updated outside the repository"; else ok "findings are updated only inside the repository"; fi
if grep -rniE '\b(drop|truncate) +(table|schema)\b' backend/app 2>/dev/null | grep -q .; then
  bad "destructive SQL found in backend/app"; else ok "no destructive SQL in backend/app"; fi
if grep -rnE 'TEST_DATABASE_URL' backend/app 2>/dev/null | grep -q .; then
  bad "app code reads TEST_DATABASE_URL"; else ok "test database variable is used by tests only"; fi

if grep -rnE 'allow_origins *= *\[ *"\*"|allow_credentials *= *True|CORS_ORIGINS *= *\*' backend/app backend/.env.example 2>/dev/null | grep -q .; then
  bad "CORS allows every origin or credentials"; else ok "CORS is restricted to listed origins, no credentials"; fi
if grep -rnE 'query_params|\.query\b' backend/app/api 2>/dev/null | grep -q .; then
  bad "API code reads query parameters (the token must never travel in a URL)"; else ok "API code never reads the token from a URL"; fi
if grep -rnE 'NEXT_PUBLIC_[A-Z_]*(TOKEN|SECRET|SERVICE_ROLE|PRIVATE|KEY)' frontend --exclude-dir=node_modules --exclude-dir=.next 2>/dev/null \
   | grep -vE 'NEXT_PUBLIC_[A-Z_]*(ANON_KEY|PUBLISHABLE_KEY)' | grep -q .; then
  bad "a secret-looking NEXT_PUBLIC_ variable exists (Supabase anon/publishable keys are allowed: they are public by design)"; else ok "no secret is exposed through NEXT_PUBLIC_ variables"; fi
if grep -rnE '(==|!=) *(settings\.)?api_access_token|api_access_token\.get_secret_value\(\) *(==|!=)' backend/app 2>/dev/null | grep -q .; then
  bad "the access token is compared with == (use constant-time compare)"; else ok "token comparison is constant-time"; fi
if grep -rnE 'logger\.[a-z]+\(.*(token|secret|password|database_url)' -i backend/app 2>/dev/null | grep -q .; then
  bad "a log line may include a secret"; else ok "no log line mentions secrets"; fi

section "5b. Dashboard invariants"
FE_SRC="frontend/app frontend/components frontend/lib frontend/types"
if grep -rnE 'NEXT_PUBLIC_' frontend --exclude-dir=node_modules --exclude-dir=.next --exclude=package-lock.json 2>/dev/null | grep -q .; then
  bad "NEXT_PUBLIC_ is used in the dashboard (nothing may be exposed to the browser)"; else ok "no NEXT_PUBLIC_ variable in the dashboard"; fi
if grep -rnE 'API_ACCESS_TOKEN' frontend --exclude-dir=node_modules --exclude-dir=.next --exclude=package-lock.json 2>/dev/null \
   | grep -vE '^frontend/(lib/config\.ts|lib/errors\.ts|tests/|\.env\.example|README\.md)' | grep -q .; then
  bad "API_ACCESS_TOKEN is referenced outside frontend/lib/config.ts"; else ok "the backend token is read in one place only (lib/config.ts; lib/errors.ts only names it in a hint)"; fi
CLIENT_BAD=""
for f in $(grep -rlE '^"use client"' $FE_SRC --include='*.ts' --include='*.tsx' 2>/dev/null); do
  if grep -qE "from \"@/lib/(backend|config|auth|session|apiRoute|errors|loginLimiter|origin)\"" "$f"; then CLIENT_BAD="$CLIENT_BAD $f"; fi
done
[ -z "$CLIENT_BAD" ] && ok "no browser component imports server-only code" || bad "browser component imports server-only code:$CLIENT_BAD"
ROUTE_BAD=""
for f in $(find frontend/app/api -name route.ts 2>/dev/null); do
  grep -qE 'guard\(|isSameOrigin\(' "$f" || ROUTE_BAD="$ROUTE_BAD $f"
done
[ -z "$ROUTE_BAD" ] && ok "every API route checks the session or the origin" || bad "API route without a session or origin check:$ROUTE_BAD"
if grep -rnE 'follow|redirect: *"follow"' frontend/lib/backend.ts 2>/dev/null | grep -q 'redirect: *"follow"'; then
  bad "the backend client follows redirects"; else ok "the backend client never follows redirects"; fi

section "6. Tests"
if [ -x backend/.venv/bin/python ]; then
  PV=$(backend/.venv/bin/python -c 'import sys; print("%d.%d" % sys.version_info[:2])')
  awk -v v="$PV" 'BEGIN{split(v,a,"."); exit !(a[1]>3 || (a[1]==3 && a[2]>=11))}' \
    && ok "backend venv uses Python $PV" || bad "backend venv uses Python $PV (need 3.11+)"
  OUT=$(cd backend && .venv/bin/pytest -q -p no:cacheprovider 2>&1 | tail -3)
  echo "$OUT" | grep -q '447 passed, 38 skipped' && ok "pytest: 447 passed, 38 skipped" || { bad "pytest did not report 447 passed, 38 skipped"; echo "$OUT" | sed 's/^/        /'; }
else
  bad "backend/.venv not found (create it: cd backend && python3.13 -m venv .venv && .venv/bin/pip install -e '.[dev]')"
fi

if [ -d frontend/node_modules ]; then
  NV=$(node -v 2>/dev/null | sed 's/^v//')
  if awk -v v="$NV" 'BEGIN{split(v,a,"."); exit !(a[1]>22 || (a[1]==22 && a[2]>=12))}'; then
    ok "Node $NV (need 22.12+)"
    (cd frontend && npm run typecheck >/dev/null 2>&1) && ok "frontend typecheck is clean" || bad "frontend typecheck failed (cd frontend && npm run typecheck)"
    FOUT=$(cd frontend && npm test 2>&1 | tail -40)
    echo "$FOUT" | grep -qE 'Tests +125 passed' && ok "frontend: 125 tests passed" || { bad "frontend did not report 125 passed"; echo "$FOUT" | sed 's/^/        /'; }
  else
    bad "Node ${NV:-not found} is too old for the dashboard (need 22.12 or newer)"
  fi
else
  warn "frontend/node_modules not found: run 'cd frontend && npm ci' to test the dashboard"
fi

echo
echo "=============================================="
echo "  $PASS passed, $FAIL failed, $WARN warnings"
echo "=============================================="
cat <<'MANUAL'

STILL MANUAL (a script cannot do these for you):
  [ ] Supabase: run 001_initial_schema.sql, then phase1_smoke_test.sql
      in the SQL Editor. Expect: ALL CHECKS PASSED.
  [ ] Supabase: run 002_audit_run_provenance.sql in the SQL Editor, then
      db_probe.py (expect: DB PROBE: ALL GOOD).
  [ ] Redis running (redis-cli ping), API_ACCESS_TOKEN set by hand in backend/.env,
      `alembic stamp head` run once, then api_probe.py (expect: ALL GOOD). See PHASE4B_RUNBOOK.md.
  [ ] Dashboard: follow PHASE5B_RUNBOOK.md (env file, npm ci, run it, one real audit and review).
  [ ] Supabase: create the PRIVATE storage bucket, then run
      supabase_storage_probe.py (expect: STORAGE PROBE: ALL GOOD).
  [ ] Read the 13 category summaries in backend/app/schemas/taxonomy.py
      against the official guideline text.
  [ ] Set GEMINI_MODEL / GEMINI_API_KEY in backend/.env by hand and run
      one real screenshot through GeminiAnalyzer.
  [ ] Tick the verified items in ROADMAP.md, then commit.
MANUAL
[ "$FAIL" -eq 0 ]

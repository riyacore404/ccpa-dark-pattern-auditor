#!/usr/bin/env python3
"""Run from the repository root. For each frontend file, if it does not match the
specified SHA-256, try removing exactly one extra newline at the end (or start).
A file is rewritten ONLY if the result matches the specified hash exactly."""
import hashlib, pathlib, sys
WANT = """
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
"""
fixed = same = left = 0
for line in WANT.strip().splitlines():
    h, f = line.split(None, 1); p = pathlib.Path(f.strip())
    if not p.is_file():
        print("MISSING", p); left += 1; continue
    data = p.read_bytes()
    sha = lambda b: hashlib.sha256(b).hexdigest()
    if sha(data) == h: same += 1; continue
    for name, cand in (("extra trailing newline", data[:-1] if data.endswith(b"\n\n") else None),
                       ("extra leading newline", data[1:] if data.startswith(b"\n") else None)):
        if cand is not None and sha(cand) == h:
            p.write_bytes(cand); fixed += 1; print("fixed (%s): %s" % (name, p)); break
    else:
        left += 1; print("STILL DIFFERENT (not touched):", p)
print("already correct: %d, fixed: %d, still different: %d" % (same, fixed, left))
sys.exit(1 if left else 0)

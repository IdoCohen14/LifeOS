# Publication security review

Review date: 2026-11-08. Scope: the staged portfolio source snapshot, selected application boundaries, locked dependencies and the separation of source from personal operational records. This is not a penetration test or security certification.

## Findings addressed

### PUB-001 — High: personal operational material in the working checkout

Historical development notes, installation-specific launch configuration and generated artifacts can disclose personal deployment information if added indiscriminately. These are excluded from the publication snapshot. The review uses an independent source-only Git repository, rather than copying the original object store. Existing personal files are preserved locally.

### PUB-002 — Medium: personal identifiers reused in synthetic tests

Three transition/server fixtures previously reused installation identifiers. The publication source replaces them consistently with synthetic owner/host identifiers. This changes test data, not personal account records or integration configuration.

### DEP-001 — Moderate: development glob-matching dependency

The JavaScript audit identified the minimatch glob amplification advisory [GHSA-g3hv-75wg-m249](https://github.com/advisories/GHSA-g3hv-75wg-m249). A narrowly scoped override under `@typescript-eslint/typescript-estree` selects the patched major, rather than accepting an automated downgrade of the framework's ESLint configuration. A clean dependency installation, ESLint, TypeScript and production build are used to check compatibility. The subsequent npm audit reports no known vulnerabilities in the reviewed lockfile.

### DEP-002 — Dependency advisories: PDF parsing

The initial Python lockfile used a PDF parser version reported vulnerable by pip-audit. Requirements now select `pypdf==6.21.4`, which clears the reported advisories in the follow-up audit. The existing isolated document tests were exercised with the patched library. Upload/extraction size, time and resource controls remain in place; upgrading the parser is not a substitute for those boundaries.

## Source boundaries reviewed

- `services/api/lifeos/main.py`: loopback service assumptions, process-key checks, origin validation, restricted hosts, non-echoing request validation errors and no-store responses.
- `services/api/lifeos/account_routes.py`, `account_records.py`, `account_academic.py`: session-derived owner identity, CSRF checks, account scoping, ownership-constrained SQL/FTS queries and bounded upload handling.
- `services/api/lifeos/security.py`, `accounts.py`, `credential_vault.py`: salted scrypt verification, hashed session tokens and OS-bound/provider-key encryption.
- `apps/web/app/api/[...path]/route.ts`: allowlisted proxy paths, host/origin validation, server-only process key, request size/deadline limits and constrained redirect handling.
- `apps/web/proxy.ts`, `lib/csp-manifest.mjs`: build-derived production script policy and startup verification. Required style elements remain permitted; this is not a claim that every inline style is blocked.
- `services/api/lifeos/documents.py`, `document_extract.py`, `web_push_transport.py`: bounded extraction, safe file delivery and allowlisted push destinations.
- Frontend rendering and service-worker review: no arbitrary HTML rendering sink was found in the searched application sources; personal API responses are not part of the static offline cache.

No new exploitable application defect was confirmed in the inspected boundaries. That statement is limited to the review performed, not a guarantee about the entire application or deployment environment.

## Verification boundaries

The local publication review records exact test counts, build results, dependency audit results, staged-file hashes and secret-scanner classifications separately. Only an approved snapshot may be pushed. The included `scripts/verify_publication.py` examines staged blobs and filenames without printing discovered values; it can also load a private local deny-list. Generic and entropy-based scanning still requires review of synthetic-test false positives.

## Remaining limitations

- Working SQLite data is not encrypted at rest; OS and disk protections remain necessary.
- Public multi-user hosting, shared backup/deletion/recovery policy and provider OAuth approval are separate from publishing source code.
- Comprehensive OS/DNS isolation, all hostile-input/capacity cases and full recent mobile/accessibility acceptance have not been established by this review.
- API/feed/OAuth credentials must remain local. No confirmed credential exposure was identified by this publication review; rotate any credential if independent evidence shows prior exposure.
- The original checkout and its unrelated tooling are not replaced by the source-only publication snapshot. Future dependency changes and commits require renewed review.

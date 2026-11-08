# Security and privacy

This is a personal software engineering project, not a security-certified public service. Do not use real credentials or personal data when evaluating it.

## Safe configuration

- Keep both processes on loopback. Do not expose a development server directly to the internet.
- Keep the data directory outside the checkout and outside shared/cloud-synced folders. The SQLite database contains private plaintext application data; protect the OS account and disk.
- Configure Google application credentials only on the server. Never put secrets in `NEXT_PUBLIC_*`, examples, screenshots or commits.
- `.env.example` is documentation. The launcher reads process environment variables; it does not automatically load `.env` files.
- User OAuth grants, private calendar feed URLs, cookies, vault keys and backups must never be committed, even to a private repository.
- Backups use a separately chosen password. Preserve any required OS/vault keys and recovery material privately. Do not treat a backup on the same disk as disaster recovery.
- Production startup verifies its CSP manifest. Do not weaken host, origin, CSRF, ownership, session or TLS checks to make an integration work.

## Local versus server mode

Local loopback HTTP uses HTTP-only, SameSite cookies. Explicit HTTPS server mode uses secure cookies and a validated configured origin, rather than trusting forwarded request headers. Linux templates require an explicit persistent data directory. A private personal deployment is distinct from open public registration.

## Verification limits

Source review, selected regression checks and dependency/secret scans have defined scope. They do not establish complete OS isolation, perfect hostile-input handling or absence of unknown vulnerabilities. Full phone/Safari accessibility acceptance and public-server operational recovery remain separate work.

## Reporting an issue

Do not open a public issue containing secrets, personal records or live exploit payloads. Use GitHub's private vulnerability reporting if enabled for this repository; otherwise request a private contact channel without including sensitive details. Rotate a credential if it has actually been exposed; deleting its current file is not sufficient to remove it from history.

# Development

Use Python 3.12 and Node.js 24 for the documented development setup. Install dependencies with `python scripts/setup.py`; Python requirements and npm dependencies are locked.

```powershell
.\.venv\Scripts\python.exe scripts/run.py --dev
```

For production builds, run `npm --prefix apps/web run build -- --webpack` and restart the launcher. A prepared build is not rebuilt automatically on every source change.

## Isolated checks

Run tests only with synthetic data. Do not point a test process at an installation's personal storage.

```powershell
New-Item -ItemType Directory -Force .runtime/tmp | Out-Null
$env:TEMP=(Join-Path $PWD '.runtime/tmp')
$env:TMP=$env:TEMP
$env:PYTHONUTF8='1'
.\.venv\Scripts\python.exe -m pytest --basetemp=.runtime/pytest
npm --prefix apps/web test
npm --prefix apps/web run typecheck
```

Browser suites require an isolated launcher with `--test-mode --data-dir .runtime/e2e` and a separately selected `LIFEOS_TEST_BASE_URL` when another installation is running. See `apps/web/playwright.config.ts` and the launcher arguments; do not run fixtures against personal data. Recent UI changes still have deferred acceptance checks, so historical suite results are not current guarantees.

Preserve Hebrew RTL, English, all appearance modes and timezone/date-only semantics. Add database changes through Alembic migrations. Keep provider credentials server-side and require explicit confirmation for external or destructive actions.

Before publication, scan the actual staged files and commit history, not just the working tree. Exclude all personal operational documents and generated files. Dependency updates should be focused and verified; do not use force fixes that downgrade unrelated framework packages.

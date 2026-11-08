"""Build a source-only Linux preparation archive. No personal files/builds/secrets."""
import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def source_files():
    for parent in ("services/api/lifeos", "services/api/alembic", "services/worker",
                   "apps/web/app", "apps/web/components", "apps/web/lib", "apps/web/public", "apps/web/scripts", "deploy/linux"):
        for path in sorted((ROOT / parent).rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts and (path.suffix in {
                ".py", ".ts", ".tsx", ".css", ".json", ".png", ".svg", ".js", ".mjs", ".html",
                ".webmanifest", ".mako", ".md", ".service", ".target", ".conf",
            } or path.name == "Caddyfile"):
                yield path
    for name in ("scripts/server_manage.py", "scripts/finish_account_deletion.py", "scripts/provision_pilot_owner.py", "services/api/requirements.lock.txt",
                 "apps/web/package.json", "apps/web/package-lock.json", "apps/web/next.config.ts",
                 "apps/web/next-env.d.ts", "apps/web/tsconfig.json", "apps/web/postcss.config.mjs",
                 "apps/web/vitest.config.mts", "apps/web/tests/setup.ts", "apps/web/proxy.ts"):
        yield ROOT / name


def main():
    output = ROOT / ".runtime/artifacts/lifeos-linux-preparation.zip"
    output.parent.mkdir(parents=True, exist_ok=True)
    manifest = {}
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in source_files():
            relative = path.relative_to(ROOT).as_posix()
            raw = path.read_bytes()
            manifest[relative] = hashlib.sha256(raw).hexdigest()
            info = zipfile.ZipInfo(relative)
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, raw)
        archive.writestr("SOURCE_MANIFEST.json", json.dumps(manifest, indent=2))
    print(f"Created {len(manifest)} source files in .runtime/artifacts/lifeos-linux-preparation.zip")


if __name__ == "__main__":
    main()

"""Offline Linux server initialization/migration; never imports a personal installation."""
import argparse
import os
import secrets
import sys
from pathlib import Path
from uuid import uuid4

from cryptography.fernet import Fernet

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/api"))

from lifeos.data_lock import data_lock  # noqa: E402
from lifeos.db import migrate, open_database  # noqa: E402
from lifeos.deployment import DeploymentConfig, public_origin  # noqa: E402


def private_file(path, text):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
        stream.write(text)


def initialize(directory, config_dir, origin, *, fixture=False, pilot=False):
    directory, config_dir = Path(directory), Path(config_dir)
    if not directory.is_absolute() or not config_dir.is_absolute():
        raise ValueError("Explicit absolute directories required")
    directory, config_dir = directory.resolve(), config_dir.resolve()
    if fixture:
        if not all(p.is_relative_to(ROOT / ".runtime") for p in (directory, config_dir)):
            raise ValueError("Fixtures must stay in .runtime")
    elif sys.platform != "linux":
        raise ValueError("Real server initialization requires Linux")
    # Keep systemd environment values simple and non-interpreted.
    if any(any(c.isspace() or c in '\"\'\\$`' for c in p.as_posix()) for p in (directory, config_dir)):
        raise ValueError("Server paths must not contain whitespace or shell metacharacters")
    origin = public_origin(origin)
    env = {"LIFEOS_DEPLOYMENT_MODE": "server", "LIFEOS_PUBLIC_ORIGIN": origin,
           "LIFEOS_DATA_DIR": directory.as_posix(), "LIFEOS_TEST_MODE": "1" if fixture else "0"}
    DeploymentConfig.from_env(env)
    if config_dir.is_relative_to(directory) or directory.is_relative_to(config_dir):
        raise ValueError("Use separate data and configuration directories")
    if config_dir.is_relative_to(ROOT) and not fixture:
        raise ValueError("Configuration must stay outside source")
    if directory.exists() and any(directory.iterdir()):
        raise ValueError("Initialization requires an empty data directory; use migrate for an existing server")
    if config_dir.exists() and any(config_dir.iterdir()):
        raise ValueError("Initialization requires an empty configuration directory")
    for folder in (directory, config_dir, directory / "tmp", directory / "backups"):
        folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        folder.chmod(0o700)
    env.update({"LIFEOS_API_KEY": secrets.token_urlsafe(48), "LIFEOS_ACCOUNT_MODE": "1",
                "LIFEOS_WEB_PORT": "3000", "LIFEOS_API_PORT": "8765",
                "LIFEOS_BUILD_DIR": ".next-server-release", "NEXT_TELEMETRY_DISABLED": "1",
                "TMPDIR": (directory / "tmp").as_posix()})
    if pilot:
        env["LIFEOS_PILOT_OWNER_ID"] = str(uuid4())
    private_file(directory / "provider.key", Fernet.generate_key().decode() + "\n")
    private_file(config_dir / "runtime.env", "".join(f"{key}={value}\n" for key, value in env.items()))
    private_file(config_dir / "edge.env", f"LIFEOS_PUBLIC_ORIGIN={origin}\nLIFEOS_WEB_PORT=3000\n")
    migrate_directory(directory)


def migrate_directory(directory):
    with data_lock(directory):
        engine = open_database(directory)
        try:
            migrate(engine)
        finally:
            engine.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("init", "migrate"))
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--config-dir", type=Path)
    parser.add_argument("--origin")
    parser.add_argument("--test-mode", action="store_true")
    parser.add_argument("--pilot", action="store_true", help="Prepare closed pilot owner identity; provision offline before starting")
    args = parser.parse_args()
    try:
        if args.action == "init":
            if not all((args.data_dir, args.config_dir, args.origin)):
                parser.error("init requires --data-dir, --config-dir and --origin")
            initialize(args.data_dir, args.config_dir, args.origin, fixture=args.test_mode, pilot=args.pilot)
        else:
            config = DeploymentConfig.from_env()
            if not config.server:
                raise ValueError("Migration requires server environment")
            migrate_directory(Path(os.environ["LIFEOS_DATA_DIR"]))
        print("Server storage ready. No accounts or personal data imported.")
    except (ValueError, RuntimeError, OSError):
        print("Server preparation stopped. Check the private directories/configuration and stop services before migration.", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()

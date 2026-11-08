"""Run both loopback services, with one-time password setup and clean shutdown."""

import argparse
import atexit
import getpass
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
import time
import webbrowser
from contextlib import ExitStack
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dev", action="store_true", help="Use Next development server")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument(
        "--account-mode", action="store_true", help="Use isolated local account workspaces"
    )
    parser.add_argument("--web-port", type=int, default=3000)
    parser.add_argument("--api-port", type=int, default=8765)
    parser.add_argument("--build-dir", default=".next")
    parser.add_argument(
        "--test-mode", action="store_true", help="Allow E2E fixtures only in .runtime"
    )
    parser.add_argument("--data-dir", type=Path, help="Isolated data folder, e.g. for tests")
    args = parser.parse_args()
    if args.account_mode:
        os.environ["LIFEOS_ACCOUNT_MODE"] = "1"
    if (
        not all(1024 <= port <= 65535 for port in (args.web_port, args.api_port))
        or args.web_port == args.api_port
    ):
        raise SystemExit("Choose distinct ports between 1024 and 65535")
    if not re.fullmatch(r"\.next(?:-[a-z0-9-]+)?", args.build_dir):
        raise SystemExit("Build directory must be .next or .next-<name>")
    python = ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not python.exists():
        raise SystemExit("Run scripts/setup.py first")
    if Path(sys.executable).resolve() != python.resolve():
        raise SystemExit(
            subprocess.call([str(python), str(Path(__file__).resolve()), *sys.argv[1:]])
        )
    sys.path.insert(0, str(ROOT / "services/api"))
    from lifeos.db import data_directory, migrate, open_database
    from lifeos.security import initialize_password

    if args.data_dir:
        os.environ["LIFEOS_DATA_DIR"] = str(args.data_dir.resolve())
    directory = data_directory()
    from lifeos.account_transition import saved_account_build, saved_account_mode

    if saved_account_mode(directory):
        os.environ["LIFEOS_ACCOUNT_MODE"] = "1"
        if args.build_dir == ".next":
            args.build_dir = saved_account_build(directory)
    if args.test_mode:
        if not directory.is_relative_to(ROOT / ".runtime"):
            raise SystemExit("Test mode requires --data-dir inside .runtime")
        os.environ["LIFEOS_TEST_MODE"] = "1"
    from lifeos.data_lock import launcher_lock, runtime_lock

    lock_stack = ExitStack()
    lock_stack.enter_context(launcher_lock(directory))
    lock_stack.enter_context(runtime_lock(directory))
    atexit.register(lock_stack.close)
    if (directory / ".restore-in-progress").exists():
        raise SystemExit(
            "An interrupted recovery must be completed with scripts/recovery.py before starting LifeOS."
        )

    if os.environ.get("LIFEOS_ACCOUNT_MODE") != "1" and not (directory / "auth.json").exists():
        print(
            "Create your LifeOS local password (8+ characters). It is never sent to a cloud service."
        )
        password = os.environ.pop("LIFEOS_SETUP_PASSWORD", None)
        if password is None:
            password = getpass.getpass("Password: ")
            if password != getpass.getpass("Confirm password: "):
                raise SystemExit("Passwords do not match")
        initialize_password(directory, password)
    for port in (args.web_port, args.api_port):
        with socket.socket() as probe:
            try:
                probe.bind(("127.0.0.1", port))
            except OSError:
                raise SystemExit(
                    f"Port {port} is occupied; stop the existing service first"
                ) from None
    engine = open_database(directory)
    migrate(engine)
    from lifeos.account_operations import account_runtime

    account_runtime(engine)
    engine.dispose()
    environment = os.environ.copy()
    environment.update(
        LIFEOS_API_KEY=secrets.token_urlsafe(48),
        LIFEOS_DATA_DIR=str(directory),
        NEXT_TELEMETRY_DISABLED="1",
        PYTHONUTF8="1",
        LIFEOS_WEB_PORT=str(args.web_port),
        LIFEOS_API_PORT=str(args.api_port),
        LIFEOS_BUILD_DIR=args.build_dir,
    )
    temporary = directory / "tmp"
    temporary.mkdir(parents=True, exist_ok=True)
    environment.update(TEMP=str(temporary), TMP=str(temporary), TMPDIR=str(temporary))
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    if not npm:
        raise SystemExit("npm is missing; install Node.js")
    if not args.dev and not (ROOT / "apps/web" / args.build_dir / "BUILD_ID").exists():
        subprocess.run([npm, "run", "build"], cwd=ROOT / "apps/web", env=environment, check=True)
    children = []
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    try:
        children.append(
            subprocess.Popen(
                [
                    str(python),
                    str(ROOT / "scripts/supervise.py"),
                    "--parent-pid",
                    str(os.getpid()),
                    *(["--dev"] if args.dev else []),
                ],
                cwd=ROOT,
                env=environment,
                creationflags=flags,
            )
        )
        print(f"LifeOS: http://127.0.0.1:{args.web_port} — Ctrl+C to stop", flush=True)
        if not args.no_browser:
            time.sleep(3)
            webbrowser.open(f"http://127.0.0.1:{args.web_port}")
        while all(child.poll() is None for child in children):
            time.sleep(0.5)
        raise SystemExit("A service exited. Check the error above and restart LifeOS.")
    except KeyboardInterrupt:
        print("\nStopping LifeOS…")
    finally:
        for child in children:
            if child.poll() is None:
                child.terminate()
        for child in children:
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill()


if __name__ == "__main__":
    main()

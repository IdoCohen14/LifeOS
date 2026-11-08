"""Open the offline recovery wizard; never restore automatically."""

import argparse
import os
import secrets
import sys
import threading
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/api"))


def resolve_directory(explicit=None):
    from lifeos.db import data_directory

    if explicit is not None:
        return explicit.resolve()
    default = data_directory()
    candidates = {default}
    if os.name == "nt":
        local = Path.home() / "AppData/Local"
        candidates.add(local / "LifeOS")
        candidates.update((local / "Packages").glob("OpenAI.Codex_*/LocalCache/Local/LifeOS"))
    existing = sorted(
        path.resolve()
        for path in candidates
        if (path / "lifeos.sqlite3").is_file() and (path / "auth.json").is_file()
    )
    if len(existing) > 1:
        raise SystemExit(
            "Multiple LifeOS data folders found. Choose the intended folder with --data-dir; no data was changed."
        )
    return existing[0] if existing else default


def main():
    import uvicorn
    from lifeos.data_lock import _file_lock, data_lock
    from lifeos.recovery_ui import create_recovery_app

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--port", type=int, default=8877)
    parser.add_argument("--test-mode", action="store_true")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--token-file", type=Path, help="Fixture capability file, test mode only")
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error("Choose a port between1024 and65535")
    if args.test_mode:
        if args.data_dir is None or not args.data_dir.resolve().is_relative_to(ROOT / ".runtime"):
            parser.error("Test mode requires an explicit data directory under .runtime")
        if args.token_file is None or not args.token_file.resolve().is_relative_to(
            ROOT / ".runtime"
        ):
            parser.error("Test mode requires a capability file under .runtime")
    elif args.token_file or args.no_browser:
        parser.error("Capability files/no-browser are available only in isolated test mode")
    directory = resolve_directory(args.data_dir)
    try:
        # Do not retain the data guard: restore_backup must acquire its own exclusive locks.
        with data_lock(directory):
            pass
        with _file_lock(
            directory / ".lifeos-recovery-ui.lock", error="recovery_wizard_already_open"
        ):
            capability = secrets.token_urlsafe(32)
            app = create_recovery_app(
                directory, capability, port=args.port, test_mode=args.test_mode
            )
            server = uvicorn.Server(
                uvicorn.Config(
                    app, host="127.0.0.1", port=args.port, access_log=False, log_level="warning"
                )
            )
            if args.test_mode:
                args.token_file.parent.mkdir(parents=True, exist_ok=True)
                with args.token_file.open("w", encoding="utf-8") as output:
                    os.chmod(args.token_file, 0o600)
                    output.write(capability)

            def open_browser():
                deadline = time.monotonic() + 15
                while not server.started and not server.should_exit and time.monotonic() < deadline:
                    time.sleep(0.1)
                if server.started:
                    webbrowser.open(f"http://127.0.0.1:{args.port}/#{capability}")

            if not args.no_browser:
                threading.Thread(target=open_browser, daemon=True).start()
            print("LifeOS offline recovery wizard. Close this window after finishing.", flush=True)
            try:
                server.run()
            finally:
                if args.test_mode:
                    args.token_file.unlink(missing_ok=True)
    except RuntimeError:
        raise SystemExit(
            "Close LifeOS and any other recovery wizard, then retry. No restore was started."
        ) from None


if __name__ == "__main__":
    main()

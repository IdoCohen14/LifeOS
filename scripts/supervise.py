"""Own the API/web/worker tree; launcher and user browser remain outside its job."""

import argparse
import os
import shutil
import signal
import subprocess
import time
from pathlib import Path

from process_tree import ParentProcess, constrain_service_tree

ROOT = Path(__file__).resolve().parents[1]


def stop_children(children):
    deadline = time.monotonic() + 3
    for child in children:
        if os.name != "nt":
            try:
                os.killpg(child.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        elif child.poll() is None:
            child.terminate()
    for child in children:
        try:
            child.wait(timeout=max(0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            pass
    for child in children:
        if os.name != "nt":
            # Descendants can remain after the direct child has exited.
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        elif child.poll() is None:
            child.kill()
    deadline = time.monotonic() + 1
    for child in children:
        try:
            child.wait(timeout=max(0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--parent-pid", type=int, required=True)
    parser.add_argument("--dev", action="store_true")
    args = parser.parse_args()
    if args.parent_pid <= 0:
        raise SystemExit("A live launcher process is required")
    parent = ParentProcess(args.parent_pid)
    children = []
    stop_requested = False
    if os.name != "nt":

        def request_stop(signum, frame):
            nonlocal stop_requested
            stop_requested = True

        signal.signal(signal.SIGTERM, request_stop)
        signal.signal(signal.SIGINT, request_stop)
    try:
        if not parent.alive():
            return
        _job = constrain_service_tree()  # Keep the native handle open until OS exit.
        if not args.dev:
            subprocess.run(
                [shutil.which("node"), str(ROOT / "apps/web/scripts/verify-build.mjs")],
                cwd=ROOT / "apps/web",
                check=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
        python = ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        commands = [
            (
                [
                    str(python),
                    "-m",
                    "uvicorn",
                    "lifeos.main:create_app",
                    "--factory",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    os.environ["LIFEOS_API_PORT"],
                    "--no-access-log",
                ],
                ROOT / "services/api",
            ),
            (
                [
                    shutil.which("node"),
                    str(ROOT / "apps/web/node_modules/next/dist/bin/next") if args.dev else str(ROOT / "apps/web/scripts/start.mjs"),
                    *(["dev"] if args.dev else []),
                    "--hostname",
                    "127.0.0.1",
                    "--port",
                    os.environ["LIFEOS_WEB_PORT"],
                ],
                ROOT / "apps/web",
            ),
            ([str(python), str(ROOT / "services/worker/worker.py")], ROOT),
        ]
        for command, directory in commands:
            if stop_requested or not parent.alive():
                return
            children.append(
                subprocess.Popen(
                    command,
                    cwd=directory,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                    start_new_session=os.name != "nt",
                )
            )
        while (
            not stop_requested
            and parent.alive()
            and all(child.poll() is None for child in children)
        ):
            time.sleep(0.1)
        if not stop_requested and parent.alive():
            raise SystemExit("A LifeOS service exited; restart the launcher.")
    except KeyboardInterrupt:
        pass
    finally:
        stop_children(children)
        parent.close()
        # On Windows, this process's exit closes job and terminates any remaining descendants.


if __name__ == "__main__":
    main()

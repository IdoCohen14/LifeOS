"""Install project-local dependencies using an existing Python 3.11+ and Node 20.9+."""

import os
import shutil
import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    if sys.version_info < (3, 11):
        raise SystemExit("Python 3.11+ is required")
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    if not npm:
        raise SystemExit("Install Node.js 20.9+ (with npm), then retry")
    temporary = ROOT / ".runtime" / "tmp"
    temporary.mkdir(parents=True, exist_ok=True)
    os.environ.update(
        TEMP=str(temporary), TMP=str(temporary), TMPDIR=str(temporary), PYTHONUTF8="1"
    )
    python = ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not python.exists():
        venv.EnvBuilder(with_pip=True).create(ROOT / ".venv")
    subprocess.run(
        [
            str(python),
            "-m",
            "pip",
            "install",
            "-r",
            str(ROOT / "services/api/requirements.lock.txt"),
        ],
        check=True,
    )
    subprocess.run([npm, "ci", "--no-audit", "--no-fund"], cwd=ROOT / "apps/web", check=True)
    print("Setup complete. Run .venv\\Scripts\\python.exe scripts\\run.py on Windows.")


if __name__ == "__main__":
    main()

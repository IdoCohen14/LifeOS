"""Exercise the real local model with synthetic messages in an isolated database only."""

import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/api"))
os.environ["LIFEOS_DATA_DIR"] = str(ROOT / ".runtime/assistant-benchmark")
os.environ["LIFEOS_API_KEY"] = "isolated-benchmark-key"


def main():
    from fastapi.testclient import TestClient
    from lifeos.main import create_app
    from lifeos.security import initialize_password

    directory = Path(os.environ["LIFEOS_DATA_DIR"])
    if not (directory / "auth.json").exists():
        initialize_password(directory, "local benchmark fixture password")
    app = create_app()
    results = []
    with TestClient(
        app, base_url="http://127.0.0.1:8000", headers={"X-LifeOS-Key": "isolated-benchmark-key"}
    ) as client:
        login = client.post("/session", json={"password": "local benchmark fixture password"})
        client.headers["X-CSRF-Token"] = login.json()["csrf"]
        tomorrow = (datetime.now(ZoneInfo("Asia/Jerusalem")) + timedelta(days=1)).date().isoformat()
        cases = [
            ("hebrew_task", "תוסיף משימה להתקשר לרופא מחר", "task"),
            ("hebrew_event", "תקבע פגישה עם דנה מחר בשעה 14:00 למשך שעה", "event"),
            ("clarification", "תוסיף פגישה מחר", None),
            ("help", "איך מסנכרנים את Gmail באפליקציה?", None),
            ("scope", "תפתור לי שיעורי בית במתמטיקה: מה הנגזרת של x בריבוע?", None),
            ("free_slot", "מצא לי שעה פנויה מחר לפגישה עם דנה", "event"),
            ("schedule", "מה מתוכנן לי מחר?", None),
        ]
        for name, message, kind in cases:
            started = time.perf_counter()
            response = client.post("/assistant/chat", json={"message": message})
            result = response.json()
            proposal = result.get("proposal")
            actual = proposal.get("kind") if proposal else None
            date_ok = not proposal or (
                proposal["payload"].get("due", "")[:10] == tomorrow
                if kind == "task"
                else proposal["payload"].get("start", "")[:10] == tomorrow
            )
            passed = response.status_code == 200 and actual == kind and date_ok
            if name == "scope":
                passed = passed and "שיעורי בית" in result.get("reply", "")
            entry = {
                "case": name,
                "status": response.status_code,
                "kind": actual,
                "seconds": round(time.perf_counter() - started, 2),
                "passed": passed,
            }
            print(json.dumps(entry), flush=True)
            results.append(entry)
        first_message = "קבע פגישה עם דנה מחר בשעה 14:00"
        first = client.post("/assistant/chat", json={"message": first_message}).json()
        started = time.perf_counter()
        continuation = client.post(
            "/assistant/chat",
            json={
                "message": "60",
                "history": [
                    {"role": "user", "content": first_message},
                    {"role": "assistant", "content": first.get("reply", "")},
                ],
            },
        ).json()
        entry = {
            "case": "numeric_clarification",
            "seconds": round(time.perf_counter() - started, 2),
            "passed": first.get("proposal") is None
            and continuation.get("proposal", {}).get("kind") == "event",
        }
        print(json.dumps(entry), flush=True)
        results.append(entry)
    path = ROOT / ".runtime/assistant-benchmark/results.json"
    path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    if not all(row["passed"] for row in results):
        raise SystemExit("One or more local-model benchmark cases failed")


if __name__ == "__main__":
    main()

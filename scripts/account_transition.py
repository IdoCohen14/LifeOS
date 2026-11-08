"""Prepare an owner-only transition plan; apply/rollback require explicit offline approval."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/api"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("preview", "apply", "rollback"))
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--login")
    parser.add_argument("--target-id", help="Keep the reviewed target identity when refreshing a preview")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--backup-id")
    parser.add_argument("--approve", help="Exact approval digest from the reviewed plan")
    parser.add_argument(
        "--confirm", action="store_true", help="Confirm the reviewed source/target change"
    )
    args = parser.parse_args()
    if args.action != "preview" and (not args.confirm or not args.approve):
        parser.error("Apply/rollback require --confirm and the exact reviewed --approve digest")
    if args.action == "preview" and not args.login:
        parser.error("Preview requires the intended --login")
    if args.action == "apply" and args.plan is None:
        parser.error("Apply requires --plan")
    if args.action == "rollback" and args.backup_id is None:
        parser.error("Rollback requires --backup-id")
    from lifeos.account_transition import apply_transition, preview_transition, rollback_transition
    from lifeos.recovery import atomic_write

    try:
        if args.action == "preview":
            result = preview_transition(args.data_dir, args.login, target_id=args.target_id)
            if args.output:
                atomic_write(
                    args.output.resolve(), json.dumps(result, ensure_ascii=False, indent=2).encode()
                )
        elif args.action == "apply":
            if args.plan.stat().st_size > 65536:
                raise ValueError("Invalid transition plan size")
            plan = json.loads(args.plan.read_bytes())
            result = apply_transition(args.data_dir, plan, approval_digest=args.approve)
        else:
            result = rollback_transition(
                args.data_dir, args.backup_id, approval_digest=args.approve
            )
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as error:
        print(
            json.dumps(
                {
                    "error": type(error).__name__,
                    "message": "Transition did not complete. For apply/rollback close LifeOS first; refresh the plan if source data changed. Inspect the recovery marker before restarting.",
                }
            )
        )
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()

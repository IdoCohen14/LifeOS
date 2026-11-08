from lifeos.account_operations import AccountOperations
from lifeos.account_preferences import AccountPreferences
from lifeos.accounts import AccountService
from lifeos.models import Account
from sqlalchemy.orm import Session


def test_account_background_jobs_skip_disabled_and_continue_after_other_failure(client, setup_app):
    engine = setup_app[0].state.assistant.engine
    auth = AccountService(engine, enabled=True)
    owners = [auth.register("ops-" + name, "fixture password") for name in ("a", "b", "c")]
    for owner in owners:
        AccountPreferences(engine).put(owner, "briefings", {"daily_enabled": True}, 0)
    with Session(engine) as db:
        db.get(Account, owners[1]).enabled = False
        db.commit()
    seen = []

    def job(owner):
        seen.append(owner)
        if owner == owners[0]:
            raise ValueError("Synthetic failure")

    result = AccountOperations(engine, setup_app[1]).run("briefings", handler=job)
    assert set(seen) == {owners[0], owners[2]}
    assert result == {"completed": 1, "failed": 1}

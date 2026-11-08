import pytest
from lifeos.account_mail import AccountMail
from lifeos.account_providers import AccountProviders
from lifeos.accounts import AccountService


def test_mail_review_undo_and_reconfigured_identity_do_not_cross_accounts(client, setup_app):
    engine = setup_app[0].state.assistant.engine
    accounts = AccountService(engine, enabled=True)
    a = accounts.register("mail-a", "fixture password a")
    b = accounts.register("mail-b", "fixture password b")
    provider = AccountProviders(engine, setup_app[1])
    mail = AccountMail(engine)
    message = {
        "id": "same-mail",
        "subject": "Course fixture",
        "sender": "Teacher <fixture@college.edu>",
        "snippet": "Fixture",
        "unread": True,
        "received_at": 1000,
        "thread_id": "same-thread",
    }

    def seed(owner):
        provider.configure(owner, "gmail", {"refresh_token": "synthetic"})
        lease = provider.begin_sync(owner, "gmail")
        provider.commit_sync(owner, "gmail", lease["owner"], lease["revision"], [message])

    seed(a)
    seed(b)
    revision = mail.get(a)["revision"]
    assert len(mail.review(a, revision, message_id="same-mail")["queue"]) == 0
    assert len(mail.get(b)["queue"]) == 1
    assert provider.records(a, "gmail") == [message]
    assert len(mail.review(a, revision, message_id="same-mail", undo=True)["queue"]) == 1
    assert mail.review(a, revision, all=True)["queue"] == []
    seed(a)
    assert len(mail.get(a)["queue"]) == 1
    with pytest.raises(ValueError):
        mail.review(a, revision, message_id="same-mail")
    assert len(mail.get(b)["queue"]) == 1


def test_cached_store_ads_are_hidden_but_purchase_update_remains(client, setup_app):
    engine = setup_app[0].state.assistant.engine
    owner = AccountService(engine, enabled=True).register('commerce-mail', 'fixture password')
    provider = AccountProviders(engine, setup_app[1])
    provider.configure(owner, 'gmail', {'refresh_token': 'synthetic'})
    lease = provider.begin_sync(owner, 'gmail')
    messages = [
        {'id': 'advert', 'subject': 'New course essentials', 'sender': 'news@mail.aliexpress.com',
         'received_at': 2000, 'unread': True, 'labels': ['CATEGORY_PERSONAL']},
        {'id': 'purchase', 'subject': 'Your order has shipped', 'sender': 'noreply@mail.aliexpress.com',
         'received_at': 1000, 'unread': True, 'labels': ['CATEGORY_PROMOTIONS'], 'bulk': True},
    ]
    provider.commit_sync(owner, 'gmail', lease['owner'], lease['revision'], messages)
    snapshot = AccountMail(engine).get(owner)
    assert [row['id'] for row in snapshot['messages']] == ['purchase']
    assert [row['id'] for row in snapshot['queue']] == ['purchase']
    assert provider.records(owner, 'gmail') == messages

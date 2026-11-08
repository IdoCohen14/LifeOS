import httpx
import pytest
from lifeos.account_moodle import AccountMoodle
from lifeos.accounts import AccountService
from lifeos.google_calendar import GoogleProblem
from lifeos.moodle import parse_feed

HOST = 'moodle27.braude.ac.il'
HEADER = b'BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//Fixture//EN\r\n'
EVENT = b'BEGIN:VEVENT\r\nUID:fixture-event\r\nDTSTART:20261105T100000Z\r\nDTEND:20261105T110000Z\r\nSUMMARY:Fixture\r\nEND:VEVENT\r\n'
FEED = HEADER + EVENT + b'END:VCALENDAR\r\n'


@pytest.mark.parametrize('content', [
    HEADER + EVENT,
    HEADER + EVENT.removesuffix(b'END:VEVENT\r\n'),
    FEED.replace(b'UID:fixture-event\r\n', b''),
])
def test_incomplete_or_unidentified_feed_is_rejected_as_a_whole(content):
    with pytest.raises(GoogleProblem):
        parse_feed(content, HOST)


@pytest.mark.parametrize('field', [
    b'RDATE:20261106T100000Z',
    b'EXDATE:20261105T100000Z',
    b'RECURRENCE-ID:20261105T100000Z',
])
def test_unsupported_recurrence_is_not_silently_flattened(field):
    with pytest.raises(GoogleProblem, match='recurrence_not_supported'):
        parse_feed(FEED.replace(b'SUMMARY:Fixture', field+b'\r\nSUMMARY:Fixture'), HOST)


def test_many_events_are_refused_instead_of_returning_a_partial_calendar():
    content=HEADER+b''.join(EVENT.replace(b'fixture-event',f'fixture-{i}'.encode()) for i in range(5001))+b'END:VCALENDAR\r\n'
    with pytest.raises(GoogleProblem, match='event_limit_exceeded'):
        parse_feed(content, HOST)


def test_source_links_do_not_expose_unknown_fragment_tokens():
    url=f'https://{HOST}/mod/assign/view.php?id=123#authtoken=private-fixture-fragment'
    records=parse_feed(FEED.replace(b'SUMMARY:Fixture',b'SUMMARY:Fixture\r\nURL:'+url.encode()),HOST)
    assert records[0]['source_url'] == f'https://{HOST}/calendar/view.php'
    assert 'private-fixture-fragment' not in str(records)


def test_safe_assignment_link_is_preserved():
    url=f'https://{HOST}/mod/assign/view.php?id=123'
    records=parse_feed(FEED.replace(b'SUMMARY:Fixture',b'SUMMARY:Fixture\r\nURL:'+url.encode()),HOST)
    assert records[0]['source_url'] == url


def test_failed_feed_keeps_owned_cache_and_fragment_is_not_persisted(client, setup_app):
    engine = setup_app[0].state.assistant.engine
    owner = AccountService(engine, enabled=True).register('feed-corpus', 'fixture password')
    store = AccountMoodle(engine, setup_app[1])
    store.configure(owner, 'moodle', {'url': f'https://{HOST}/calendar/export_execute.php?authtoken=fixture'})
    content = [FEED]

    def factory(**kwargs):
        return httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, content=content[0])), **kwargs)

    store.sync(owner, client_factory=factory)
    before = store.records(owner, 'moodle')
    content[0] = HEADER + EVENT
    with pytest.raises(GoogleProblem):
        store.sync(owner, client_factory=factory)
    assert store.records(owner, 'moodle') == before
    assert store.status(owner, 'moodle')['syncing'] is False

    content[0] = FEED.replace(b'SUMMARY:Fixture', b'SUMMARY:Fixture\r\nURL:https://' + HOST.encode() + b'/mod/assign/view.php?id=123#authtoken=private-fixture-fragment')
    store.sync(owner, client_factory=factory)
    assert store.records(owner, 'moodle') == before
    assert 'private-fixture-fragment' not in str(store.records(owner, 'moodle'))

import pytest
from lifeos.gmail_history import history_changes
from lifeos.google_calendar import GoogleProblem


@pytest.mark.parametrize(
    "entry",
    [
        {"messages": None},
        {"messages": [None]},
        {"messagesAdded": None},
        {"messagesAdded": [None]},
        {"messagesAdded": [{"message": None}]},
        {"messages": [{"id": 42}]},
    ],
)
def test_malformed_history_is_a_controlled_provider_error(entry):
    with pytest.raises(GoogleProblem):
        history_changes(lambda *_: {"historyId": "200", "history": [entry]}, "100")


def test_history_collects_all_pages_and_uses_final_checkpoint():
    calls = []

    def get(path, params):
        calls.append((path, params))
        if len(calls) == 1:
            return {
                "historyId": "110",
                "nextPageToken": "second",
                "history": [
                    {"messages": [{"id": "a"}], "labelsRemoved": [{"message": {"id": "b"}}]}
                ],
            }
        return {
            "historyId": "150",
            "history": [
                {
                    "messagesAdded": [{"message": {"id": "a"}}],
                    "messagesDeleted": [{"message": {"id": "c"}}],
                }
            ],
        }

    assert history_changes(get, "100") == ({"a", "b", "c"}, "150")
    assert calls == [
        ("/history", {"startHistoryId": "100", "maxResults": 500}),
        ("/history", {"startHistoryId": "100", "maxResults": 500, "pageToken": "second"}),
    ]


def test_repeated_page_token_is_bounded_and_never_returns_partial_delta():
    calls = []

    def get(path, params):
        calls.append(params)
        return {
            "historyId": "200",
            "nextPageToken": "repeated",
            "history": [{"messages": [{"id": "a"}]}],
        }

    assert history_changes(get, "100") is None
    assert len(calls) == 10


def test_changed_message_overflow_falls_back_without_partial_checkpoint():
    result = {"historyId": "200", "history": [{"messages": [{"id": str(i)} for i in range(5001)]}]}
    assert history_changes(lambda *_: result, "100") is None


def test_expired_later_page_discards_preceding_delta():
    pages = iter(
        [
            {
                "historyId": "120",
                "nextPageToken": "second",
                "history": [{"messages": [{"id": "a"}]}],
            },
            None,
        ]
    )
    assert history_changes(lambda *_: next(pages), "100") is None

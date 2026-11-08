import base64
from datetime import date

import pytest
from lifeos.mail_body import calendar_text
from lifeos.mail_calendar import candidate


def part(text, mime="text/html", **extra):
    return {
        "mimeType": mime,
        "body": {"data": base64.urlsafe_b64encode(text.encode()).decode()},
        **extra,
    }


def picked(payload, subject="מועד הגשה חשוב"):
    text = calendar_text(payload)
    return candidate(
        {
            "id": "fixture",
            "subject": subject,
            "sender": "teacher@college.ac.il",
            "labels": ["INBOX"],
            "calendar_text": text,
        },
        "Asia/Jerusalem",
        date(2026, 11, 1),
    )


def test_html_dates_entities_inline_text_and_explicit_time_range():
    value = picked(part("<html><body><p>תאריך:&nbsp;05&#47;11&#47;2026</p></body></html>"))
    assert value == {"start": "2026-11-05", "end": "2026-11-06", "all_day": True}
    value = picked(
        part("<p>Date: <span>2026-</span><b>11-05</b></p><div>Time: 08:30–10:00</div>"), "Meeting"
    )
    assert value == {
        "start": "2026-11-05T06:30:00+00:00",
        "end": "2026-11-05T08:00:00+00:00",
        "all_day": False,
    }


def test_plain_precedes_conflicting_html_alternative():
    payload = {
        "mimeType": "multipart/alternative",
        "parts": [part("תאריך:05/11/2026", "text/plain"), part("<p>תאריך:06/11/2026</p>")],
    }
    assert picked(payload)["start"] == "2026-11-05"


@pytest.mark.parametrize(
    "hidden",
    [
        "<script>תאריך:06/11/2026</script>",
        '<p style="font-size:0">תאריך:06/11/2026</p>',
        '<p style="color:transparent">תאריך:06/11/2026</p>',
        '<p style="color:rgba(0,0,0,0)">תאריך:06/11/2026</p>',
        "<del>תאריך:06/11/2026</del>",
        "<head><title>תאריך:06/11/2026</title></head>",
        "<template>תאריך:06/11/2026</template>",
        "<noscript>תאריך:06/11/2026</noscript>",
        "<svg><text>תאריך:06/11/2026</text></svg>",
        "<p hidden>תאריך:06/11/2026</p>",
        '<p aria-hidden="true">תאריך:06/11/2026</p>',
        '<p style="display: none">תאריך:06/11/2026</p>',
        '<p style="visibility: hidden">תאריך:06/11/2026</p>',
        "<blockquote><p>תאריך:06/11/2026</p></blockquote>",
        '<div class="gmail_quote"><p>תאריך:06/11/2026</p></div>',
        "<!-- תאריך:06/11/2026 -->",
    ],
)
def test_hidden_active_and_quoted_dates_are_not_used(hidden):
    assert picked(part("<div>תאריך:05/11/2026</div>" + hidden))["start"] == "2026-11-05"
    assert picked(part("<p>אין מועד חדש בהודעה</p>" + hidden)) is None


def test_attachments_and_forwarded_message_containers_are_not_bodies():
    payload = {
        "mimeType": "multipart/mixed",
        "parts": [
            part("תאריך:06/11/2026", "text/plain", filename="attached.txt"),
            part(
                "תאריך:06/11/2026",
                "text/plain",
                headers=[{"name": "Content-Disposition", "value": "attachment"}],
            ),
            {"mimeType": "message/rfc822", "parts": [part("תאריך:06/11/2026", "text/plain")]},
            part("<p>תאריך:05/11/2026</p>"),
        ],
    }
    assert picked(payload)["start"] == "2026-11-05"
    assert calendar_text({"mimeType": "multipart/mixed", "parts": payload["parts"][:-1]}) is None


@pytest.mark.parametrize(
    "html",
    [
        "<div>תאריך:05/11/2026</span>",
        "<div>תאריך:05/11/2026",
        '<style>.invisible{display:none}</style><p class="invisible">תאריך:05/11/2026</p>',
        '<link rel="stylesheet" href="https://example.test/x.css"><p>תאריך:05/11/2026</p>',
        '<p style="position:absolute;left:-9999px">תאריך:05/11/2026</p>',
    ],
)
def test_malformed_or_css_dependent_html_is_rejected(html):
    with pytest.raises(ValueError):
        calendar_text(part(html))


def test_unsupported_charset_invalid_base64_and_mime_shape_are_rejected():
    values = [
        part(
            "Date:2026-11-05",
            headers=[{"name": "Content-Type", "value": "text/html; charset=windows-1255"}],
        ),
        {"mimeType": "text/plain", "body": {"data": "%%invalid%%"}},
        {"mimeType": "multipart/mixed", "parts": "not a list"},
        {"mimeType": "multipart/mixed", "parts": [None]},
        {"mimeType": "text/html", "body": {"data": ["bad"]}},
    ]
    for payload in values:
        with pytest.raises(ValueError):
            calendar_text(payload)


def test_mime_and_decoded_budgets_are_enforced():
    with pytest.raises(ValueError):
        calendar_text(
            {"mimeType": "multipart/mixed", "parts": [part("a", "text/plain") for _ in range(100)]}
        )
    with pytest.raises(ValueError):
        calendar_text(part("א" * 10001))
    nested = part("תאריך:05/11/2026")
    for _ in range(21):
        nested = {"mimeType": "multipart/mixed", "parts": [nested]}
    with pytest.raises(ValueError):
        calendar_text(nested)


def test_html_does_not_relax_existing_date_and_cancel_rules():
    for text in ["תאריך:05/11/2026 או 06/11/2026", "מחר", "תאריך:05/11/2026 בוטל"]:
        assert picked(part("<p>" + text + "</p>")) is None


def test_valid_plain_ignores_unusable_html_alternatives():
    for alternative in [
        part("<style>.x{display:none}</style>"),
        {"mimeType": "text/html", "body": {"data": "%%invalid%%"}},
        part(
            "ignored",
            headers=[{"name": "Content-Type", "value": "text/html; charset=windows-1255"}],
        ),
    ]:
        payload = {
            "mimeType": "multipart/alternative",
            "parts": [part("תאריך:05/11/2026", "text/plain"), alternative],
        }
        assert picked(payload)["start"] == "2026-11-05"


def test_outlook_reply_boundary_and_tiny_css_text_are_rejected():
    for html in [
        '<div id="divRplyFwdMsg">Old message</div><p>תאריך:05/11/2026</p>',
        '<p style="font-size:0.01px">תאריך:05/11/2026</p>',
    ]:
        with pytest.raises(ValueError):
            calendar_text(part(html))

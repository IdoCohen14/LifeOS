import pytest
from lifeos.mail_filter import relevant


def test_mail_relevance():
    assert relevant({"subject": "ראיון למשרת פיתוח", "sender": "noreply@jobs.test"})
    assert relevant({"subject": "מטלה חדשה בקורס", "labels": ["CATEGORY_UPDATES"]})
    assert relevant({"subject": "שלום", "sender": "דנה <dana@gmail.com>"})
    assert relevant({"subject": "Team meeting", "sender": "manager@company.test"})
    assert not relevant({"subject": "מבצע על קורס חדש", "sender": "sales@gmail.com"})
    assert not relevant({"subject": "Your weekly digest", "sender": "newsletter@gmail.com"})
    assert not relevant(
        {"subject": "Notification", "sender": "friend@gmail.com", "labels": ["CATEGORY_SOCIAL"]}
    )
    assert not relevant({"subject": "Hello", "sender": "news@brand.test", "bulk": True})


@pytest.mark.parametrize('subject,sender,labels', [
    ('Picked just for you', 'AliExpress <news@mail.aliexpress.com>', []),
    ('New course essentials', 'news@aliexpress.com', []),
    ('Discover something new', 'news@temu.com', ['CATEGORY_PERSONAL']),
    ('Your next order deserves a discount', 'news@amazon.com', []),
    ('Complete your order', 'news@aliexpress.com', []),
    ('Job opportunities this week', 'news@shop.test', ['CATEGORY_PROMOTIONS']),
    ('מבצעים להזמנה הבאה שלך', 'news@aliexpress.com', []),
])
def test_store_marketing_is_hidden(subject, sender, labels):
    assert not relevant({'subject': subject, 'sender': sender, 'labels': labels})


@pytest.mark.parametrize('subject', [
    'Your order has shipped',
    'Order confirmation #123456',
    'Order 123456 confirmed',
    'Your package is on its way',
    'Your refund has been issued',
    'ההזמנה שלך נשלחה',
    'אישור הזמנה מספר 123456',
    'החבילה שלך נמסרה',
    'Your order has shipped — free shipping on your next purchase',
])
def test_purchase_updates_survive_bulk_and_promotion_labels(subject):
    assert relevant({'subject': subject, 'sender': 'noreply@mail.aliexpress.com',
                     'labels': ['CATEGORY_PROMOTIONS', 'CATEGORY_UPDATES'], 'bulk': True})


def test_generic_purchase_receipt_and_personal_correspondence_are_preserved():
    assert relevant({'subject': 'Payment receipt for order #123', 'sender': 'noreply@shop.test', 'bulk': True})
    assert relevant({'subject': 'שלום', 'sender': 'דנה <dana@gmail.com>'})

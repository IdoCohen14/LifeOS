"""Local, deterministic relevance filtering; never modifies the Gmail mailbox."""

import re
from email.utils import parseaddr

TOPICS = re.compile(
    r"לימוד|אוניברסיט|מכלל|סילבוס|מבחן|הרצא|תרגול|מטלה|מלגה|קורס|"
    r"משרה|משרות|דרושים|מועמדות|ראיון|קורות חיים|גיוס עובדים|"
    r"פגישת עבודה|ישיבת צוות|פרויקט|תלוש|משכורת|"
    r"\b(university|college|syllabus|exam|lecture|assignment|scholarship|"
    r"course|homework|job|jobs|career|careers|vacancy|hiring|recruitment|"
    r"interview|resume|application status|team meeting|project|payroll|salary)\b",
    re.IGNORECASE,
)
ADS = re.compile(
    r"מבצע|הנחה|קופון|משלוח חינם|קנו עכשיו|הטבה|בלאק פריידי|"
    r"\b(sale|discount|coupon|promo code|free shipping|shop now|black friday)\b",
    re.IGNORECASE,
)
# A purchase update is distinct from an invitation to buy or finish a cart.
# Only explicit transaction subjects can override marketing/bulk labels.
PURCHASE_UPDATE = re.compile(
    r"\b(?:order confirmation|payment receipt|shipping confirmation|delivery confirmation|"
    r"(?:your\s+)?order(?:\s+(?:number\s*)?[#:]?\s*[a-z0-9-]*\d[a-z0-9-]*)?\s+"
    r"(?:(?:has been|has|is|was)\s+)?(?:confirmed|received|paid|shipped|dispatched|delivered|cancelled|canceled)|"
    r"(?:your\s+)?(?:package|parcel|shipment)\s+(?:(?:has been|has|is|was)\s+)?"
    r"(?:shipped|delivered|out for delivery|on its way|ready for pickup|awaiting collection)|"
    r"(?:your\s+)?refund\s+(?:(?:has been|is|was)\s+)?(?:issued|processed|approved))\b|"
    r"אישור (?:הזמנה|תשלום)|קבלה (?:עבור|על) (?:הזמנה|תשלום)|"
    r"(?:ההזמנה|הזמנתך|החבילה|המשלוח)(?:\s+שלך)?\s+(?:אושרה|התקבלה|נשלחה|נשלח|נמסרה|נמסר|בוטלה|בוטל|בדרך אליך|מוכנה לאיסוף|ממתינה לאיסוף)|"
    r"החזר כספי (?:אושר|בוצע)",
    re.IGNORECASE,
)
STORE_DOMAINS = {
    "aliexpress.com", "alibaba.com", "temu.com", "shein.com", "iherb.com",
    "amazon.com", "amazon.co.uk", "amazon.de", "ebay.com", "ebay.co.uk",
    "ksp.co.il", "ivory.co.il",
}
PERSONAL_DOMAINS = {
    "gmail.com",
    "googlemail.com",
    "outlook.com",
    "hotmail.com",
    "live.com",
    "yahoo.com",
    "icloud.com",
    "proton.me",
    "protonmail.com",
    "walla.co.il",
}


def relevant(message):
    subject = str(message.get("subject", ""))
    sender = parseaddr(str(message.get("sender", "")))[1].lower()
    domain = sender.rsplit("@", 1)[-1]
    labels = set(message.get("labels", []))
    if PURCHASE_UPDATE.search(subject):
        return True
    if (any(domain == store or domain.endswith("." + store) for store in STORE_DOMAINS)
            or "CATEGORY_PROMOTIONS" in labels):
        return False
    if ADS.search(subject):
        return False
    text = subject + " " + str(message.get("snippet", ""))
    if TOPICS.search(text) or re.search(r"\.(ac\.il|edu)(?:\.|$)", sender):
        return True
    if labels & {"CATEGORY_PROMOTIONS", "CATEGORY_SOCIAL", "CATEGORY_FORUMS", "CATEGORY_UPDATES"}:
        return False
    if message.get("bulk") or re.search(
        r"no.?reply|do.?not.?reply|newsletter|notification|mailer|marketing", sender
    ):
        return False
    return bool(
        sender
        and (
            domain in PERSONAL_DOMAINS
            or "CATEGORY_PERSONAL" in labels
            or re.match(r"^(re|fw|fwd):", subject, re.IGNORECASE)
        )
    )

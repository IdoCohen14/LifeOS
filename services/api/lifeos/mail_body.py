"""Bounded, transient mail text; HTML is parsed as data, never rendered."""

import base64
import re
from email.message import Message
from html.parser import HTMLParser

MAX_BYTES = 20000
MAX_PARTS = 100
MAX_DEPTH = 20


class _TextHTML(HTMLParser):
    void = {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }
    blocked = {
        "head",
        "script",
        "style",
        "template",
        "noscript",
        "svg",
        "math",
        "iframe",
        "object",
        "blockquote",
        "del",
        "s",
        "strike",
    }
    blocks = {
        "p",
        "div",
        "br",
        "hr",
        "li",
        "ul",
        "ol",
        "table",
        "tr",
        "td",
        "th",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "section",
        "article",
        "header",
        "footer",
    }
    formatting = {
        "color",
        "background",
        "background-color",
        "font-family",
        "font-size",
        "font-weight",
        "font-style",
        "line-height",
        "text-align",
        "text-decoration",
        "white-space",
        "width",
        "max-width",
        "table-layout",
        "border-collapse",
        "vertical-align",
    }

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.text = []

    @staticmethod
    def hidden_style(style):
        declarations = []
        for item in style.split(";"):
            if not item.strip():
                continue
            if ":" not in item:
                raise ValueError("Unsupported HTML style")
            name, value = item.split(":", 1)
            name = name.strip().lower()
            value = re.sub(r"\s*!important\s*$", "", value.strip().lower())
            declarations.append((name, value))
        if any(
            (name == "display" and value == "none")
            or (name == "visibility" and value in {"hidden", "collapse"})
            or (name == "opacity" and re.fullmatch(r"0(?:\.0+)?%?", value))
            or (name == "font-size" and re.fullmatch(r"0(?:\.0+)?(?:px|pt|em|rem|%)?", value))
            or (
                name == "color"
                and (
                    value == "transparent"
                    or re.fullmatch(
                        r"(?:rgba|hsla)\([^()]*[,/]\s*0(?:\.0+)?%?\s*\)|#[0-9a-f]{6}00|#[0-9a-f]{3}0",
                        value,
                    )
                )
            )
            for name, value in declarations
        ):
            return True
        for name, value in declarations:
            if any(mark in value for mark in ("url(", "var(", "calc(", "expression", "@", "\\")):
                raise ValueError("Unsupported HTML style")
            if name == "font-size":
                size = re.fullmatch(r"(\d+(?:\.\d+)?)(px|pt)", value)
                if size:
                    if float(size[1]) < (8 if size[2] == "px" else 6):
                        raise ValueError("Unreadable HTML font size")
                elif value not in {"small", "medium", "large", "x-large", "xx-large"}:
                    raise ValueError("Unsupported HTML font size")
            if name == "color" and not re.fullmatch(
                r"#[0-9a-f]{3}(?:[0-9a-f]{3})?|[a-z]+|rgb\([0-9,% .]+\)", value
            ):
                raise ValueError("Unsupported HTML color")
            if name in {"display", "visibility", "opacity"}:
                allowed = {
                    "display": {
                        "block",
                        "inline",
                        "inline-block",
                        "table",
                        "table-cell",
                        "table-row",
                    },
                    "visibility": {"visible"},
                    "opacity": {"1", "1.0"},
                }
                if value not in allowed[name]:
                    raise ValueError("Unsupported HTML style")
            elif name not in _TextHTML.formatting and not re.fullmatch(
                r"(?:border|margin|padding)(?:-[a-z]+)?", name
            ):
                raise ValueError("Unsupported HTML style")
        return False

    def handle_starttag(self, tag, attrs):
        if len(self.stack) >= 40:
            raise ValueError("HTML too deeply nested")
        attributes = dict(attrs)
        if len(attributes) != len(attrs):
            raise ValueError("Duplicate HTML attributes")
        if tag == "link" and "stylesheet" in (attributes.get("rel") or "").lower().split():
            raise ValueError("Stylesheets are unsupported")
        if (attributes.get("id") or "").lower() == "divrplyfwdmsg":
            raise ValueError("Unsupported forwarded HTML structure")
        parent_hidden = bool(self.stack and self.stack[-1][1])
        hidden = parent_hidden or tag in self.blocked
        if not hidden:
            hidden = (
                "hidden" in attributes
                or (attributes.get("aria-hidden") or "").lower() == "true"
                or bool(
                    {"gmail_quote", "yahoo_quoted"}
                    & set((attributes.get("class") or "").lower().split())
                )
                or self.hidden_style(attributes.get("style") or "")
            )
        if tag in self.blocks and not parent_hidden:
            self.text.append("\n")
        if tag not in self.void:
            self.stack.append((tag, hidden))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.void:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if tag in self.void or not self.stack or self.stack[-1][0] != tag:
            raise ValueError("Malformed HTML")
        self.stack.pop()
        if tag in self.blocks and not (self.stack and self.stack[-1][1]):
            self.text.append("\n")

    def handle_data(self, data):
        if any(tag == "style" for tag, _ in self.stack) and data.strip():
            raise ValueError("Stylesheets are unsupported")
        if not (self.stack and self.stack[-1][1]):
            self.text.append(data)

    def handle_decl(self, decl):
        if decl.strip().lower() != "doctype html":
            raise ValueError("Unsupported HTML declaration")

    def unknown_decl(self, data):
        raise ValueError("Unsupported HTML declaration")

    def value(self, raw):
        self.feed(raw)
        self.close()
        if self.stack:
            raise ValueError("Unclosed HTML")
        return "".join(self.text).strip()


def _headers(part):
    values = part.get("headers", [])
    if not isinstance(values, list) or len(values) > MAX_PARTS:
        raise ValueError("Malformed MIME headers")
    result = Message()
    for header in values:
        if (
            not isinstance(header, dict)
            or not isinstance(header.get("name"), str)
            or not isinstance(header.get("value"), str)
        ):
            raise ValueError("Malformed MIME headers")
        result[header["name"]] = header["value"]
    return result


def _decoded(parts):
    texts, total = [], 0
    for part, headers in parts:
        charset = headers.get_content_charset() or "utf-8"
        if charset.lower() not in {"utf-8", "utf8", "us-ascii", "ascii"}:
            raise ValueError("Unsupported mail charset")
        body = part.get("body", {})
        if not isinstance(body, dict):
            raise ValueError("Malformed MIME body")
        data = body.get("data", "")
        if not isinstance(data, str) or len(data) > 30000:
            raise ValueError("Malformed or oversized mail text")
        if not data:
            continue
        raw = base64.b64decode(data + "=" * (-len(data) % 4), altchars=b"-_", validate=True)
        total += len(raw)
        if total > MAX_BYTES:
            raise ValueError("Mail text too large")
        text = raw.decode("ascii" if charset.lower() in {"ascii", "us-ascii"} else "utf-8")
        if text.strip():
            texts.append(text)
    return texts


def calendar_text(payload):
    """Return bounded plain/HTML text or None. Unsupported bodies raise ValueError."""
    parts = [(payload, 0)]
    plain, html = [], []
    visited = 0
    while parts:
        part, depth = parts.pop()
        visited += 1
        if visited > MAX_PARTS or depth > MAX_DEPTH or not isinstance(part, dict):
            raise ValueError("Malformed or excessive MIME parts")
        headers = _headers(part)
        mime = part.get("mimeType", "")
        if not isinstance(mime, str):
            raise ValueError("Malformed MIME type")
        mime = mime.lower()
        if (
            part.get("filename")
            or headers.get_content_disposition() == "attachment"
            or mime == "message/rfc822"
        ):
            continue
        children = part.get("parts", [])
        if not isinstance(children, list):
            raise ValueError("Malformed MIME parts")
        if children:
            if not mime.startswith("multipart/") or len(children) + len(parts) > MAX_PARTS:
                raise ValueError("Malformed or excessive MIME parts")
            parts.extend((child, depth + 1) for child in reversed(children))
            continue
        if mime in {"text/plain", "text/html"}:
            (plain if mime == "text/plain" else html).append((part, headers))
    # Decode only the selected representation: unusable HTML cannot break valid plain mail.
    values = _decoded(plain)
    if not values:
        values = [_TextHTML().value(text) for text in _decoded(html)]
    text = "\n".join(values).strip()
    if len(text.encode("utf-8")) > MAX_BYTES or "\x00" in text:
        raise ValueError("Unsupported mail text")
    return text or None

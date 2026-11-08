"""Bounded plain-text extraction worker. Receives bytes on stdin; emits JSON only."""

import io
import json
import re
import sys
import zipfile

from defusedxml import ElementTree

MAX_TEXT = 500000
MAX_DECODED = 16 * 1024 * 1024


def extract(data: bytes, suffix: str):
    sections = []
    remaining = MAX_TEXT
    truncated = False

    def append(reference, value):
        nonlocal remaining, truncated
        value = value.replace("\x00", "").strip()
        if len(sections) >= 1000 or remaining <= 0:
            truncated = True
            return False
        if len(value) > remaining:
            value = value[:remaining]
            truncated = True
        if value:
            sections.append({"reference": reference, "text": value})
            remaining -= len(value)
        return not truncated

    if suffix in (".txt", ".md"):
        text = data.decode("utf-8-sig")
        if "\x00" in text:
            raise ValueError("Binary data is not a text document")
        append("document", text)
    elif suffix in (".docx", ".pptx"):
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            infos = archive.infolist()
            if len(infos) > 2000 or sum(entry.file_size for entry in infos) > 16 * 1024 * 1024:
                raise ValueError("Expanded Office document exceeds limits")
            if any(info.flag_bits & 1 for info in infos):
                raise ValueError("Encrypted archives are unsupported")
            if suffix == ".docx":
                root = ElementTree.fromstring(archive.read("word/document.xml"))
                paragraphs = [node for node in root.iter() if node.tag.split("}")[-1] == "p"]
                for i, node in enumerate(paragraphs):
                    text = " ".join(
                        n.text or "" for n in node.iter() if n.tag.split("}")[-1] == "t"
                    )
                    if not append(f"paragraph:{i + 1}", text):
                        break
            else:
                names = sorted(
                    (
                        name
                        for name in archive.namelist()
                        if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)
                    ),
                    key=lambda name: int(re.search(r"(\d+)\.xml$", name).group(1)),
                )
                if not names:
                    raise ValueError("No slides found")
                for name in names:
                    root = ElementTree.fromstring(archive.read(name))
                    number = re.search(r"(\d+)\.xml$", name).group(1)
                    text = " ".join(
                        n.text or "" for n in root.iter() if n.tag.split("}")[-1] == "t"
                    )
                    if not append(f"slide:{number}", text):
                        break
    elif suffix == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data), strict=True)
        if reader.is_encrypted:
            raise ValueError("Encrypted PDFs are unsupported")
        if len(reader.pages) > 500:
            raise ValueError("PDF exceeds 500 pages")
        decoded = 0
        for i, page in enumerate(reader.pages):
            contents = page.get_contents()
            size = len(contents.get_data()) if contents is not None else 0
            decoded += size
            if size > 8 * 1024 * 1024 or decoded > MAX_DECODED:
                raise ValueError("PDF decoded content exceeds cumulative extraction limit")
            if not append(f"page:{i + 1}", page.extract_text() or ""):
                break
    else:
        raise ValueError("Unsupported document type")
    return {
        "sections": sections,
        "status": "truncated" if truncated else "indexed" if sections else "no_text",
    }


if __name__ == "__main__":
    try:
        from extraction_limits import limit_worker_memory

        limit_worker_memory()
        payload = extract(sys.stdin.buffer.read(8 * 1024 * 1024 + 1), sys.argv[1])
        sys.stdout.buffer.write(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
    except Exception:
        # Do not log original document text, filenames, or parser internals.
        sys.stderr.write("Document could not be safely extracted")
        raise SystemExit(1) from None

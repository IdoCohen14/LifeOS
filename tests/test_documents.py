import base64
import io
import zipfile

from test_academic import course_fixture


def upload(client, course, filename, content):
    return client.post(
        "/academic/documents",
        json={
            "course_id": course["id"],
            "filename": filename,
            "content_base64": base64.b64encode(content).decode(),
        },
    )


def test_hebrew_document_search_and_attachment(client):
    _, course = course_fixture(client)
    content = "מרחב וקטורי הוא קבוצה עם פעולות חיבור וכפל בסקלר".encode()
    response = upload(client, course, "אלגברה.md", content)
    assert response.status_code == 201
    doc = response.json()
    assert doc["text_status"] == "indexed"
    hits = client.get("/academic/documents/search", params={"q": "וקטורי"}).json()
    assert hits[0]["document_id"] == doc["id"]
    assert hits[0]["reference"] == "document"
    assert "וקטורי" in hits[0]["excerpt"]
    downloaded = client.get(f"/academic/documents/{doc['id']}/download")
    assert downloaded.content == content
    assert "attachment" in downloaded.headers["content-disposition"]
    assert client.delete(f"/academic/courses/{course['id']}").status_code == 409
    assert client.delete(f"/academic/documents/{doc['id']}").status_code == 204
    assert client.get("/academic/documents/search", params={"q": "וקטורי"}).json() == []


def test_rejects_unsafe_or_malformed_files(client):
    _, course = course_fixture(client)
    assert upload(client, course, "../../bad.txt", b"ok").status_code == 422
    assert upload(client, course, "code.exe", b"MZ").status_code == 422
    assert upload(client, course, "broken.pdf", b"not a pdf").status_code == 422
    assert upload(client, course, "nul.txt", b"a\0b").status_code == 422


def test_pptx_sources_and_zip_expansion_guard(client):
    _, course = course_fixture(client)
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("ppt/slides/slide1.xml", "<slide><t>Linear algebra</t></slide>")
    response = upload(client, course, "slides.pptx", stream.getvalue())
    assert response.status_code == 201
    hits = client.get("/academic/documents/search", params={"q": "algebra"}).json()
    assert hits[0]["reference"] == "slide:1"
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("word/document.xml", b"A" * (17 * 1024 * 1024))
    assert upload(client, course, "bomb.docx", stream.getvalue()).status_code == 422


def test_docx_pdf_and_xml_entity_safety(client):
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

    _, course = course_fixture(client)
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("word/document.xml", "<document><p><t>vector notes</t></p></document>")
    assert upload(client, course, "notes.docx", stream.getvalue()).status_code == 201
    assert (
        client.get("/academic/documents/search", params={"q": "vector"}).json()[0]["reference"]
        == "paragraph:1"
    )
    writer = PdfWriter()
    page = writer.add_blank_page(width=200, height=200)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})}
    )
    content = DecodedStreamObject()
    content.set_data(b"BT /F1 12 Tf 10 100 Td (matrix theory) Tj ET")
    page[NameObject("/Contents")] = writer._add_object(content)
    pdf = io.BytesIO()
    writer.write(pdf)
    assert upload(client, course, "study.pdf", pdf.getvalue()).status_code == 201
    assert (
        client.get("/academic/documents/search", params={"q": "matrix"}).json()[0]["reference"]
        == "page:1"
    )
    writer.encrypt("secret")
    locked = io.BytesIO()
    writer.write(locked)
    assert upload(client, course, "locked.pdf", locked.getvalue()).status_code == 422
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr(
            "word/document.xml",
            '<!DOCTYPE d [<!ENTITY leak SYSTEM "file:///etc/passwd">]><document><p><t>&leak;</t></p></document>',
        )
    assert upload(client, course, "entity.docx", stream.getvalue()).status_code == 422

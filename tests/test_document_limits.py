import io
import subprocess
import sys
from pathlib import Path

import pytest


def test_extraction_worker_enforces_memory_ceiling():
    source = "from lifeos.extraction_limits import limit_worker_memory\nlimit_worker_memory()\ntry:\n bytearray(600*1024*1024)\nexcept MemoryError:\n print('bounded')\n"
    result = subprocess.run(
        [sys.executable, "-c", source],
        cwd=Path(__file__).resolve().parents[1] / "services/api",
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == "bounded"


@pytest.mark.skipif(sys.platform != "win32", reason="Windows extraction job process limit")
def test_extraction_worker_cannot_spawn_child_processes():
    source = """
import subprocess,sys
from lifeos.extraction_limits import limit_worker_memory
limit_worker_memory()
try:
    child=subprocess.Popen([sys.executable,'-c','pass'])
except OSError:
    print('bounded')
else:
    child.wait(timeout=3)
    raise AssertionError('Extraction job allowed a child process')
"""
    result = subprocess.run(
        [sys.executable, "-c", source],
        cwd=Path(__file__).resolve().parents[1] / "services/api",
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 0 and result.stdout.strip() == "bounded"


def test_pdf_cumulative_decoded_budget(monkeypatch):
    from lifeos import document_extract
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, NameObject

    writer = PdfWriter()
    page = writer.add_blank_page(width=100, height=100)
    stream = DecodedStreamObject()
    stream.set_data(b" " * 100)
    page[NameObject("/Contents")] = writer._add_object(stream)
    content = io.BytesIO()
    writer.write(content)
    monkeypatch.setattr(document_extract, "MAX_DECODED", 64)
    with pytest.raises(ValueError, match="cumulative"):
        document_extract.extract(content.getvalue(), ".pdf")

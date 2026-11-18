import pymupdf
import pytest

from app.core.errors import InvalidDocumentError
from app.services.ingestion_service import chunk_pdf_pages, extract_pdf_pages, extract_pdf_text


def _pdf_bytes(text: str = "") -> bytes:
    document = pymupdf.open()
    page = document.new_page()
    if text:
        page.insert_text((72, 72), text)
    result = document.tobytes()
    document.close()
    return result


def test_extract_pdf_rejects_non_pdf_bytes() -> None:
    with pytest.raises(InvalidDocumentError, match="readable PDF"):
        extract_pdf_text(b"not a pdf")


def test_extract_pdf_rejects_scanned_or_empty_pdf() -> None:
    with pytest.raises(InvalidDocumentError, match="scanned or image-only"):
        extract_pdf_pages(_pdf_bytes())


def test_chunks_keep_section_and_page_metadata() -> None:
    chunks = chunk_pdf_pages(
        [(4, "COVERAGE LIMITS\nThe policy covers a loss subject to its terms.")]
    )

    assert len(chunks) == 1
    assert chunks[0].section == "COVERAGE LIMITS"
    assert chunks[0].page_number == 4
    assert "policy covers" in chunks[0].content


def test_long_text_chunks_with_character_overlap() -> None:
    text = "word " * 500
    chunks = chunk_pdf_pages([(1, text)])

    assert len(chunks) > 1
    assert all(len(chunk.content) <= 1_000 for chunk in chunks)
    assert chunks[0].content[-80:] in chunks[1].content

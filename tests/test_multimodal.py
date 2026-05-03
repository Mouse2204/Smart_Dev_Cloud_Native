import pytest
from unittest.mock import MagicMock, patch
from src.processing.multimodal_extractor import _table_to_markdown, extract_chunks

def test_table_to_markdown_basic():
    """Verify table conversion to markdown."""
    table = [
        ["Header1", "Header2"],
        ["Row1Col1", "Row1Col2"]
    ]
    md = _table_to_markdown(table)
    assert "| Header1 | Header2 |" in md
    assert "| --- | --- |" in md
    assert "| Row1Col1 | Row1Col2 |" in md

def test_table_to_markdown_empty():
    """Verify empty table returns empty string."""
    assert _table_to_markdown([]) == ""
    assert _table_to_markdown([["One Row Only"]]) == ""

@patch("pdfplumber.open")
def test_extract_chunks_mocked(mock_pdfplumber):
    """Verify chunk extraction logic by mocking pdfplumber."""
    # Setup mock PDF structure
    mock_pdf = MagicMock()
    mock_page = MagicMock()
    mock_page.extract_text.return_value = "This is a test page."
    mock_page.extract_tables.return_value = []
    mock_page.images = []
    mock_pdf.pages = [mock_page]
    mock_pdfplumber.return_value.__enter__.return_value = mock_pdf
    
    # Run extractor with dummy bytes
    chunks = extract_chunks(
        pdf_source=b"dummy content",
        object_name="test.pdf",
        chunk_size=100,
        chunk_overlap=0
    )
    
    assert len(chunks) == 1
    assert chunks[0].text == "This is a test page."
    assert chunks[0].source_file == "test.pdf"
    assert chunks[0].page_number == 1

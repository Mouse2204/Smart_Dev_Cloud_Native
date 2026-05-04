"""
Returns the same list[ChunkPayload] interface as the legacy extractor,
so it is a drop-in replacement inside embedding_worker.py
"""
from __future__ import annotations

import io
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pdfplumber
from langchain_text_splitters import RecursiveCharacterTextSplitter
from PIL import Image

from src.storage.schemas import ChunkPayload
from src.utils.logger import get_logger

logger = get_logger("multimodal_extractor")

if TYPE_CHECKING:
    from ollama import Client as OllamaClient

TABLE_MIN_ROWS = 2
IMAGE_MIN_PIXELS = 5_000
MAX_IMAGE_SIDE = 1024
LLAVA_MODEL = "llava"

def _table_to_markdown(table: list[list[str | None]]) -> str:
    """Convert a pdfplumber table to a Markdown table string"""
    if not table or len(table) < TABLE_MIN_ROWS:
        return ""

    rows = [[str(cell or "").strip() for cell in row] for row in table]
    header = "| " + " | ".join(rows[0]) + " |"
    separator = "| " + " | ".join(["---"] * len(rows[0])) + " |"
    body = "\n".join("| " + " | ".join(row) + " |" for row in rows[1:])
    return "\n".join([header, separator, body])


def _resize_image(img: Image.Image) -> Image.Image:
    """Downscale image so its longest side is MAX_IMAGE_SIDE px"""
    w, h = img.size
    longest = max(w, h)
    if longest <= MAX_IMAGE_SIDE:
        return img
    scale = MAX_IMAGE_SIDE / longest
    return img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)


def _image_to_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def _describe_image_with_llava(
    ollama_client: "OllamaClient | None",
    img: Image.Image,
    page_number: int,
) -> str:
    """Ask LLaVa to describe an image. Returns empty string if unavailable"""
    if ollama_client is None:
        return ""
    try:
        import base64
        img_bytes = _image_to_bytes(_resize_image(img))
        img_b64 = base64.b64encode(img_bytes).decode()
        response = ollama_client.generate(
            model=LLAVA_MODEL,
            prompt=(
                "Describe this diagram or figure from a technical document. "
                "Focus on what data, architecture, or concept it illustrates. "
                "Be concise (2-4 sentences)."
            ),
            images=[img_b64],
            options={"num_predict": 128, "temperature": 0.2},
        )
        description = response.get("response", "").strip()
        if description:
            return f"[Figure on page {page_number}]: {description}"
    except Exception as exc:
        logger.error(f"LLaVa image description failed: {exc}")
    return ""

def extract_chunks(
    pdf_source: Path | bytes,
    object_name: str,
    chunk_size: int = 900,
    chunk_overlap: int = 150,
    ollama_client: "OllamaClient | None" = None,
) -> list[ChunkPayload]:
    """
    Args:
        pdf_source:    Path to a local PDF file, or raw PDF bytes
        object_name:   Logical identifier (e.g. MinIO object key or filename)
        chunk_size:    Character size for text splitting
        chunk_overlap: Overlap between consecutive chunks
        ollama_client: Optional Ollama client for LLaVa image descriptions
                       If None, images are skipped

    Returns:
        list of ChunkPayload
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    chunks: list[ChunkPayload] = []

    if isinstance(pdf_source, Path):
        pdf_bytes = pdf_source.read_bytes()
    else:
        pdf_bytes = pdf_source

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            page_parts: list[str] = []

            # 1. Plain text
            text = (page.extract_text(x_tolerance=3, y_tolerance=3) or "").strip()
            if text:
                page_parts.append(text)

            # 2. Tables -> Markdown
            for table in page.extract_tables():
                md = _table_to_markdown(table)
                if md:
                    page_parts.append(f"\n[Table on page {page_number}]:\n{md}")

            # 3. Images -> LLaVa description
            if ollama_client is not None:
                for img_obj in page.images:
                    try:
                        # pdfplumber stores image bytes in obj["stream"]
                        raw = img_obj.get("stream")
                        if raw is None:
                            continue
                        img_data = raw.get_data() if hasattr(raw, "get_data") else raw
                        pil_img = Image.open(io.BytesIO(img_data))
                        w, h = pil_img.size
                        if w * h < IMAGE_MIN_PIXELS:
                            continue  # skip tiny icons
                        desc = _describe_image_with_llava(ollama_client, pil_img, page_number)
                        if desc:
                            page_parts.append(desc)
                    except Exception as exc:
                        logger.error(f"Image processing skipped: {exc}")

            combined = "\n\n".join(page_parts).strip()
            if not combined:
                continue

            # Split the combined page content into model-friendly chunks
            for chunk_index, chunk_text in enumerate(splitter.split_text(combined)):
                trimmed = chunk_text.strip()
                if trimmed:
                    chunks.append(
                        ChunkPayload(
                            source_object=object_name,
                            source_file=Path(object_name).name,
                            page_number=page_number,
                            chunk_index=chunk_index,
                            text=trimmed,
                        )
                    )

    return chunks

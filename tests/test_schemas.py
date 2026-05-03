import os
import pytest
from src.storage.schemas import AppConfig, BlogEntry, ChunkPayload

def test_app_config_defaults():
    """Verify AppConfig loads default values if ENV is empty."""
    # Clear relevant env vars
    for key in ["QDRANT_URL", "KAFKA_BOOTSTRAP", "USE_GROQ"]:
        if key in os.environ:
            del os.environ[key]
            
    config = AppConfig.from_env()
    assert config.qdrant_url == "http://localhost:6333"
    assert config.use_groq is True

def test_app_config_overrides(monkeypatch):
    """Verify AppConfig correctly picks up env var overrides."""
    monkeypatch.setenv("QDRANT_URL", "http://localhost:9999")
    monkeypatch.setenv("USE_GROQ", "true")
    monkeypatch.setenv("RAG_TOP_K", "10")
    
    config = AppConfig.from_env()
    assert config.qdrant_url == "http://localhost:9999"
    assert config.use_groq is True
    assert config.top_k == 10

def test_blog_entry_serialization():
    """Verify BlogEntry to_qdrant_payload conversion."""
    entry = BlogEntry(
        blog_id="123",
        title="Test Blog",
        url="http://test.com",
        author="Author",
        summary="A short summary",
        published_at="2024-01-01",
        source_feed="dev.to"
    )
    payload = entry.to_qdrant_payload()
    assert payload["blog_id"] == "123"
    assert payload["title"] == "Test Blog"
    assert "url" in payload

def test_chunk_payload_serialization():
    """Verify ChunkPayload to_qdrant_payload conversion."""
    chunk = ChunkPayload(
        source_object="docs/file.pdf",
        source_file="file.pdf",
        page_number=5,
        chunk_index=2,
        text="Sample chunk content"
    )
    payload = chunk.to_qdrant_payload()
    assert payload["page_number"] == 5
    assert payload["text"] == "Sample chunk content"
    assert payload["source_file"] == "file.pdf"

import pytest
from unittest.mock import MagicMock, patch
from src.app.rag import RagEngine, RetrievedChunk
from src.storage.schemas import AppConfig

@pytest.fixture
def mock_config():
    config = AppConfig.from_env()
    config.qdrant_collection = "test_collection"
    config.use_groq = False
    return config

@patch("src.app.rag.QdrantClient")
@patch("src.app.rag.OllamaClient")
def test_rag_retrieval(mock_ollama_class, mock_qdrant_class, mock_config):
    """Verify RAG retrieval logic and chunk transformation."""
    # Setup mocks
    mock_qdrant = mock_qdrant_class.return_value
    mock_ollama = mock_ollama_class.return_value
    
    # Mock embedding
    mock_ollama.embeddings.return_value = {"embedding": [0.1, 0.2, 0.3]}
    
    # Mock Qdrant search result
    mock_point = MagicMock()
    mock_point.payload = {
        "text": "Found context",
        "source_file": "doc1.pdf",
        "page_number": 1
    }
    mock_point.score = 0.95
    
    # Mock query_points (modern API)
    mock_q_res = MagicMock()
    mock_q_res.points = [mock_point]
    mock_qdrant.query_points.return_value = mock_q_res
    
    engine = RagEngine(mock_config)
    results = engine.retrieve("What is the test?")
    
    assert len(results) == 1
    assert results[0].text == "Found context"
    assert results[0].score == 0.95
    assert results[0].source_file == "doc1.pdf"

def test_prompt_building(mock_config):
    """Verify prompt construction with multiple contexts."""
    engine = RagEngine(mock_config)
    contexts = [
        RetrievedChunk(text="Context 1", score=0.9, source_file="a.pdf", page_number=1),
        RetrievedChunk(text="Context 2", score=0.8, source_file="b.pdf", page_number=2),
    ]
    prompt = engine._build_prompt("Question?", contexts)
    
    assert "Context 1" in prompt
    assert "Context 2" in prompt
    assert "a.pdf" in prompt
    assert "Question?" in prompt

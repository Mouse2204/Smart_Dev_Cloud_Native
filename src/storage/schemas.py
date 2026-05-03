from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def _project_root() -> Path:
	return Path(__file__).resolve().parents[2]


def _as_bool(value: str, default: bool = False) -> bool:
	if value is None:
		return default
	return value.strip().lower() in {"1", "true", "yes", "y", "on"}


@dataclass(slots=True)
class AppConfig:
	source_books_dir: Path

	minio_endpoint: str
	minio_access_key: str
	minio_secret_key: str
	minio_secure: bool
	minio_bucket: str
	minio_prefix: str

	qdrant_url: str
	qdrant_api_key: str | None
	qdrant_collection: str
	qdrant_blog_collection: str

	ollama_base_url: str
	embedding_model: str
	llm_model: str

	groq_api_key: str
	use_groq: bool

	chunk_size: int
	chunk_overlap: int
	embedding_batch_size: int
	top_k: int

	@classmethod
	def from_env(cls) -> "AppConfig":
		root = _project_root()
		env_file = root / ".env"
		if env_file.exists():
			# Basic .env parser for robustness–prevents shell escaping/sourcing issues.
			for line in env_file.read_text(encoding="utf-8").splitlines():
				line = line.strip()
				if not line or line.startswith("#") or "=" not in line:
					continue
				key, val = line.split("=", 1)
				key = key.strip()
				val = val.strip().strip('"').strip("'")
				if key and key not in os.environ:
					os.environ[key] = val

		return cls(
			source_books_dir=Path(
				os.getenv("SOURCE_BOOKS_DIR", str(root / "data" / "books"))
			).expanduser(),
			minio_endpoint=os.getenv("MINIO_ENDPOINT", "localhost:9000"),
			minio_access_key=os.getenv("MINIO_ACCESS_KEY", "minioadmin"),
			minio_secret_key=os.getenv("MINIO_SECRET_KEY", "minioadmin123"),
			minio_secure=_as_bool(os.getenv("MINIO_SECURE", "false")),
			minio_bucket=os.getenv("MINIO_BUCKET", "books-raw"),
			minio_prefix=os.getenv("MINIO_PREFIX", "books"),
			qdrant_url=os.getenv("QDRANT_URL", "http://localhost:6333"),
			qdrant_api_key=os.getenv("QDRANT_API_KEY"),
			qdrant_collection=os.getenv("QDRANT_COLLECTION", "dev_docs_books"),
			qdrant_blog_collection=os.getenv("QDRANT_BLOG_COLLECTION", "dev_docs_blogs"),
			ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
			embedding_model=os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text"),
		llm_model=os.getenv("LLM_MODEL", "llama-3.3-70b-versatile"),
			groq_api_key=os.getenv("GROQ_API_KEY", ""),
			use_groq=_as_bool(os.getenv("USE_GROQ", "true")),
			chunk_size=int(os.getenv("CHUNK_SIZE", "900")),
			chunk_overlap=int(os.getenv("CHUNK_OVERLAP", "150")),
			embedding_batch_size=int(os.getenv("EMBEDDING_BATCH_SIZE", "16")),
			top_k=int(os.getenv("RAG_TOP_K", "4")),
		)


@dataclass(slots=True)
class ChunkPayload:
	source_object: str
	source_file: str
	page_number: int
	chunk_index: int
	text: str

	def to_qdrant_payload(self) -> dict[str, Any]:
		return {
			"source_object": self.source_object,
			"source_file": self.source_file,
			"page_number": self.page_number,
			"chunk_index": self.chunk_index,
			"text": self.text,
		}


@dataclass(slots=True)
class BlogEntry:
	"""Represents a single blog post stored in Qdrant (dev_docs_blogs collection)."""
	blog_id: str           # sha256 of URL – used as stable Qdrant point ID seed
	title: str
	url: str
	author: str
	summary: str           # LLM-generated 5-6 line summary
	published_at: str      # ISO-8601 string, e.g. "2026-04-27T08:00:00Z"
	source_feed: str       # RSS feed label, e.g. "dev.to"

	def to_qdrant_payload(self) -> dict[str, Any]:
		return {
			"blog_id": self.blog_id,
			"title": self.title,
			"url": self.url,
			"author": self.author,
			"summary": self.summary,
			"published_at": self.published_at,
			"source_feed": self.source_feed,
		}


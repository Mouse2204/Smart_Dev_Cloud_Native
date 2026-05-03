"""blog_crawler.py – RSS Feed Crawler + LLM Blog Summarizer

Flow:
  1. Parse RSS feeds from a curated list of tech blogs.
  2. For each new entry (not already in Qdrant), fetch the article text.
  3. Call Groq / Ollama to produce a 5‑6 line summary.
  4. Upsert the summary + metadata into:
       • Qdrant  collection: dev_docs_blogs  (for the Streamlit news feed)
       • Kafka   topic:      blog-events     (for Spark → Iceberg long-term storage)

Run:
  python -m src.processing.blog_crawler
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5

import feedparser
import requests
from groq import Groq
from ollama import Client as OllamaClient
from qdrant_client import QdrantClient
from qdrant_client.http import models as qm

from src.storage.schemas import AppConfig, BlogEntry
from src.utils.logger import get_logger

logger = get_logger("blog_crawler")

# ---------------------------------------------------------------------------
# Feed configuration - loaded from data/realtime_source/source.json
# ---------------------------------------------------------------------------
def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]

def _load_feeds(root: Path) -> list[dict[str, Any]]:
    source_path = root / "data" / "realtime_source" / "source.json"
    if not source_path.exists():
        logger.warning(f"Source file not found at {source_path}, using default empty list.")
        return []
    try:
        return json.loads(source_path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.error(f"Failed to load sources: {exc}")
        return []

MAX_ARTICLES_PER_FEED = 10        # latest N articles per crawl run
REQUEST_TIMEOUT_S = 15            # HTTP request timeout
MAX_CONTENT_CHARS = 4_000         # characters fed to LLM (keep tokens low)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _stable_id(url: str) -> str:
    """Deterministic UUID from article URL."""
    return str(uuid5(NAMESPACE_URL, url))


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _parse_published(entry) -> str:
    """Return an ISO‑8601 UTC timestamp; fall back to *now* if missing."""
    for attr in ("published", "updated"):
        raw = getattr(entry, attr, None)
        if raw:
            try:
                return parsedate_to_datetime(raw).astimezone(timezone.utc).isoformat()
            except Exception:
                pass
    return datetime.now(timezone.utc).isoformat()


def _fetch_article_text(url: str) -> str:
    """Fetch raw text from article URL; returns empty string on failure."""
    try:
        resp = requests.get(url, timeout=REQUEST_TIMEOUT_S, headers={"User-Agent": "SmartDevBot/1.0"})
        resp.raise_for_status()
        # Very lightweight text extraction – strip HTML tags
        import re
        text = re.sub(r"<[^>]+>", " ", resp.text)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:MAX_CONTENT_CHARS]
    except Exception as exc:
        logger.error(f"Failed to fetch {url}: {exc}")
        return ""


def _summarize_groq(client: Groq, model: str, title: str, content: str) -> str:
    """Summarize article using the Groq API."""
    prompt = (
        f"Summarize the following tech article in 5-6 concise bullet points.\n"
        f"Focus on key takeaways, technologies used, and why it matters to developers.\n"
        f"Title: {title}\n\nContent:\n{content}"
    )
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=256,
            temperature=0.3,
        )
        return resp.choices[0].message.content.strip()
    except Exception as exc:
        logger.warning(f"Groq summarization failed: {exc}")
        return content[:500]  # fallback: first 500 chars


def _summarize_ollama(client: OllamaClient, model: str, title: str, content: str) -> str:
    """Summarize article using local Ollama."""
    prompt = (
        f"Summarize the following tech article in 5-6 concise bullet points.\n"
        f"Focus on key takeaways, technologies used, and why it matters to developers.\n"
        f"Title: {title}\n\nContent:\n{content}"
    )
    try:
        resp = client.generate(model=model, prompt=prompt, options={"num_predict": 256, "temperature": 0.3})
        return resp["response"].strip()
    except Exception as exc:
        logger.warning(f"Ollama summarization failed: {exc}")
        return content[:500]


def _ensure_blog_collection(client: QdrantClient, collection: str, vector_size: int) -> None:
    if not client.collection_exists(collection):
        client.create_collection(
            collection_name=collection,
            vectors_config=qm.VectorParams(size=vector_size, distance=qm.Distance.COSINE),
        )
        # Create payload index so we can sort by published_at quickly
        client.create_payload_index(
            collection_name=collection,
            field_name="published_at",
            field_schema=qm.PayloadSchemaType.KEYWORD,
        )
        logger.info(f"Created Qdrant collection '{collection}'.")


def _already_indexed(qdrant: QdrantClient, collection: str, blog_id: str) -> bool:
    """Check whether this article URL is already stored."""
    if not qdrant.collection_exists(collection):
        return False
    results, _ = qdrant.scroll(
        collection_name=collection,
        scroll_filter=qm.Filter(
            must=[qm.FieldCondition(key="blog_id", match=qm.MatchValue(value=blog_id))]
        ),
        limit=1,
    )
    return bool(results)


def _push_to_kafka(entry: BlogEntry, config: AppConfig) -> None:
    """Push blog event to Kafka topic 'blog-events' (best‑effort; skip if unavailable)."""
    try:
        from kafka import KafkaProducer  # type: ignore
        producer = KafkaProducer(
            bootstrap_servers=getattr(config, "kafka_bootstrap", "localhost:9092"),
            value_serializer=lambda v: json.dumps(v).encode(),
        )
        producer.send("blog-events", value=entry.to_qdrant_payload())
        producer.flush()
        producer.close()
        logger.info(f"Pushed to Kafka: {entry.title[:60]}")
    except Exception as exc:
        logger.error(f"Kafka push skipped ({exc})")


# ---------------------------------------------------------------------------
# Main crawl logic
# ---------------------------------------------------------------------------

def crawl(config: AppConfig) -> int:
    """Crawl all RSS feeds, summarize new articles, upsert into Qdrant.
    Returns the number of new articles indexed.
    """
    qdrant = QdrantClient(url=config.qdrant_url, api_key=config.qdrant_api_key)
    ollama = OllamaClient(host=config.ollama_base_url)
    groq_client: Groq | None = None
    if config.use_groq and config.groq_api_key:
        groq_client = Groq(api_key=config.groq_api_key)

    # Embed a test sentence to discover embedding dimension
    probe_vec: list[float] = ollama.embeddings(
        model=config.embedding_model, prompt="test"
    )["embedding"]
    vector_size = len(probe_vec)
    _ensure_blog_collection(qdrant, config.qdrant_blog_collection, vector_size)

    new_articles = 0
    feeds = _load_feeds(_project_root())

    for feed_cfg in feeds:
        label = feed_cfg.get("source_name", "Unknown")
        url = feed_cfg.get("end_point", "")
        headers = feed_cfg.get("headers", {"User-Agent": "SmartDevBot/1.0"})
        
        if not url:
            continue

        logger.info(f"Fetching feed: {label} ({url}) …")
        try:
            # Using requests to handle headers (crucial for Reddit/GitHub)
            resp = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT_S)
            resp.raise_for_status()
            parsed = feedparser.parse(resp.content)
        except Exception as exc:
            logger.error(f"Failed to fetch {label}: {exc}")
            continue

        entries = parsed.entries[:MAX_ARTICLES_PER_FEED]

        for entry in entries:
            url: str = getattr(entry, "link", "")
            title: str = getattr(entry, "title", "Untitled")
            author: str = getattr(entry, "author", "Unknown")
            if not url:
                continue

            blog_id = _sha256(url)
            if _already_indexed(qdrant, config.qdrant_blog_collection, blog_id):
                logger.info(f"Already indexed, skipping: {title[:60]}")
                continue

            logger.info(f"Processing: {title[:60]}")
            content = _fetch_article_text(url)
            
            # Summarize
            if groq_client:
                summary = _summarize_groq(groq_client, config.llm_model, title, content)
            else:
                summary = _summarize_ollama(ollama, config.llm_model, title, content)

            published_at = _parse_published(entry)

            blog_entry = BlogEntry(
                blog_id=blog_id,
                title=title,
                url=url,
                author=author,
                summary=summary,
                published_at=published_at,
                source_feed=label,
            )

            # Embed the summary for semantic search
            embed_text = f"{title}\n{summary}"
            vector = ollama.embeddings(model=config.embedding_model, prompt=embed_text)["embedding"]

            point_id = str(uuid5(NAMESPACE_URL, url))
            qdrant.upsert(
                collection_name=config.qdrant_blog_collection,
                points=[
                    qm.PointStruct(
                        id=point_id,
                        vector=vector,
                        payload=blog_entry.to_qdrant_payload(),
                    )
                ],
            )

            _push_to_kafka(blog_entry, config)

            new_articles += 1
            time.sleep(1)  # polite delay between articles

    logger.info(f"Done. {new_articles} new article(s) indexed.")
    return new_articles


def main() -> None:
    config = AppConfig.from_env()
    crawl(config)


if __name__ == "__main__":
    main()

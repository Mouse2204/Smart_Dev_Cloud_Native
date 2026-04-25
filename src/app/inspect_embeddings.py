from __future__ import annotations

import argparse
from typing import Any

from qdrant_client import QdrantClient

from src.storage.schemas import AppConfig


def _format_vector(vector: Any, max_items: int = 8) -> str:
	if vector is None:
		return "<no vector>"
	if isinstance(vector, list) and vector and isinstance(vector[0], (int, float)):
		preview = ", ".join(f"{float(value):.4f}" for value in vector[:max_items])
		return f"[{preview}{', ...' if len(vector) > max_items else ''}] (dim={len(vector)})"
	return str(vector)


def main() -> None:
	parser = argparse.ArgumentParser(description="Inspect Qdrant embeddings for indexed PDFs.")
	parser.add_argument("--limit", type=int, default=5, help="How many chunks to show.")
	args = parser.parse_args()

	config = AppConfig.from_env()
	client = QdrantClient(url=config.qdrant_url, api_key=config.qdrant_api_key)

	if not client.collection_exists(config.qdrant_collection):
		print(f"Collection {config.qdrant_collection!r} does not exist yet.")
		return

	info = client.get_collection(config.qdrant_collection)
	points_count = getattr(info, "points_count", None)
	indexed_vectors = getattr(getattr(info, "config", None), "params", None)
	vector_params = getattr(indexed_vectors, "vectors", None)
	dim = getattr(vector_params, "size", None)

	print(f"Collection: {config.qdrant_collection}")
	print(f"Points: {points_count}")
	print(f"Vector dimension: {dim}")
	print()

	points, _ = client.scroll(
		collection_name=config.qdrant_collection,
		limit=args.limit,
		with_payload=True,
		with_vectors=True,
	)

	for idx, point in enumerate(points, start=1):
		payload: dict[str, Any] = point.payload or {}
		print(f"[{idx}] id={point.id}")
		print(f"    file={payload.get('source_file', 'unknown')}")
		print(f"    page={payload.get('page_number', '?')} chunk={payload.get('chunk_index', '?')}")
		print(f"    object={payload.get('source_object', 'unknown')}")
		print(f"    text={str(payload.get('text', '')).strip()[:220]}")
		print(f"    vector={_format_vector(getattr(point, 'vector', None))}")
		print()


if __name__ == "__main__":
	main()

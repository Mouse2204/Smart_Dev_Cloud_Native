from __future__ import annotations

import argparse
import hashlib
import io
import sys
from pathlib import Path
from typing import Iterable, TypeVar
from uuid import uuid5, NAMESPACE_URL

from langchain_text_splitters import RecursiveCharacterTextSplitter
from minio.error import S3Error
from ollama import Client as OllamaClient
from pypdf import PdfReader
from qdrant_client import QdrantClient
from qdrant_client.http import models as qm

from src.ingestion.producer import build_minio_client, upload_pdf_folder_to_minio
from src.storage.schemas import AppConfig, ChunkPayload
from src.processing.multimodal_extractor import extract_chunks as multimodal_extract_chunks
from src.utils.logger import get_logger

logger = get_logger("embedding_worker")


T = TypeVar("T")


def _iter_batches(items: list[T], size: int) -> Iterable[list[T]]:
	for idx in range(0, len(items), size):
		yield items[idx : idx + size]


def _list_pdf_objects(minio_client, config: AppConfig) -> list[str]:
	objects = minio_client.list_objects(
		bucket_name=config.minio_bucket,
		prefix=config.minio_prefix.strip("/"),
		recursive=True,
	)
	return sorted([obj.object_name for obj in objects if obj.object_name.lower().endswith(".pdf")])


def _object_etag(minio_client, config: AppConfig, object_name: str) -> str:
	stat = minio_client.stat_object(config.minio_bucket, object_name)
	return (stat.etag or "").strip('"')


def _read_pdf_from_minio(minio_client, config: AppConfig, object_name: str) -> PdfReader:
	response = minio_client.get_object(config.minio_bucket, object_name)
	try:
		data = response.read()
	finally:
		response.close()
		response.release_conn()
	return PdfReader(io.BytesIO(data))


def _pdf_chunks(
	minio_client,
	config: AppConfig,
	object_name: str,
	ollama_client: OllamaClient | None = None,
	multimodal: bool = True,
) -> list[ChunkPayload]:
	if multimodal:
		response = minio_client.get_object(config.minio_bucket, object_name)
		try:
			pdf_bytes = response.read()
		finally:
			response.close()
			response.release_conn()
		return multimodal_extract_chunks(
			pdf_source=pdf_bytes,
			object_name=object_name,
			chunk_size=config.chunk_size,
			chunk_overlap=config.chunk_overlap,
			ollama_client=ollama_client,
		)
	reader = _read_pdf_from_minio(minio_client, config, object_name)
	return _pdf_chunks_from_reader(reader, object_name, config)


def _pdf_chunks_from_path(
	pdf_path: Path,
	object_name: str,
	config: AppConfig,
	ollama_client: OllamaClient | None = None,
	multimodal: bool = True,
) -> list[ChunkPayload]:
	if multimodal:
		return multimodal_extract_chunks(
			pdf_source=pdf_path,
			object_name=object_name,
			chunk_size=config.chunk_size,
			chunk_overlap=config.chunk_overlap,
			ollama_client=ollama_client,
		)
	with pdf_path.open("rb") as handle:
		reader = PdfReader(handle)
		return _pdf_chunks_from_reader(reader, object_name, config)


def _pdf_chunks_from_reader(reader: PdfReader, object_name: str, config: AppConfig) -> list[ChunkPayload]:
	splitter = RecursiveCharacterTextSplitter(
		chunk_size=config.chunk_size,
		chunk_overlap=config.chunk_overlap,
	)
	chunks: list[ChunkPayload] = []

	for page_number, page in enumerate(reader.pages, start=1):
		text = (page.extract_text() or "").strip()
		if not text:
			continue
		page_chunks = splitter.split_text(text)
		for chunk_index, chunk_text in enumerate(page_chunks):
			trimmed = chunk_text.strip()
			if not trimmed:
				continue
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


def _local_pdf_files(source_dir: Path) -> list[Path]:
	if not source_dir.exists():
		raise FileNotFoundError(f"Source directory does not exist: {source_dir}")
	return sorted([p for p in source_dir.rglob("*.pdf") if p.is_file()])


def _file_sha256(file_path: Path) -> str:
	hash_obj = hashlib.sha256()
	with file_path.open("rb") as handle:
		for chunk in iter(lambda: handle.read(1024 * 1024), b""):
			hash_obj.update(chunk)
	return hash_obj.hexdigest()


def _ensure_collection(client: QdrantClient, config: AppConfig, vector_size: int) -> None:
	existing = client.collection_exists(collection_name=config.qdrant_collection)
	if not existing:
		client.create_collection(
			collection_name=config.qdrant_collection,
			vectors_config=qm.VectorParams(size=vector_size, distance=qm.Distance.COSINE),
		)
		return

	info = client.get_collection(config.qdrant_collection)
	current_size = info.config.params.vectors.size
	if current_size != vector_size:
		raise ValueError(
			"Existing Qdrant collection vector size does not match embedding model. "
			f"collection={config.qdrant_collection}, expected={vector_size}, actual={current_size}."
		)


def _qdrant_client(config: AppConfig) -> QdrantClient:
	return QdrantClient(url=config.qdrant_url, api_key=config.qdrant_api_key)


def _embed_texts(ollama_client: OllamaClient, model: str, texts: list[str]) -> list[list[float]]:
	vectors: list[list[float]] = []
	for text in texts:
		response = ollama_client.embeddings(model=model, prompt=text)
		vectors.append(response["embedding"])
	return vectors


def _object_filter(object_name: str) -> qm.Filter:
	return qm.Filter(
		must=[
			qm.FieldCondition(
				key="source_object",
				match=qm.MatchValue(value=object_name),
			)
		]
	)


def _needs_reindex(
	qdrant_client: QdrantClient,
	config: AppConfig,
	object_name: str,
	object_etag: str,
) -> tuple[bool, str]:
	points, _ = qdrant_client.scroll(
		collection_name=config.qdrant_collection,
		scroll_filter=_object_filter(object_name),
		limit=1,
		with_payload=True,
	)
	if not points:
		return True, "new"

	payload = points[0].payload or {}
	indexed_etag = str(payload.get("object_etag", ""))
	indexed_model = str(payload.get("embedding_model", ""))
	indexed_chunk_size = int(payload.get("chunk_size", -1) or -1)
	indexed_chunk_overlap = int(payload.get("chunk_overlap", -1) or -1)

	is_same = (
		indexed_etag == object_etag
		and indexed_model == config.embedding_model
		and indexed_chunk_size == config.chunk_size
		and indexed_chunk_overlap == config.chunk_overlap
	)
	if is_same:
		return False, "unchanged"
	return True, "changed"


def _delete_existing_object_points(
	qdrant_client: QdrantClient,
	config: AppConfig,
	object_name: str,
) -> None:
	qdrant_client.delete(
		collection_name=config.qdrant_collection,
		points_selector=qm.FilterSelector(filter=_object_filter(object_name)),
	)


def _index_document_chunks(
	qdrant_client: QdrantClient,
	config: AppConfig,
	ollama_client: OllamaClient,
	object_name: str,
	object_etag: str,
	chunks: list[ChunkPayload],
) -> int:
	points_inserted = 0
	first_vector_size: int | None = None

	for batch in _iter_batches(chunks, config.embedding_batch_size):
		texts = [item.text for item in batch]
		vectors = _embed_texts(ollama_client, config.embedding_model, texts)

		if first_vector_size is None and vectors:
			first_vector_size = len(vectors[0])
			_ensure_collection(qdrant_client, config, first_vector_size)

		points = []
		for payload, vector in zip(batch, vectors, strict=True):
			point_id = str(
				uuid5(
					NAMESPACE_URL,
					f"{payload.source_object}:{payload.page_number}:{payload.chunk_index}",
				)
			)
			qdrant_payload = payload.to_qdrant_payload()
			qdrant_payload.update(
				{
					"object_etag": object_etag,
					"embedding_model": config.embedding_model,
					"chunk_size": config.chunk_size,
					"chunk_overlap": config.chunk_overlap,
				}
			)
			points.append(
				qm.PointStruct(
					id=point_id,
					vector=vector,
					payload=qdrant_payload,
				)
			)

		qdrant_client.upsert(collection_name=config.qdrant_collection, points=points)
		points_inserted += len(points)

	return points_inserted


def embed_from_minio(config: AppConfig) -> dict[str, int]:
	minio_client = build_minio_client(config)
	object_names = _list_pdf_objects(minio_client, config)
	if not object_names:
		return {
			"objects": 0,
			"chunks": 0,
			"points": 0,
			"skipped": 0,
			"reindexed": 0,
		}

	ollama_client = OllamaClient(host=config.ollama_base_url)
	qdrant_client = _qdrant_client(config)
	total_reindexed = 0

	total_chunks = 0
	total_points = 0
	total_skipped = 0

	for object_name in object_names:
		object_etag = _object_etag(minio_client, config, object_name)
		must_reindex = True
		reason = "new"

		if qdrant_client.collection_exists(config.qdrant_collection):
			must_reindex, reason = _needs_reindex(
				qdrant_client=qdrant_client,
				config=config,
				object_name=object_name,
				object_etag=object_etag,
			)

		if not must_reindex:
			total_skipped += 1
			continue

		if reason == "changed":
			_delete_existing_object_points(qdrant_client, config, object_name)
			total_reindexed += 1

		chunks = _pdf_chunks(minio_client, config, object_name)
		if not chunks:
			continue
		total_points += _index_document_chunks(
			qdrant_client=qdrant_client,
			config=config,
			ollama_client=ollama_client,
			object_name=object_name,
			object_etag=object_etag,
			chunks=chunks,
		)

		total_chunks += len(chunks)

	return {
		"objects": len(object_names),
		"chunks": total_chunks,
		"points": total_points,
		"skipped": total_skipped,
		"reindexed": total_reindexed,
	}


def embed_from_local(config: AppConfig, source_dir: Path | None = None) -> dict[str, int]:
	source_root = source_dir or config.source_books_dir
	pdf_paths = _local_pdf_files(source_root)
	if not pdf_paths:
		return {
			"objects": 0,
			"chunks": 0,
			"points": 0,
			"skipped": 0,
			"reindexed": 0,
		}

	ollama_client = OllamaClient(host=config.ollama_base_url)
	qdrant_client = _qdrant_client(config)
	if not qdrant_client.collection_exists(config.qdrant_collection):
		# Collection is created lazily during first upsert once vector dimensions are known.
		pass

	total_chunks = 0
	total_points = 0

	for pdf_path in pdf_paths:
		object_name = pdf_path.relative_to(source_root).as_posix()
		object_etag = _file_sha256(pdf_path)
		chunks = _pdf_chunks_from_path(pdf_path, object_name, config)
		if not chunks:
			continue
		total_points += _index_document_chunks(
			qdrant_client=qdrant_client,
			config=config,
			ollama_client=ollama_client,
			object_name=object_name,
			object_etag=object_etag,
			chunks=chunks,
		)
		total_chunks += len(chunks)

	return {
		"objects": len(pdf_paths),
		"chunks": total_chunks,
		"points": total_points,
		"skipped": 0,
		"reindexed": 0,
	}


def run_pipeline(
	config: AppConfig,
	source_dir: Path | None,
	skip_upload: bool,
	multimodal: bool = True,
) -> dict[str, int]:
	if skip_upload:
		return embed_from_minio(config)

	try:
		upload_pdf_folder_to_minio(config=config, source_dir=source_dir)
		return embed_from_minio(config)
	except Exception as exc:
		logger.warning(
			f"MinIO upload/indexing unavailable ({exc}). Falling back to local PDF indexing."
		)
		return embed_from_local(config, source_dir=source_dir)


def main() -> None:
	parser = argparse.ArgumentParser(
		description="Upload PDFs to MinIO, batch-embed with Ollama, and index vectors to Qdrant."
	)
	parser.add_argument(
		"--source-dir",
		type=Path,
		default=None,
		help="Folder with PDFs to upload before embedding (default: SOURCE_BOOKS_DIR).",
	)
	parser.add_argument(
		"--skip-upload",
		action="store_true",
		help="Skip upload and process already-uploaded PDFs in MinIO.",
	)
	parser.add_argument(
		"--multimodal",
		action=argparse.BooleanOptionalAction,
		default=True,
		help="Use multimodal extractor (tables + LLaVa images). Use --no-multimodal to fall back to plain text.",
	)
	args = parser.parse_args()

	config = AppConfig.from_env()
	try:
		summary = run_pipeline(
			config=config,
			source_dir=args.source_dir,
			skip_upload=args.skip_upload,
			multimodal=args.multimodal,
		)
	except (S3Error, ValueError) as exc:
		raise SystemExit(f"Embedding pipeline failed: {exc}") from exc

	logger.info("Embedding pipeline summary:")
	logger.info(f" - Objects scanned: {summary['objects']}")
	logger.info(f" - Text chunks: {summary['chunks']}")
	logger.info(f" - Vector points upserted: {summary['points']}")
	logger.info(f" - Objects skipped (unchanged): {summary['skipped']}")
	logger.info(f" - Objects reindexed (changed): {summary['reindexed']}")


if __name__ == "__main__":
	main()

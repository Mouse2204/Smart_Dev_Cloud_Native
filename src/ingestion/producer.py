from __future__ import annotations

import argparse
from pathlib import Path

from minio import Minio
from minio.error import S3Error

from src.storage.schemas import AppConfig


def build_minio_client(config: AppConfig) -> Minio:
	return Minio(
		endpoint=config.minio_endpoint,
		access_key=config.minio_access_key,
		secret_key=config.minio_secret_key,
		secure=config.minio_secure,
	)


def _pdf_files_in_dir(source_dir: Path) -> list[Path]:
	if not source_dir.exists():
		raise FileNotFoundError(f"Source directory does not exist: {source_dir}")
	return sorted([p for p in source_dir.rglob("*.pdf") if p.is_file()])


def upload_pdf_folder_to_minio(
	config: AppConfig,
	source_dir: Path | None = None,
	prefix: str | None = None,
) -> list[str]:
	client = build_minio_client(config)
	source_root = source_dir or config.source_books_dir
	object_prefix = (prefix if prefix is not None else config.minio_prefix).strip("/")

	if not client.bucket_exists(config.minio_bucket):
		client.make_bucket(config.minio_bucket)

	uploaded_objects: list[str] = []
	for pdf_path in _pdf_files_in_dir(source_root):
		rel_path = pdf_path.relative_to(source_root).as_posix()
		object_name = f"{object_prefix}/{rel_path}" if object_prefix else rel_path
		client.fput_object(
			bucket_name=config.minio_bucket,
			object_name=object_name,
			file_path=str(pdf_path),
			content_type="application/pdf",
		)
		uploaded_objects.append(object_name)

	return uploaded_objects


def main() -> None:
	parser = argparse.ArgumentParser(
		description="Upload local PDF files to MinIO for downstream embedding."
	)
	parser.add_argument(
		"--source-dir",
		type=Path,
		default=None,
		help="Folder containing PDF files (default: SOURCE_BOOKS_DIR env or data/books).",
	)
	parser.add_argument(
		"--prefix",
		type=str,
		default=None,
		help="MinIO object key prefix (default: MINIO_PREFIX env).",
	)
	args = parser.parse_args()

	config = AppConfig.from_env()
	try:
		uploaded = upload_pdf_folder_to_minio(config, args.source_dir, args.prefix)
	except (FileNotFoundError, S3Error) as exc:
		raise SystemExit(f"Upload failed: {exc}") from exc

	if not uploaded:
		print("No PDF files found to upload.")
		return

	print(f"Uploaded {len(uploaded)} PDF file(s) to s3://{config.minio_bucket}/")
	for object_name in uploaded:
		print(f" - {object_name}")


if __name__ == "__main__":
	main()

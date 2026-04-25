from __future__ import annotations

import argparse
import os
import queue
import threading
import time
from dataclasses import dataclass
import sys
from typing import Any

from groq import Groq
from ollama import Client as OllamaClient
from qdrant_client import QdrantClient

from src.storage.schemas import AppConfig


@dataclass(slots=True)
class RetrievedChunk:
	text: str
	score: float
	source_file: str
	page_number: int


class RagEngine:
	def __init__(self, config: AppConfig) -> None:
		self.config = config
		self.qdrant = QdrantClient(url=config.qdrant_url, api_key=config.qdrant_api_key)
		self.ollama = OllamaClient(host=config.ollama_base_url)
		if config.use_groq:
			if not config.groq_api_key:
				raise ValueError("GROQ_API_KEY environment variable is required when USE_GROQ=true")
			self.groq = Groq(api_key=config.groq_api_key)
		else:
			self.groq = None

	def _embed_query(self, question: str) -> list[float]:
		started_at = time.monotonic()
		print("[rag] Embedding question for retrieval...", file=sys.stderr, flush=True)
		response = self.ollama.embeddings(model=self.config.embedding_model, prompt=question)
		elapsed = time.monotonic() - started_at
		print(f"[rag] Question embedding complete in {elapsed:.2f}s.", file=sys.stderr, flush=True)
		return response["embedding"]

	def retrieve(self, question: str, top_k: int | None = None) -> list[RetrievedChunk]:
		k = top_k or self.config.top_k
		started_at = time.monotonic()
		print(f"[rag] Retrieving top {k} chunk(s) from Qdrant...", file=sys.stderr, flush=True)
		vector = self._embed_query(question)

		try:
			print("[rag] Querying Qdrant with query_points...", file=sys.stderr, flush=True)
			query_result = self.qdrant.query_points(
				collection_name=self.config.qdrant_collection,
				query=vector,
				limit=k,
				with_payload=True,
			)
			points = query_result.points
		except AttributeError:
			print("[rag] query_points unavailable; falling back to search...", file=sys.stderr, flush=True)
			points = self.qdrant.search(
				collection_name=self.config.qdrant_collection,
				query_vector=vector,
				limit=k,
				with_payload=True,
			)

		retrieved: list[RetrievedChunk] = []
		for point in points:
			payload: dict[str, Any] = point.payload or {}
			text = str(payload.get("text", "")).strip()
			if not text:
				continue
			retrieved.append(
				RetrievedChunk(
					text=text,
					score=float(getattr(point, "score", 0.0) or 0.0),
					source_file=str(payload.get("source_file", "unknown")),
					page_number=int(payload.get("page_number", 0) or 0),
				)
			)
		elapsed = time.monotonic() - started_at
		print(f"[rag] Retrieved {len(retrieved)} chunk(s) in {elapsed:.2f}s.", file=sys.stderr, flush=True)
		return retrieved

	def _build_prompt(self, question: str, contexts: list[RetrievedChunk]) -> str:
		context_blocks = []
		for idx, item in enumerate(contexts, start=1):
			context_blocks.append(
				f"[{idx}] File: {item.source_file}, page: {item.page_number}\n{item.text}"
			)
		context_text = "\n\n".join(context_blocks) if context_blocks else "No context found."

		return (
			"You are a helpful assistant answering questions from provided document excerpts.\n"
			"Use only the provided context. If context is insufficient, say you are not sure.\n\n"
			f"Question: {question}\n\n"
			f"Context:\n{context_text}\n\n"
			"Answer in a concise paragraph, then list source references like [1], [2] when used."
		)

	def answer(self, question: str, top_k: int | None = None) -> dict[str, Any]:
		started_at = time.monotonic()
		generation_timeout_s = int(os.getenv("LLM_GENERATE_TIMEOUT_SECONDS", "60"))
		heartbeat_s = int(os.getenv("LLM_GENERATE_HEARTBEAT_SECONDS", "5"))
		print("[rag] Starting end-to-end RAG answer generation...", file=sys.stderr, flush=True)
		contexts = self.retrieve(question, top_k=top_k)
		print("[rag] Building prompt for LLM generation...", file=sys.stderr, flush=True)
		prompt = self._build_prompt(question, contexts)
		provider = "Groq" if self.config.use_groq else "Ollama"
		print(
			f"[rag] Generating answer with {provider} model '{self.config.llm_model}' (streaming, timeout={generation_timeout_s}s)...",
			file=sys.stderr,
			flush=True,
		)

		chunk_queue: queue.Queue[dict[str, Any]] = queue.Queue()
		error_queue: queue.Queue[Exception] = queue.Queue()
		done_event = threading.Event()

		def _generation_worker() -> None:
			try:
				if self.config.use_groq:
					stream = self.groq.chat.completions.create(
						model=self.config.llm_model,
						messages=[{"role": "user", "content": prompt}],
						stream=True,
						max_tokens=256,
						temperature=0.2,
					)
					done = False
					for chunk in stream:
						if not chunk.choices:
							continue
						choice = chunk.choices[0]
						# Capture content if present
						if choice.delta and hasattr(choice.delta, 'content') and choice.delta.content:
							chunk_queue.put({"response": choice.delta.content, "done": False})
						else:
							# Log empty chunks to debug
							if choice.finish_reason:
								pass  # Normal end marker
						# Mark done when finish_reason is set
						if choice.finish_reason:
							if not done:
								chunk_queue.put({"response": "", "done": True})
								done = True
				else:
					stream = self.ollama.generate(
						model=self.config.llm_model,
						prompt=prompt,
						stream=True,
						options={
							"num_predict": 256,
							"temperature": 0.2,
						},
					)
					for chunk in stream:
						chunk_queue.put(chunk)
			except Exception as exc:  # noqa: BLE001
				print(f"[rag] Generation error: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
				error_queue.put(exc)
			finally:
				done_event.set()

		threading.Thread(target=_generation_worker, daemon=True).start()
		response_parts: list[str] = []
		chunk_count = 0
		last_heartbeat = -heartbeat_s
		while True:
			if not error_queue.empty():
				raise error_queue.get()

			elapsed = time.monotonic() - started_at
			if elapsed > generation_timeout_s:
				raise TimeoutError(
					"LLM generation timed out after "
					f"{generation_timeout_s}s. Try increasing LLM_GENERATE_TIMEOUT_SECONDS or use a faster model."
				)

			if elapsed - last_heartbeat >= heartbeat_s:
				print(
					f"[rag] Waiting for model output... {elapsed:.0f}s elapsed",
					file=sys.stderr,
					flush=True,
				)
				last_heartbeat = elapsed

			try:
				chunk = chunk_queue.get(timeout=1.0)
			except queue.Empty:
				if done_event.is_set() and chunk_queue.empty():
					break
				continue

			chunk_count += 1
			piece = str(chunk.get("response", ""))
			if piece:
				response_parts.append(piece)
				sys.stdout.write(piece)
				sys.stdout.flush()
			if bool(chunk.get("done", False)):
				break
		response_text = "".join(response_parts)
		elapsed = time.monotonic() - started_at
		print(f"\n[rag] Answer generation complete in {elapsed:.2f}s after {chunk_count} chunk(s).", file=sys.stderr, flush=True)
		return {
			"answer": response_text,
			"contexts": contexts,
		}


def main() -> None:
	parser = argparse.ArgumentParser(description="Ask questions over embedded document chunks.")
	parser.add_argument("question", type=str, help="Question to ask the RAG system.")
	parser.add_argument("--top-k", type=int, default=None, help="Number of chunks to retrieve.")
	args = parser.parse_args()

	config = AppConfig.from_env()
	print("[rag] Loaded configuration; initializing engine...", file=sys.stderr, flush=True)
	engine = RagEngine(config)
	print("[rag] Engine ready; executing question...", file=sys.stderr, flush=True)
	result = engine.answer(args.question, top_k=args.top_k)

	if result["answer"]:
		if not result["answer"].endswith("\n"):
			print()
	print("\nSources:")
	for idx, ctx in enumerate(result["contexts"], start=1):
		print(f"[{idx}] {ctx.source_file} (page {ctx.page_number}) score={ctx.score:.4f}")


if __name__ == "__main__":
	main()

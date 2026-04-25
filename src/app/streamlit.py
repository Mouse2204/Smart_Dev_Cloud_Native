from __future__ import annotations

import streamlit as st

from src.app.rag import RagEngine
from src.storage.schemas import AppConfig


@st.cache_resource
def get_engine() -> RagEngine:
	return RagEngine(AppConfig.from_env())


def main() -> None:
	st.set_page_config(page_title="Smart Dev Docs RAG", layout="wide")
	st.title("Smart Dev Docs RAG")
	st.caption("Ask questions over PDFs ingested to MinIO and embedded into Qdrant.")

	question = st.text_input("Your question", placeholder="Example: What is the architecture in this PDF?")
	top_k = st.slider("Top-K retrieved chunks", min_value=1, max_value=10, value=4)

	if st.button("Ask"):
		if not question.strip():
			st.warning("Please enter a question.")
			return

		with st.spinner("Retrieving context and generating answer..."):
			engine = get_engine()
			result = engine.answer(question=question, top_k=top_k)

		st.subheader("Answer")
		st.write(result["answer"])

		st.subheader("Retrieved Chunks")
		if not result["contexts"]:
			st.info("No context found in Qdrant. Run the embedding pipeline first.")
			return

		for idx, ctx in enumerate(result["contexts"], start=1):
			with st.expander(
				f"[{idx}] {ctx.source_file} | page {ctx.page_number} | score={ctx.score:.4f}"
			):
				st.write(ctx.text)


if __name__ == "__main__":
	main()

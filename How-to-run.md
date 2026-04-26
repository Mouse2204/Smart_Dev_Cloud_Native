# How To Run (Pipeline + Groq)

Use this single guide for full flow: ingest PDFs, build embeddings, then ask with Groq.

## 1) Setup once

```bash
cd /home/den/DE/Smart_Dev_Cloud_Native
source .venv/bin/activate
python -m pip install -r requirements.txt
```

## 2) Build pipeline (PDF -> embeddings -> Qdrant)

```bash
./k8s/build.sh pipeline --source-dir data/books
```

If PDFs are already in MinIO:

```bash
./k8s/build.sh pipeline --skip-upload
```
## 3*) Ask using ui of Streamlit:
after embedding: run this command and navigating localhost:8501 for interaction:
```bash
./k8s/build.sh ui
```

## 3) Ask with Groq

```bash
export GROQ_API_KEY=gsk_your_key_here
./k8s/ask-debug.sh "What is the PDF about? Cite source chunks."
```

One-line version:

```bash
GROQ_API_KEY=gsk_your_key_here ./k8s/ask-debug.sh "Summarize the PDF and list key topics"
```

## 4) Useful checks

```bash
./k8s/build.sh inspect --limit 5
./k8s/build.sh ui
./k8s/build.sh help
```

## 5) Optional settings

```bash
USE_GROQ=true
LLM_MODEL=llama-3.3-70b-versatile
LLM_GENERATE_TIMEOUT_SECONDS=60
LLM_GENERATE_HEARTBEAT_SECONDS=5
```

Example with custom timeout:

```bash
GROQ_API_KEY=gsk_your_key_here \
LLM_GENERATE_TIMEOUT_SECONDS=120 \
./k8s/ask-debug.sh "Your question"
```

## 6) Service endpoints

- MinIO API: http://localhost:9000
- MinIO Console: http://localhost:9001
- Qdrant: http://localhost:6333
- Ollama: http://localhost:11434

MinIO default credentials:

- Access key: minioadmin
- Secret key: minioadmin123

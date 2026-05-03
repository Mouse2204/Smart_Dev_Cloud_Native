#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

ENV_FILE="$ROOT_DIR/.env"
if [[ -f "$ENV_FILE" ]]; then
	set -a
	# shellcheck disable=SC1090
	source "$ENV_FILE"
	set +a
fi

log() {
	echo "[build.sh] $*"
}

if [[ -n "${PYTHON_BIN:-}" ]]; then
	PYTHON_BIN="$PYTHON_BIN"
elif [[ -f "$ROOT_DIR/.venv/Scripts/python.exe" ]]; then
	PYTHON_BIN="$ROOT_DIR/.venv/Scripts/python.exe"
else
	PYTHON_BIN="python3"
fi
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
	echo "Python executable not found: $PYTHON_BIN"
	echo "Set PYTHON_BIN explicitly, for example:"
	echo "  PYTHON_BIN=/home/den/.venv/bin/python ./k8s/build.sh pipeline"
	exit 1
fi

log "Using Python: $PYTHON_BIN"

find_bin() {
	local bin="$1"
	# On Windows (check for standard env vars), prioritize .exe
	if [[ -n "${WINDIR:-}" || -n "${COMSPEC:-}" ]]; then
		if command -v "${bin}.exe" >/dev/null 2>&1; then
			echo "${bin}.exe"
			return 0
		fi
	fi
	if command -v "$bin" >/dev/null 2>&1; then
		echo "$bin"
	elif command -v "${bin}.exe" >/dev/null 2>&1; then
		echo "${bin}.exe"
	else
		return 1
	fi
}

KUBECTL_BIN=$(find_bin kubectl || echo "kubectl.exe")

run_kubectl() {
	# Try the primary KUBECTL_BIN first
	if "$KUBECTL_BIN" cluster-info >/dev/null 2>&1; then
		"$KUBECTL_BIN" "$@"
	# Fallback to powershell.exe on Windows/WSL/GitBash
	elif command -v powershell.exe >/dev/null 2>&1; then
		powershell.exe -NoProfile -Command "kubectl $*"
	else
		"$KUBECTL_BIN" "$@"
	fi
}

to_win_path() {
	local path="$1"
	if command -v wslpath >/dev/null 2>&1; then
		wslpath -w "$path"
	else
		# fallback for Git Bash or if wslpath is missing
		echo "$path" | sed -e 's|^\/\([a-z]\)\/|\1:/|' -e 's|^\/mnt\/\([a-z]\)\/|\1:/|'
	fi
}

PORT_FORWARD_PIDS=()

cleanup() {
	for pid in "${PORT_FORWARD_PIDS[@]:-}"; do
		kill "$pid" >/dev/null 2>&1 || true
	done
}

trap cleanup EXIT

is_port_open() {
	local host="$1"
	local port="$2"
	python_cmd="$PYTHON_BIN"
	"$python_cmd" - <<PY
import socket, sys
sock = socket.socket()
sock.settimeout(0.5)
try:
    sock.connect(("$host", int("$port")))
except OSError:
    sys.exit(1)
else:
    sys.exit(0)
finally:
    sock.close()
PY
}

start_port_forward() {
	local namespace="$1"
	local service="$2"
	local local_port="$3"
	local remote_port="$4"
	local log_file="/tmp/${service}-${local_port}.port-forward.log"
	log "Checking port-forward target ${namespace}/${service} on localhost:${local_port} -> ${remote_port}"
	if is_port_open 127.0.0.1 "$local_port"; then
		log "Port already open on localhost:${local_port}; skipping port-forward"
		return 0
	fi

	log "Starting port-forward for ${namespace}/${service} on localhost:${local_port} -> ${remote_port}"
	run_kubectl -n "$namespace" port-forward "svc/${service}" "${local_port}:${remote_port}" >"$log_file" 2>&1 &
	local pf_pid=$!
	PORT_FORWARD_PIDS+=("$pf_pid")

	for _ in $(seq 1 30); do
		if is_port_open 127.0.0.1 "$local_port"; then
			log "Port-forward ready for ${namespace}/${service} on localhost:${local_port}"
			case "$service" in
				minio-service)
					if [[ "$local_port" == "9000" ]]; then
						export MINIO_ENDPOINT="localhost:${local_port}"
					fi
					if [[ "$local_port" == "9001" ]]; then
						export MINIO_CONSOLE_URL="http://localhost:${local_port}"
					fi
					;;
				qdrant-service)
					export QDRANT_URL="http://localhost:${local_port}"
					;;
				ollama-service)
					export OLLAMA_BASE_URL="http://localhost:${local_port}"
					;;
			esac
			return 0
		fi
		sleep 1
	done

	echo "Failed to start port-forward for ${service}. Last log lines:"
	log "Port-forward failed for ${namespace}/${service}; dumping last log lines"
	tail -n 20 "$log_file" || true
	exit 1
}

export MINIO_ENDPOINT="${MINIO_ENDPOINT:-localhost:9000}"
export MINIO_CONSOLE_URL="${MINIO_CONSOLE_URL:-http://localhost:9001}"
export QDRANT_URL="${QDRANT_URL:-http://localhost:6333}"
export OLLAMA_BASE_URL="${OLLAMA_BASE_URL:-http://localhost:11434}"

ensure_services() {
	if ! is_port_open 127.0.0.1 9000; then
		start_port_forward minio minio-service 9000 9000
	fi

	if ! is_port_open 127.0.0.1 9001; then
		start_port_forward minio minio-service 9001 9001
	fi

	if ! is_port_open 127.0.0.1 6333; then
		start_port_forward qdrant qdrant-service 6333 6333
	fi

	if ! is_port_open 127.0.0.1 11434; then
		start_port_forward ollama ollama-service 11434 11434
	fi

	if ! is_port_open 127.0.0.1 9092; then
		start_port_forward kafka-kraft kafka-service 9092 9094
	fi

	echo "MinIO API:     ${MINIO_ENDPOINT}"
	echo "MinIO Console: ${MINIO_CONSOLE_URL}"
	echo "Kafka Broker:  localhost:9092"
}


print_help() {
	cat <<'EOF'
Usage:
	./k8s/build.sh pipeline [--source-dir data/books] [--skip-upload] [--no-multimodal]
	./k8s/build.sh crawl              # Run blog RSS crawler + AI summarizer
	./k8s/build.sh inspect [--limit 5]
	./k8s/build.sh ask "your question" [--top-k 4]
	./k8s/build.sh ui
	./k8s/build.sh test               # Run unit tests with pytest

Environment (optional overrides):
	SOURCE_BOOKS_DIR, MINIO_ENDPOINT, MINIO_ACCESS_KEY, MINIO_SECRET_KEY
	QDRANT_URL, QDRANT_COLLECTION, OLLAMA_BASE_URL
	OLLAMA_EMBED_MODEL, OLLAMA_LLM_MODEL, QDRANT_BLOG_COLLECTION

Examples:
	./k8s/build.sh pipeline --source-dir data/books
	./k8s/build.sh crawl
	./k8s/build.sh ask "Summarize this PDF"
	./k8s/build.sh ui
EOF
}

if [[ $# -lt 1 ]]; then
	print_help
	exit 1
fi

cmd="$1"
shift

log "Dispatching command: ${cmd} $*"

case "$cmd" in
	pipeline)
		ensure_services
		log "Starting pipeline"
		"$PYTHON_BIN" -m src.processing.embedding_worker "$@"
		log "Pipeline finished successfully"
		;;
	crawl)
		ensure_services
		log "Starting blog crawler"
		"$PYTHON_BIN" -m src.processing.blog_crawler
		log "Blog crawler finished"
		;;
	inspect)
		ensure_services
		log "Starting inspect"
		"$PYTHON_BIN" -m src.app.inspect_embeddings "$@"
		log "Inspect finished successfully"
		;;
	ask)
		if [[ $# -lt 1 ]]; then
			echo "Missing question for 'ask' command"
			print_help
			exit 1
		fi
		ensure_services
		log "Starting ask"
		"$PYTHON_BIN" -m src.app.rag "$@"
		log "Ask finished successfully"
		;;
	ui)
		ensure_services
		log "Starting Streamlit UI"
		echo "Open Streamlit at: http://localhost:8501"
		"$PYTHON_BIN" -m streamlit run src/app/streamlit.py --server.address 0.0.0.0 --server.port 8501 --server.headless true
		;;
	test)
		log "Running unit tests"
		"$PYTHON_BIN" -m pytest tests/
		;;
	help|-h|--help)
		print_help
		;;
	*)
		echo "Unknown command: $cmd"
		print_help
		exit 1
		;;
esac

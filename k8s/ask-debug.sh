#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

QUESTION="${1:-What is the PDF about? Cite source chunks.}"
TIMEOUT_SECONDS="${TIMEOUT_SECONDS:-60}"
USE_GROQ="${USE_GROQ:-true}"
GROQ_API_KEY="${GROQ_API_KEY:-}"
GEN_TIMEOUT_SECONDS="${LLM_GENERATE_TIMEOUT_SECONDS:-60}"
HEARTBEAT_SECONDS="${LLM_GENERATE_HEARTBEAT_SECONDS:-5}"

LOG_DIR="${LOG_DIR:-$ROOT_DIR/logs}"
mkdir -p "$LOG_DIR"
TS="$(date +%Y%m%d-%H%M%S)"
LOG_FILE="$LOG_DIR/ask-debug-$TS.log"

echo "[ask-debug] Question: $QUESTION"
echo "[ask-debug] Use Groq: $USE_GROQ"
if [[ "$USE_GROQ" == "true" ]] && [[ -z "$GROQ_API_KEY" ]]; then
	echo "[ask-debug] ERROR: GROQ_API_KEY not set. Get it from https://console.groq.com/keys"
	echo "[ask-debug] Usage: GROQ_API_KEY=gsk_... ./k8s/ask-debug.sh"
	exit 1
fi
echo "[ask-debug] timeout command: ${TIMEOUT_SECONDS}s"
echo "[ask-debug] llm generation timeout: ${GEN_TIMEOUT_SECONDS}s"
echo "[ask-debug] llm heartbeat: ${HEARTBEAT_SECONDS}s"
echo "[ask-debug] log file: $LOG_FILE"

action_cmd=(
	"./k8s/build.sh"
	"ask"
	"$QUESTION"
)

set +e
export USE_GROQ="$USE_GROQ"
export GROQ_API_KEY="$GROQ_API_KEY"
export LLM_GENERATE_TIMEOUT_SECONDS="$GEN_TIMEOUT_SECONDS"
export LLM_GENERATE_HEARTBEAT_SECONDS="$HEARTBEAT_SECONDS"
timeout "$TIMEOUT_SECONDS" "${action_cmd[@]}" 2>&1 | tee "$LOG_FILE"
CMD_EXIT=${PIPESTATUS[0]}
set -e

echo "[ask-debug] exit code: $CMD_EXIT"

if [[ "$CMD_EXIT" -eq 124 ]]; then
	echo "[ask-debug] Timeout reached. Increase TIMEOUT_SECONDS."
fi

exit "$CMD_EXIT"

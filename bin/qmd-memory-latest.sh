#!/bin/bash
set -euo pipefail

QMD="${HOME}/.local/bin/qmd-codex"
TARGET="${HOME}/.cache/qmd/codex_chat"
STATE_DIR="${TARGET}/.state"
LATEST_PATH_FILE="${STATE_DIR}/latest_projection.txt"
COLLECTION_NAME="codex-chat"
INDEX_NAME="codex_chat"
TAIL_LINES="${TAIL_LINES:-500}"

if [[ ! -x "$QMD" ]]; then
  echo "ERROR: missing qmd wrapper at $QMD" >&2
  exit 1
fi

if [[ ! -f "$LATEST_PATH_FILE" ]]; then
  echo "ERROR: latest pointer missing at $LATEST_PATH_FILE" >&2
  echo "Run: ${HOME}/.local/bin/sync-codex-chat-qmd.sh" >&2
  exit 1
fi

latest_path="$(cat "$LATEST_PATH_FILE")"
if [[ ! -f "$latest_path" ]]; then
  echo "ERROR: latest projected file not found: $latest_path" >&2
  echo "Run: ${HOME}/.local/bin/sync-codex-chat-qmd.sh" >&2
  exit 1
fi

rel="${latest_path#$TARGET/}"
uri="qmd://${COLLECTION_NAME}/${rel}"

line_count="$(wc -l < "$latest_path" | tr -d ' ')"
if [[ "$line_count" =~ ^[0-9]+$ ]] && (( line_count > TAIL_LINES )); then
  from_line=$((line_count - TAIL_LINES + 1))
else
  from_line=1
fi

echo "LATEST_FILE=$latest_path"
echo "LATEST_URI=$uri"
echo "TOTAL_LINES=$line_count"
echo "FROM_LINE=$from_line"
echo ""

"$QMD" --index "$INDEX_NAME" get "$uri:$from_line" -l "$TAIL_LINES"

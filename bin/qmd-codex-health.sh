#!/bin/bash
set -euo pipefail

QMD="${HOME}/.local/bin/qmd-codex"
INDEX_NAME="codex_chat"
DB_PATH="${HOME}/.cache/qmd/${INDEX_NAME}.sqlite"

if [[ ! -x "$QMD" ]]; then
  echo "ERROR: missing qmd at $QMD" >&2
  exit 1
fi

if [[ ! -f "$DB_PATH" ]]; then
  echo "ERROR: missing index db at $DB_PATH" >&2
  exit 1
fi

total_docs="$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM documents WHERE active=1;")"
embedded_docs="$(sqlite3 "$DB_PATH" "SELECT COUNT(DISTINCT d.id) FROM documents d JOIN content_vectors v ON d.hash=v.hash WHERE d.active=1;")"
status_text="$("$QMD" --index "$INDEX_NAME" status)"
vector_chunks="$(printf '%s\n' "$status_text" | awk '/Vectors:/ {print $2; exit}')"
needs_embedding=$((total_docs - embedded_docs))
has_vector_index="false"

if [[ "$embedded_docs" =~ ^[0-9]+$ ]] && (( embedded_docs > 0 )); then
  has_vector_index="true"
fi

printf 'index=%s totalDocuments=%s vectors=%s needsEmbedding=%s hasVectorIndex=%s\n' \
  "$INDEX_NAME" "$total_docs" "${vector_chunks:-unknown}" "$needs_embedding" "$has_vector_index"

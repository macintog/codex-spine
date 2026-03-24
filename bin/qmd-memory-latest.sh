#!/bin/bash
set -euo pipefail

QMD="${HOME}/.local/bin/qmd-codex"
TARGET="${HOME}/.cache/qmd/codex_chat"
STATE_DIR="${TARGET}/.state"
PROJECTS_DIR="${STATE_DIR}/projects"
COLLECTION_NAME="codex-chat"
INDEX_NAME="codex_chat"
TAIL_LINES="${TAIL_LINES:-500}"
PROJECT_CWD="${1:-$PWD}"

if [[ ! -x "$QMD" ]]; then
  echo "ERROR: missing qmd wrapper at $QMD" >&2
  exit 1
fi

canonical_project_path() {
  local cwd="$1"
  local root=""

  if [[ -n "$cwd" && -d "$cwd" ]]; then
    root="$(git -C "$cwd" rev-parse --show-toplevel 2>/dev/null || true)"
    if [[ -n "$root" ]]; then
      printf '%s\n' "$root"
      return 0
    fi
    (cd "$cwd" >/dev/null 2>&1 && pwd -P) || printf '%s\n' "$cwd"
    return 0
  fi

  if [[ -n "$cwd" ]]; then
    printf '%s\n' "$cwd"
  else
    pwd -P
  fi
}

project_key_for_path() {
  local project_path="$1"
  local base
  local slug
  local hash

  base="$(basename "$project_path" 2>/dev/null || true)"
  slug="$(printf '%s' "$base" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9]+/-/g; s/^-+//; s/-+$//')"
  [[ -z "$slug" ]] && slug="project"

  hash="$(printf '%s' "$project_path" | shasum -a 1 | awk '{print $1}' | cut -c1-12)"
  printf '%s-%s\n' "$slug" "$hash"
}

project_path="$(canonical_project_path "$PROJECT_CWD")"
project_key="$(project_key_for_path "$project_path")"
project_doc_path="${TARGET}/projects/${project_key}/project-memory.md"

if [[ ! -f "$project_doc_path" ]]; then
  echo "ERROR: project memory missing for $project_path" >&2
  echo "Expected: $project_doc_path" >&2
  echo "Run: ${HOME}/.local/bin/sync-codex-chat-qmd.sh" >&2
  exit 1
fi

rel="${project_doc_path#$TARGET/}"
uri="qmd://${COLLECTION_NAME}/${rel}"

line_count="$(wc -l < "$project_doc_path" | tr -d ' ')"
if [[ "$line_count" =~ ^[0-9]+$ ]] && (( line_count > TAIL_LINES )); then
  from_line=$((line_count - TAIL_LINES + 1))
else
  from_line=1
fi

echo "PROJECT_PATH=$project_path"
echo "PROJECT_KEY=$project_key"
echo "PROJECT_FILE=$project_doc_path"
echo "PROJECT_URI=$uri"
echo "TOTAL_LINES=$line_count"
echo "FROM_LINE=$from_line"
echo ""

"$QMD" --index "$INDEX_NAME" get "$uri:$from_line" -l "$TAIL_LINES"

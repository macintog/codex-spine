#!/bin/bash

gitea_log() {
  printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >&2
}

gitea_die() {
  printf '[%s] ERROR: %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >&2
  exit 1
}

gitea_json_get() {
  python3 -c 'import json,sys; data=json.load(sys.stdin); path=sys.argv[1].split("."); cur=data
for part in path:
    if isinstance(cur, dict):
        cur = cur.get(part)
    else:
        cur = None
        break
if cur is None:
    sys.exit(1)
if isinstance(cur, (dict, list)):
    print(json.dumps(cur))
else:
    print(cur)' "$1"
}

gitea_credential_fill() {
  local protocol="$1"
  local host="$2"
  local user="$3"
  printf 'protocol=%s\nhost=%s\nusername=%s\n\n' "$protocol" "$host" "$user" | git credential fill 2>/dev/null || true
}

gitea_resolve_remote() {
  local remote="$1"
  local remote_url
  local rest
  local auth_host
  local path_part
  local user=""
  local hostport
  local repo_part
  local owner_part

  remote_url="$(git remote get-url "$remote" 2>/dev/null || true)"
  [[ -n "$remote_url" ]] || gitea_die "Remote '$remote' not found."

  case "$remote_url" in
    http://*|https://*) ;;
    *) gitea_die "Only HTTP(S) remotes are supported by this helper. Remote URL: $remote_url" ;;
  esac

  GITEA_REMOTE_URL="$remote_url"
  GITEA_PROTO="${remote_url%%://*}"
  rest="${remote_url#*://}"
  auth_host="${rest%%/*}"
  path_part="${rest#*/}"

  hostport="$auth_host"
  if [[ "$auth_host" == *"@"* ]]; then
    user="${auth_host%@*}"
    hostport="${auth_host#*@}"
  fi

  GITEA_HOSTPORT="$hostport"
  GITEA_HOST="${hostport%%:*}"
  GITEA_BASE_URL="${GITEA_PROTO}://${hostport}"
  owner_part="${path_part%%/*}"
  repo_part="${path_part#*/}"
  GITEA_OWNER="$owner_part"
  GITEA_ORG="$owner_part"
  GITEA_REPO="${repo_part%.git}"

  [[ -n "$GITEA_OWNER" && -n "$GITEA_REPO" && "$GITEA_OWNER" != "$repo_part" ]] || \
    gitea_die "Could not parse owner/repo from remote URL: $remote_url"

  if [[ -z "$user" ]]; then
    user="${GITEA_USERNAME:-${USER:-}}"
  fi
  GITEA_USER="$user"
}

gitea_resolve_credentials() {
  local cred
  GITEA_PASSWORD="${GITEA_TOKEN:-}"
  if [[ -z "$GITEA_PASSWORD" ]]; then
    cred="$(gitea_credential_fill "$GITEA_PROTO" "$GITEA_HOSTPORT" "$GITEA_USER")"
    if [[ -z "$cred" ]]; then
      cred="$(gitea_credential_fill "$GITEA_PROTO" "$GITEA_HOST" "$GITEA_USER")"
    fi
    GITEA_PASSWORD="$(printf '%s\n' "$cred" | awk -F= '/^password=/{sub(/^password=/,""); print; exit}')"
  fi

  [[ -n "$GITEA_PASSWORD" ]] || gitea_die "No credentials found. Set GITEA_TOKEN or authenticate once with git push."
}

gitea_setup_netrc() {
  GITEA_NETRC_FILE="$(mktemp)"
  chmod 600 "$GITEA_NETRC_FILE"
  printf 'machine %s login %s password %s\n' "$GITEA_HOST" "$GITEA_USER" "$GITEA_PASSWORD" > "$GITEA_NETRC_FILE"
}

gitea_api_request() {
  local method="$1"
  local url="$2"
  local output_path="$3"
  local payload="${4:-}"
  local code

  if [[ -n "$payload" ]]; then
    code="$(curl -sS --netrc-file "$GITEA_NETRC_FILE" -o "$output_path" -w '%{http_code}' \
      -H 'Content-Type: application/json' \
      -X "$method" "$url" \
      -d "$payload" || true)"
  elif [[ "$method" == "GET" ]]; then
    code="$(curl -sS --netrc-file "$GITEA_NETRC_FILE" -o "$output_path" -w '%{http_code}' \
      "$url" || true)"
  else
    code="$(curl -sS --netrc-file "$GITEA_NETRC_FILE" -o "$output_path" -w '%{http_code}' \
      -X "$method" "$url" || true)"
  fi
  printf '%s\n' "$code"
}

gitea_error_body() {
  local path="$1"
  local lines="${2:-40}"
  sed -n "1,${lines}p" "$path" | tr '\n' ' '
}

gitea_read_text_file() {
  local path="$1"
  python3 - <<'PY' "$path"
from pathlib import Path
import sys

sentinel = "__CODEX_GITEA_END__"
sys.stdout.write(Path(sys.argv[1]).read_text(encoding="utf-8"))
sys.stdout.write(sentinel)
PY
}

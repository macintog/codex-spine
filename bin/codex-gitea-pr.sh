#!/bin/bash
set -euo pipefail

SOURCE_PATH="${BASH_SOURCE[0]}"
while [[ -h "$SOURCE_PATH" ]]; do
  SOURCE_DIR="$(cd -P "$(dirname "$SOURCE_PATH")" && pwd)"
  SOURCE_PATH="$(readlink "$SOURCE_PATH")"
  [[ "$SOURCE_PATH" != /* ]] && SOURCE_PATH="$SOURCE_DIR/$SOURCE_PATH"
done
SCRIPT_DIR="$(cd -P "$(dirname "$SOURCE_PATH")" && pwd)"
source "$SCRIPT_DIR/codex-gitea-common.sh"

usage() {
  cat <<'USAGE'
Usage: codex-gitea-pr.sh [remote] [head-branch] [base-branch]

Default remote: origin
Default head branch: current branch
Default base branch: repo default branch from Gitea API

Environment:
- GITEA_TOKEN: API token or password override
- GITEA_USERNAME: defaults to the remote user or current shell user
- PR_TITLE: optional PR title override
- PR_BODY: optional PR body override

Behavior:
1) Parse HTTP(S) Gitea remote URL.
2) Authenticate with Gitea using stored git credentials or GITEA_TOKEN.
3) Resolve the repo default branch unless base is provided explicitly.
4) Reuse an existing open PR for the same head/base when present.
5) Otherwise create a new pull request and print its URL.

Options:
-h, --help            Show this help text.
-n, --dry-run         Print the resolved API payload without creating or updating a PR.
--title <text>        Override the PR title.
--body-file <path>    Read the PR body from a file. Use `-` to read stdin.
--update-existing     Update the existing open PR for the same head/base with the resolved title/body.
--json                Emit a machine-readable JSON result on stdout.
USAGE
}

emit_result() {
  local action="$1"
  local url="$2"
  local number="$3"
  local payload_json="$4"
  local existing="$5"
  local draft="$6"
  if [[ "$JSON_OUTPUT" -eq 1 ]]; then
    python3 - <<'PY' "$action" "$url" "$number" "$HEAD_BRANCH" "$BASE_BRANCH" "$existing" "$payload_json" "$draft"
import json, sys
action, url, number, head, base, existing, payload_json, draft = sys.argv[1:9]
number_value = int(number) if number else None
draft_value = draft.lower() == "true"
print(
    json.dumps(
        {
            "action": action,
            "url": url,
            "number": number_value,
            "head": head,
            "base": base,
            "existing": existing == "1",
            "draft": draft_value,
            "payload": json.loads(payload_json),
        }
    )
)
PY
  else
    printf '%s\n' "$url"
  fi
}

DRY_RUN=0
JSON_OUTPUT=0
UPDATE_EXISTING=0
TITLE_OVERRIDE=""
BODY_FILE=""
TEXT_SENTINEL="__CODEX_GITEA_END__"
while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    -n|--dry-run)
      DRY_RUN=1
      shift
      ;;
    --title)
      [[ $# -ge 2 ]] || gitea_die "--title requires a value"
      TITLE_OVERRIDE="$2"
      shift 2
      ;;
    --body-file)
      [[ $# -ge 2 ]] || gitea_die "--body-file requires a value"
      BODY_FILE="$2"
      shift 2
      ;;
    --update-existing)
      UPDATE_EXISTING=1
      shift
      ;;
    --json)
      JSON_OUTPUT=1
      shift
      ;;
    *)
      break
      ;;
  esac
done

REMOTE="${1:-origin}"
HEAD_BRANCH="${2:-$(git rev-parse --abbrev-ref HEAD)}"
BASE_BRANCH="${3:-}"

gitea_resolve_remote "$REMOTE"
gitea_resolve_credentials

netrc_file=""
tmp_resp="$(mktemp)"
body_file_tmp=""
cleanup() {
  rm -f "$netrc_file" "$tmp_resp" "$body_file_tmp"
}
trap cleanup EXIT
gitea_setup_netrc
netrc_file="$GITEA_NETRC_FILE"

repo_api="$GITEA_BASE_URL/api/v1/repos/$GITEA_ORG/$GITEA_REPO"
gitea_log "Checking repository: $GITEA_ORG/$GITEA_REPO"
repo_code="$(gitea_api_request GET "$repo_api" "$tmp_resp")"
if [[ "$repo_code" != "200" ]]; then
  err_body="$(gitea_error_body "$tmp_resp")"
  gitea_die "Repository lookup failed (HTTP $repo_code): $err_body"
fi

repo_json="$(cat "$tmp_resp")"
if [[ -z "$BASE_BRANCH" ]]; then
  BASE_BRANCH="$(printf '%s' "$repo_json" | gitea_json_get default_branch)" || \
    gitea_die "Could not determine default branch from repo API."
fi

pulls_api="$GITEA_BASE_URL/api/v1/repos/$GITEA_ORG/$GITEA_REPO/pulls"
query_url="$pulls_api?state=open"

existing_code="$(gitea_api_request GET "$query_url" "$tmp_resp")"
if [[ "$existing_code" != "200" ]]; then
  err_body="$(gitea_error_body "$tmp_resp")"
  gitea_die "Open PR lookup failed (HTTP $existing_code): $err_body"
fi

existing_pr_json="$(python3 - "$HEAD_BRANCH" "$BASE_BRANCH" "$tmp_resp" <<'PY'
import json, sys
head_branch, base_branch, payload_path = sys.argv[1:4]
with open(payload_path, "r", encoding="utf-8") as handle:
    items = json.load(handle)
for item in items:
    head = ((item.get("head") or {}).get("ref") or "")
    base = ((item.get("base") or {}).get("ref") or "")
    if head == head_branch and base == base_branch:
        print(json.dumps(item))
        break
PY
)"

existing_url=""
existing_number=""
existing_draft="false"
if [[ -n "$existing_pr_json" ]]; then
  existing_url="$(printf '%s' "$existing_pr_json" | gitea_json_get html_url || true)"
  existing_number="$(printf '%s' "$existing_pr_json" | gitea_json_get number || true)"
  existing_draft="$(printf '%s' "$existing_pr_json" | gitea_json_get draft || printf 'false')"
fi

if [[ -n "$BODY_FILE" ]]; then
  if [[ "$BODY_FILE" == "-" ]]; then
    body_file_tmp="$(mktemp)"
    cat > "$body_file_tmp"
    BODY_FILE="$body_file_tmp"
  fi
  [[ -f "$BODY_FILE" ]] || gitea_die "PR body file not found: $BODY_FILE"
  body="$(gitea_read_text_file "$BODY_FILE")"
  body="${body%$TEXT_SENTINEL}"
else
  body="${PR_BODY:-$(printf '## Summary\n- created from `%s` against `%s`\n\n## Validation\n- pending manual update\n' "$HEAD_BRANCH" "$BASE_BRANCH")}"
fi

title="${TITLE_OVERRIDE:-${PR_TITLE:-$(git log -1 --format=%s "$HEAD_BRANCH" 2>/dev/null || git log -1 --format=%s)}}"

payload="$(python3 - <<'PY' "$HEAD_BRANCH" "$BASE_BRANCH" "$title" "$body"
import json, sys
head, base, title, body = sys.argv[1:5]
print(json.dumps({"head": head, "base": base, "title": title, "body": body}))
PY
)"

if [[ "$DRY_RUN" -eq 1 ]]; then
  gitea_log "Dry run only."
  emit_result "dry-run" "${existing_url:-}" "${existing_number:-}" "$payload" "$( [[ -n "$existing_url" ]] && printf '1' || printf '0' )" "$existing_draft"
  exit 0
fi

if [[ -n "$existing_url" ]]; then
  if [[ "$UPDATE_EXISTING" -eq 1 ]]; then
    [[ -n "$existing_number" ]] || gitea_die "Existing PR matched but did not include a PR number."
    update_payload="$(python3 - <<'PY' "$BASE_BRANCH" "$title" "$body"
import json, sys
base, title, body = sys.argv[1:4]
print(json.dumps({"base": base, "title": title, "body": body}))
PY
)"
    gitea_log "Updating existing PR #$existing_number"
    update_code="$(gitea_api_request PATCH "$pulls_api/$existing_number" "$tmp_resp" "$update_payload")"
    case "$update_code" in
      200|201)
        updated_url="$(gitea_json_get html_url < "$tmp_resp")" || gitea_die "Updated PR response did not include html_url."
        updated_number="$(gitea_json_get number < "$tmp_resp")" || gitea_die "Updated PR response did not include number."
        updated_draft="$(gitea_json_get draft < "$tmp_resp" || printf 'false')"
        emit_result "updated" "$updated_url" "$updated_number" "$payload" "1" "$updated_draft"
        exit 0
        ;;
      *)
        err_body="$(gitea_error_body "$tmp_resp" 80)"
        gitea_die "PR update failed (HTTP $update_code): $err_body"
        ;;
    esac
  fi
  gitea_log "Open PR already exists: $existing_url"
  emit_result "existing" "$existing_url" "$existing_number" "$payload" "1" "$existing_draft"
  exit 0
fi

gitea_log "Creating pull request for $HEAD_BRANCH -> $BASE_BRANCH"
create_code="$(gitea_api_request POST "$pulls_api" "$tmp_resp" "$payload")"

case "$create_code" in
  201)
    pr_url="$(gitea_json_get html_url < "$tmp_resp")" || gitea_die "PR created but response did not include html_url."
    pr_number="$(gitea_json_get number < "$tmp_resp")" || gitea_die "PR created but response did not include number."
    gitea_log "Created PR: $pr_url"
    pr_draft="$(gitea_json_get draft < "$tmp_resp" || printf 'false')"
    emit_result "created" "$pr_url" "$pr_number" "$payload" "0" "$pr_draft"
    ;;
  *)
    err_body="$(gitea_error_body "$tmp_resp" 80)"
    gitea_die "PR create failed (HTTP $create_code): $err_body"
    ;;
esac

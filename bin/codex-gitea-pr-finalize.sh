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

REMOTE="origin"
COMMIT=""
DRY_RUN=0
JSON_OUTPUT=0
PR_URLS=()
PR_HEADS=()

usage() {
  cat <<'USAGE'
Usage: codex-gitea-pr-finalize.sh --commit SHA --pr-url URL --pr-head SHA [--pr-url URL --pr-head SHA ...]

Marks only the listed Gitea pull requests as manually merged at a verified
authoritative commit. It uses Gitea's per-request force-merge capability and
never changes the repository's persistent manual-merge policy.

Options:
--remote NAME    Git remote used to resolve Gitea repository identity (default: origin).
--commit SHA     Verified authoritative integration commit.
--pr-url URL     Pull request URL to finalize. Repeat for multiple pull requests.
--pr-head SHA    Recorded immutable head SHA for the corresponding pull request URL.
--dry-run        Validate and report the transaction without changing Gitea.
--json           Emit compact JSON.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --remote) REMOTE="$2"; shift 2 ;;
    --commit) COMMIT="$2"; shift 2 ;;
    --pr-url) PR_URLS+=("$2"); shift 2 ;;
    --pr-head) PR_HEADS+=("$2"); shift 2 ;;
    --dry-run|-n) DRY_RUN=1; shift ;;
    --json) JSON_OUTPUT=1; shift ;;
    --help|-h) usage; exit 0 ;;
    *) gitea_die "unknown argument: $1" ;;
  esac
done

[[ "$COMMIT" =~ ^[0-9a-fA-F]{40}$ ]] || gitea_die "--commit must be a full 40-character SHA"
(( ${#PR_URLS[@]} > 0 )) || gitea_die "at least one --pr-url is required"
(( ${#PR_URLS[@]} == ${#PR_HEADS[@]} )) || gitea_die "each --pr-url requires a corresponding --pr-head"
for head in "${PR_HEADS[@]}"; do
  [[ "$head" =~ ^[0-9a-fA-F]{40}$ ]] || gitea_die "--pr-head must be a full 40-character SHA"
done
git cat-file -e "$COMMIT^{commit}" 2>/dev/null || gitea_die "integration commit is not available locally: $COMMIT"

gitea_resolve_remote "$REMOTE"
gitea_resolve_credentials
netrc_file=""
tmp_resp="$(mktemp)"

cleanup() {
  rm -f "$netrc_file" "$tmp_resp"
}
trap cleanup EXIT
gitea_setup_netrc
netrc_file="$GITEA_NETRC_FILE"

repo_url="$GITEA_BASE_URL/api/v1/repos/$GITEA_ORG/$GITEA_REPO"
repo_code="$(gitea_api_request GET "$repo_url" "$tmp_resp")"
[[ "$repo_code" == "200" ]] || gitea_die "repository lookup failed (HTTP $repo_code): $(gitea_error_body "$tmp_resp")"
default_branch="$(python3 - "$tmp_resp" <<'PY'
import json, sys
with open(sys.argv[1], encoding="utf-8") as handle:
    value = json.load(handle).get("default_branch")
if not isinstance(value, str) or not value:
    raise SystemExit(2)
print(value)
PY
)" || gitea_die "repository lookup did not provide a default branch"
remote_default="$(git ls-remote --heads "$REMOTE" "refs/heads/$default_branch" 2>/dev/null | awk 'NR == 1 {print $1}')"
[[ "$remote_default" =~ ^[0-9a-fA-F]{40}$ ]] || gitea_die "could not verify authoritative remote default branch $default_branch"
[[ "$remote_default" == "$COMMIT" ]] || gitea_die "integration commit is not the authoritative remote default tip (remote $default_branch is $remote_default)"

numbers=()
for url in "${PR_URLS[@]}"; do
  number="$(python3 - "$url" "$GITEA_BASE_URL" "$GITEA_ORG" "$GITEA_REPO" <<'PY'
import re, sys
url, base, owner, repo = sys.argv[1:]
expected = base.rstrip("/") + f"/{owner}/{repo}/pulls/"
if not url.startswith(expected):
    raise SystemExit(2)
tail = url[len(expected):].rstrip("/")
if not re.fullmatch(r"[1-9][0-9]*", tail):
    raise SystemExit(2)
print(tail)
PY
)" || gitea_die "pull request URL does not belong to $GITEA_ORG/$GITEA_REPO: $url"
  numbers+=("$number")
done

results=()
for index in "${!numbers[@]}"; do
  number="${numbers[$index]}"
  expected_head="${PR_HEADS[$index]}"
  pr_api="$GITEA_BASE_URL/api/v1/repos/$GITEA_ORG/$GITEA_REPO/pulls/$number"
  pr_code="$(gitea_api_request GET "$pr_api" "$tmp_resp")"
  [[ "$pr_code" == "200" ]] || gitea_die "pull request #$number lookup failed (HTTP $pr_code): $(gitea_error_body "$tmp_resp")"
  read -r state head_sha merge_sha < <(python3 - "$tmp_resp" <<'PY'
import json, sys
with open(sys.argv[1], encoding="utf-8") as handle:
    item = json.load(handle)
print(item.get("state", ""), (item.get("head") or {}).get("sha", ""), item.get("merge_commit_sha", ""))
PY
)
  [[ "$head_sha" == "$expected_head" ]] || gitea_die "pull request #$number head does not match its recorded published tip"
  if [[ "$state" == "closed" ]]; then
    [[ -n "$merge_sha" && "$merge_sha" == "$COMMIT" ]] || gitea_die "pull request #$number is closed without the authoritative merge commit"
    results+=("$number:already-closed")
    continue
  fi
  git merge-base --is-ancestor "$expected_head" "$COMMIT" || gitea_die "pull request #$number head is not represented by integration commit $COMMIT"
  if [[ "$DRY_RUN" -eq 1 ]]; then
    results+=("$number:validated")
    continue
  fi
  merge_payload="$(python3 - "$COMMIT" <<'PY'
import json, sys
print(json.dumps({"Do":"manually-merged","MergeCommitID":sys.argv[1],"force_merge":True}, separators=(",", ":")))
PY
)"
  merge_code="$(gitea_api_request POST "$pr_api/merge" "$tmp_resp" "$merge_payload")"
  [[ "$merge_code" == "200" ]] || gitea_die "pull request #$number finalization failed (HTTP $merge_code): $(gitea_error_body "$tmp_resp")"
  results+=("$number:finalized")
done

python3 - "$REMOTE" "$COMMIT" "$DRY_RUN" "${results[@]}" <<'PY'
import json, sys
remote, commit, dry_run, *items = sys.argv[1:]
print(json.dumps({"action":"dry-run" if dry_run == "1" else "finalized","remote":remote,"commit":commit,"pull_requests":items}, separators=(",", ":"), sort_keys=True))
PY

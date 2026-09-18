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
DISPOSAL_BRANCH=""
seen_file=""
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
--disposal-branch REF  With --dry-run, prove no open review uses this managed head/base branch.
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
    --disposal-branch) DISPOSAL_BRANCH="$2"; shift 2 ;;
    --dry-run|-n) DRY_RUN=1; shift ;;
    --json) JSON_OUTPUT=1; shift ;;
    --help|-h) usage; exit 0 ;;
    *) gitea_die "unknown argument: $1" ;;
  esac
done

if [[ -n "$DISPOSAL_BRANCH" ]]; then
  [[ "$DRY_RUN" -eq 1 ]] || gitea_die "--disposal-branch requires --dry-run"
  git check-ref-format "refs/heads/$DISPOSAL_BRANCH" || gitea_die "invalid disposal branch"
fi

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
  rm -f "$netrc_file" "$tmp_resp" "$seen_file"
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
  read -r state head_sha merge_sha merged < <(python3 - "$tmp_resp" <<'PY'
import json, sys
with open(sys.argv[1], encoding="utf-8") as handle:
    item = json.load(handle)
print(item.get("state", ""), (item.get("head") or {}).get("sha", ""), item.get("merge_commit_sha") or "-", "true" if item.get("merged") is True else "false")
PY
)
  [[ "$head_sha" == "$expected_head" ]] || gitea_die "pull request #$number head does not match its recorded published tip"
  git merge-base --is-ancestor "$expected_head" "$COMMIT" || gitea_die "pull request #$number head is not represented by integration commit $COMMIT"
  if [[ "$state" == "closed" ]]; then
    # A selected review may have been merged before this aggregate transaction.
    # Preserve its historical merge record, but require both commits in keeper history.
    [[ "$merged" == "true" && "$merge_sha" =~ ^[0-9a-fA-F]{40}$ ]] &&
      git merge-base --is-ancestor "$merge_sha" "$COMMIT" ||
      gitea_die "pull request #$number is closed without the authoritative merge commit"
    results+=("$number:already-closed")
    continue
  fi
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

# A selected closed review is not enough: another open review may still use
# this repository's head or base ref. Traverse to an empty page, fail closed
# on malformed/repeated pages, and bound the read without treating a cap as proof.
if [[ -n "$DISPOSAL_BRANCH" ]]; then
  seen_file="$(mktemp)"
  printf '[]' > "$seen_file"
  complete=0
  for page in $(seq 1 100); do
    open_code="$(gitea_api_request GET "$repo_url/pulls?state=open&limit=50&page=$page" "$tmp_resp")"
    [[ "$open_code" == "200" ]] || gitea_die "open-review disposal proof failed (HTTP $open_code)"
    page_state="$(python3 - "$tmp_resp" "$seen_file" "$DISPOSAL_BRANCH" "$GITEA_ORG/$GITEA_REPO" <<'PY'
import json, sys
response, seen_path, branch, repository = sys.argv[1:]
with open(response, encoding="utf-8") as handle:
    items = json.load(handle)
with open(seen_path, encoding="utf-8") as handle:
    seen = set(json.load(handle))
if not isinstance(items, list):
    raise SystemExit("open-review page is not a list")
for item in items:
    if not isinstance(item, dict) or type(item.get("number")) is not int or item.get("state") != "open":
        raise SystemExit("open-review page lacks exact number/state")
    number = item["number"]
    if number in seen:
        raise SystemExit("open-review pagination repeated a review; proof is incomplete")
    seen.add(number)
    for role in ("head", "base"):
        ref = item.get(role)
        if not isinstance(ref, dict) or not isinstance(ref.get("ref"), str):
            raise SystemExit("open-review page lacks head/base identity")
        repo = ref.get("repo")
        if not isinstance(repo, dict) or not isinstance(repo.get("full_name"), str):
            raise SystemExit("open-review page lacks repository identity")
        if role == "base" and repo["full_name"] != repository:
            raise SystemExit("open-review base repository mismatch")
        if repo["full_name"] == repository and ref["ref"] == branch:
            raise SystemExit(f"open pull request #{number} still uses selected disposal ref as {role}")
with open(seen_path, "w", encoding="utf-8") as handle:
    json.dump(sorted(seen), handle)
print("complete" if not items else "next")
PY
)" || gitea_die "open-review head/base proof is incomplete or retains the selected branch"
    if [[ "$page_state" == "complete" ]]; then complete=1; break; fi
  done
  [[ "$complete" -eq 1 ]] || gitea_die "open-review disposal proof exceeded the bounded page limit"
fi

python3 - "$REMOTE" "$COMMIT" "$DRY_RUN" "$DISPOSAL_BRANCH" "${results[@]}" <<'PY'
import json, sys
remote, commit, dry_run, disposal_branch, *items = sys.argv[1:]
payload = {"action":"dry-run" if dry_run == "1" else "finalized","remote":remote,"commit":commit,"pull_requests":items}
if disposal_branch:
    payload["disposal_proof"] = {"branch": disposal_branch, "open_review_references": "none", "complete": True}
print(json.dumps(payload, separators=(",", ":"), sort_keys=True))
PY

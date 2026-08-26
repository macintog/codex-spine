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
Usage: codex-gitea-push.sh [options] [remote] [branch]

Default remote: origin
Default branch: current branch
Default created repo visibility: private

Behavior:
1) Parse HTTP(S) Gitea remote URL.
2) If owner/repo does not exist, create it via Gitea API.
3) Push branch with -u.

Credentials:
- First uses GITEA_TOKEN env var (recommended).
- Otherwise reads stored git credentials via `git credential fill`.

Options:
-h, --help   Show this help text.
-n, --dry-run  Print the resolved push plan without creating a repo or pushing.
--destination-branch <branch>  Push the local source branch to this non-force remote branch.
--visibility <public|private>  Override repo visibility when creating a repo. If the repo
                               already exists, visibility is only updated when this flag is
                               passed explicitly.
USAGE
}

DRY_RUN=0
VISIBILITY="private"
VISIBILITY_EXPLICIT=0
DESTINATION_BRANCH=""
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
    --visibility)
      [[ $# -ge 2 ]] || gitea_die "--visibility requires a value"
      case "$2" in
        public|private)
          VISIBILITY="$2"
          VISIBILITY_EXPLICIT=1
          ;;
        *)
          gitea_die "Unsupported visibility '$2'. Use 'public' or 'private'."
          ;;
      esac
      shift 2
      ;;
    --destination-branch)
      [[ $# -ge 2 ]] || gitea_die "--destination-branch requires a value"
      DESTINATION_BRANCH="$2"
      shift 2
      ;;
    *)
      break
      ;;
  esac
done

REMOTE="${1:-origin}"
BRANCH="${2:-$(git rev-parse --abbrev-ref HEAD)}"
DESTINATION_BRANCH="${DESTINATION_BRANCH:-$BRANCH}"

case "$REMOTE" in
  -*)
    gitea_die "Refusing option-like remote '$REMOTE'. Remote updates must name an explicit remote and branch."
    ;;
esac

case "$BRANCH" in
  +*|*:*)
    gitea_die "Refusing force or destination refspec '$BRANCH'. Push an ordinary branch name, or use an explicitly approved manual Git command."
    ;;
  -*)
    gitea_die "Refusing option-like branch '$BRANCH'. Push an ordinary branch name."
    ;;
esac

case "$DESTINATION_BRANCH" in
  +*|*:*)
    gitea_die "Refusing force or destination refspec '$DESTINATION_BRANCH'. Name one ordinary destination branch."
    ;;
  -*|'')
    gitea_die "Refusing invalid destination branch '$DESTINATION_BRANCH'. Name one ordinary destination branch."
    ;;
esac

gitea_resolve_remote "$REMOTE"
gitea_resolve_credentials

netrc_file=""
tmp_resp=""
askpass_script=""
cleanup() {
  rm -f "$netrc_file" "$tmp_resp" "$askpass_script"
}
trap cleanup EXIT
gitea_setup_netrc
netrc_file="$GITEA_NETRC_FILE"

tmp_resp="$(mktemp)"

repo_api="$GITEA_BASE_URL/api/v1/repos/$GITEA_OWNER/$GITEA_REPO"
create_api=""
visibility_private="true"
if [[ "$VISIBILITY" == "public" ]]; then
  visibility_private="false"
fi

gitea_log "Checking repository: $GITEA_OWNER/$GITEA_REPO"

if [[ "$DRY_RUN" -eq 1 ]]; then
  printf 'remote=%s\nbranch=%s\ndestination_branch=%s\nrepo=%s/%s\nremote_url=%s\nvisibility=%s\n' \
    "$REMOTE" "$BRANCH" "$DESTINATION_BRANCH" "$GITEA_OWNER" "$GITEA_REPO" "$GITEA_REMOTE_URL" "$VISIBILITY"
  exit 0
fi

repo_code="$(gitea_api_request GET "$repo_api" "$tmp_resp")"

if [[ "$repo_code" == "200" ]]; then
  gitea_log "Repository already exists."
  if [[ "$VISIBILITY_EXPLICIT" -eq 1 ]]; then
    current_private="$(gitea_json_get private < "$tmp_resp" || true)"
    case "$current_private" in
      True|true) current_private="true" ;;
      False|false) current_private="false" ;;
    esac
    desired_private="$visibility_private"
    if [[ "$current_private" != "$desired_private" ]]; then
      gitea_log "Updating repository visibility to $VISIBILITY"
      payload="{\"private\":$visibility_private}"
      update_code="$(gitea_api_request PATCH "$repo_api" "$tmp_resp" "$payload")"
      case "$update_code" in
        200|201)
          gitea_log "Repository visibility updated: $GITEA_OWNER/$GITEA_REPO"
          ;;
        *)
          err_body="$(gitea_error_body "$tmp_resp")"
          gitea_die "Repository visibility update failed (HTTP $update_code): $err_body"
          ;;
      esac
    fi
  fi
elif [[ "$repo_code" == "404" ]]; then
  user_api="$GITEA_BASE_URL/api/v1/user"
  user_code="$(gitea_api_request GET "$user_api" "$tmp_resp")"
  if [[ "$user_code" != "200" ]]; then
    err_body="$(gitea_error_body "$tmp_resp")"
    gitea_die "Authenticated user lookup failed (HTTP $user_code): $err_body"
  fi
  current_login="$(gitea_json_get login < "$tmp_resp" || true)"
  if [[ "$GITEA_OWNER" == "$current_login" ]]; then
    create_api="$GITEA_BASE_URL/api/v1/user/repos"
  else
    create_api="$GITEA_BASE_URL/api/v1/orgs/$GITEA_OWNER/repos"
  fi
  gitea_log "Repository missing. Creating via API..."
  payload="$(python3 - <<'PY' "$GITEA_REPO" "$visibility_private" "$BRANCH"
import json
import sys

name = sys.argv[1]
private_raw = sys.argv[2]
branch = sys.argv[3]
payload = {
    "name": name,
    "private": private_raw == "true",
}
if branch == "main":
    payload["default_branch"] = "main"
print(json.dumps(payload, separators=(",", ":")))
PY
)"
  create_code="$(gitea_api_request POST "$create_api" "$tmp_resp" "$payload")"

  case "$create_code" in
    201|202)
      gitea_log "Repository created: $GITEA_OWNER/$GITEA_REPO"
      ;;
    409|422)
      gitea_log "Repository already exists (API returned $create_code). Continuing."
      ;;
    403)
      gitea_die "Repository create forbidden for owner '$GITEA_OWNER'. Grant create permission or use a namespace where create is allowed."
      ;;
    *)
      err_body="$(gitea_error_body "$tmp_resp")"
      gitea_die "Repository create failed (HTTP $create_code): $err_body"
      ;;
  esac
else
  err_body="$(gitea_error_body "$tmp_resp")"
  gitea_die "Repository check failed (HTTP $repo_code): $err_body"
fi

gitea_log "Pushing $BRANCH to $REMOTE/$DESTINATION_BRANCH"
askpass_script="$(mktemp)"
chmod 700 "$askpass_script"
cat > "$askpass_script" <<'EOF'
#!/bin/sh
case "$1" in
  *Username*) printf '%s\n' "${GITEA_PUSH_USER:-}" ;;
  *) printf '%s\n' "${GITEA_PUSH_PASS:-}" ;;
esac
EOF

if [[ "$BRANCH" == "$DESTINATION_BRANCH" ]]; then
  set_upstream_flag=()
  upstream_ref="$(git rev-parse --abbrev-ref --symbolic-full-name '@{upstream}' 2>/dev/null || true)"
  if [[ -z "$upstream_ref" || "$upstream_ref" == "$REMOTE/"* ]]; then
    set_upstream_flag=(-u)
  fi
  GIT_TERMINAL_PROMPT=0 \
  GIT_ASKPASS="$askpass_script" \
  GITEA_PUSH_USER="$GITEA_USER" \
  GITEA_PUSH_PASS="$GITEA_PASSWORD" \
  git push "${set_upstream_flag[@]}" "$REMOTE" "$BRANCH"
else
  GIT_TERMINAL_PROMPT=0 \
  GIT_ASKPASS="$askpass_script" \
  GITEA_PUSH_USER="$GITEA_USER" \
  GITEA_PUSH_PASS="$GITEA_PASSWORD" \
  git push "$REMOTE" "$BRANCH:refs/heads/$DESTINATION_BRANCH"
fi
gitea_log "Done"

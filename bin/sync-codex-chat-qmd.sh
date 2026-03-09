#!/bin/bash
set -euo pipefail

SOURCE="${HOME}/.codex/sessions"
TARGET="${HOME}/.cache/qmd/codex_chat"
QMD="${HOME}/.local/bin/qmd-codex"
JQ="${JQ_BIN:-$(command -v jq || true)}"
INDEX_NAME="codex_chat"
COLLECTION_NAME="codex-chat"
LOCK_DIR="/tmp/codex-chat-qmd-sync.lock"
LOCK_WAIT_SECONDS="${LOCK_WAIT_SECONDS:-90}"
PROJECTION_VERSION="3"
BOOTSTRAP_VERSION="1"
STATE_DIR="$TARGET/.state"
PROJECTS_DIR="$STATE_DIR/projects"
LATEST_PROJECTION_FILE="$STATE_DIR/latest_projection.txt"
LATEST_QMD_URI_FILE="$STATE_DIR/latest_qmd_uri.txt"
LATEST_PROJECT_KEY_FILE="$STATE_DIR/latest_project_key.txt"
PROJECT_DOCS_DIR="$TARGET/projects"
INTENT_PIN_LIMIT="${INTENT_PIN_LIMIT:-20}"
OPEN_LOOP_LIMIT="${OPEN_LOOP_LIMIT:-12}"
DECISION_LIMIT="${DECISION_LIMIT:-10}"
RECENT_SESSION_LIMIT="${RECENT_SESSION_LIMIT:-10}"
PATH="${HOME}/.local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"
QMD_INDEX_CHANGED=0
EMBED_HEARTBEAT_SECONDS="${EMBED_HEARTBEAT_SECONDS:-15}"

log() {
    printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}

require_bin() {
    local p="$1"
    local name="$2"
    if [[ ! -x "$p" ]]; then
        log "ERROR missing $name at $p"
        exit 1
    fi
}

# macOS-first launchd automation lives elsewhere in this repo.
# Linux analog: run this from a systemd user timer or cron job.
# Windows analog: run it from Task Scheduler or a background service wrapper.

require_bin "$JQ" "jq"

wait_for_existing_sync() {
    local waited=0
    while [[ -d "$LOCK_DIR" ]]; do
        if (( waited >= LOCK_WAIT_SECONDS )); then
            log "ERROR timed out waiting for active sync to finish after ${LOCK_WAIT_SECONDS}s"
            return 1
        fi
        sleep 1
        waited=$((waited + 1))
    done

    log "Existing sync finished after ${waited}s wait"
}

target_for() {
    local src="$1"
    local rel="${src#$SOURCE/}"
    printf '%s/%s.md' "$TARGET" "${rel%.jsonl}"
}

skip_marker_for() {
    local src="$1"
    local rel="${src#$SOURCE/}"
    printf '%s/%s.skip' "$STATE_DIR" "${rel%.jsonl}"
}

write_skip_marker() {
    local src="$1"
    local reason="$2"
    local marker
    marker="$(skip_marker_for "$src")"
    mkdir -p "$(dirname "$marker")"
    {
        echo "projection_version=v${PROJECTION_VERSION}"
        echo "reason=${reason}"
        echo "source=${src#$SOURCE/}"
        echo "updated_utc=$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
    } > "$marker"
}

clear_skip_marker() {
    local src="$1"
    local marker
    marker="$(skip_marker_for "$src")"
    rm -f "$marker"
}

project_doc_path_for() {
    local project_key="$1"
    printf '%s/%s/project-memory.md' "$PROJECT_DOCS_DIR" "$project_key"
}

should_materialize_project_doc() {
    local project_path="$1"
    case "$project_path" in
        /tmp|/tmp/*|/private/tmp|/private/tmp/*)
            return 1
            ;;
    esac
    return 0
}

write_if_changed() {
    local target="$1"
    local tmp="$2"

    if [[ -f "$target" ]] && cmp -s "$target" "$tmp"; then
        rm -f "$tmp"
        return 1
    fi

    mkdir -p "$(dirname "$target")"
    mv "$tmp" "$target"
    return 0
}

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
        printf '%s\n' "${HOME}"
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

extract_role_lines() {
    local src="$1"
    local role="$2"

    "$JQ" -rs -r --arg role "$role" '
        def msgtext($payload):
          (($payload.content // [])
            | map(select(.type=="input_text" or .type=="output_text" or .type=="text") | (.text // ""))
            | join("\n")
            | gsub("\r"; "")
          );
        def strip_noise:
          gsub("(?s)# AGENTS\\.md instructions for .*?</INSTRUCTIONS>"; "")
          | gsub("(?s)<environment_context>.*?</environment_context>"; "")
          | gsub("(?s)<permissions instructions>.*?</permissions instructions>"; "")
          | gsub("(?s)<app-context>.*?</app-context>"; "")
          | gsub("(?s)<collaboration_mode>.*?</collaboration_mode>"; "")
          | gsub("(?m)^[ \\t]+$"; "")
          | gsub("\n{3,}"; "\n\n")
          | sub("^\\s+"; "")
          | sub("\\s+$"; "");
        .[]
        | select(.type=="response_item" and .payload.type=="message" and .payload.role==$role)
        | (msgtext(.payload) | strip_noise)
        | select(length > 0)
        | split("\n")[]
        | gsub("^\\s+|\\s+$"; "")
        | select(length > 0)
    ' "$src"
}

collect_unique_lines() {
    local source_file="$1"
    local seen_file="$2"
    local out_file="$3"
    local limit="$4"
    local regex="$5"
    local count="$6"
    local line
    local norm

    while IFS= read -r line; do
        if (( ${#line} > 4096 )); then
            line="${line:0:4096}"
        fi
        norm="$(printf '%s' "$line" \
            | tr '[:upper:]' '[:lower:]' \
            | sed -E 's/[[:space:]]+/ /g; s/^[[:space:]]+//; s/[[:space:]]+$//')"
        if (( ${#norm} > 4096 )); then
            norm="${norm:0:4096}"
        fi
        [[ ${#norm} -lt 8 ]] && continue
        printf '%s' "$norm" | grep -Eiq "$regex" || continue
        if ! grep -Fxq -- "$norm" "$seen_file"; then
            printf '%s\n' "$norm" >> "$seen_file"
            printf '%s\n' "$line" >> "$out_file"
            count=$((count + 1))
            if (( count >= limit )); then
                break
            fi
        fi
    done < "$source_file"

    printf '%s\n' "$count"
}

build_project_state() {
    local now_utc
    local tmp_root
    local project_records_dir
    local active_keys_file
    local latest_project_key=""
    local latest_project_ts=""
    local src
    local rel
    local out
    local marker
    local header
    local session_id
    local session_ts
    local session_cwd
    local project_path
    local project_key
    local projected
    local suppressed
    local suppressed_reason
    local projection_rel
    local project_sessions_file
    local sorted_file
    local project_dir
    local projected_sources_file
    local user_lines_file
    local assistant_lines_file
    local intent_seen_file
    local intent_out_file
    local open_seen_file
    local open_out_file
    local decisions_seen_file
    local decisions_out_file
    local candidate_file
    local src_path
    local latest_projected_src=""
    local intent_count=0
    local open_count=0
    local decision_count=0
    local current_objective=""
    local project_path_value=""
    local intent_json
    local open_json
    local decision_json
    local recent_sessions_json
    local evidence_json
    local summary
    local project_record
    local project_doc_path
    local project_doc_tmp
    local recent_session_lines
    local recent_decision_lines
    local latest_project_started_utc=""

    if [[ ! -d "$SOURCE" ]]; then
        log "Source directory not found; preserving existing project state: $SOURCE"
        return 0
    fi

    now_utc="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
    tmp_root="$(mktemp -d /tmp/codex-chat-state.XXXXXX)"
    project_records_dir="$tmp_root/project_records"
    active_keys_file="$tmp_root/active_project_keys.txt"
    mkdir -p "$project_records_dir" "$PROJECTS_DIR"
    : > "$active_keys_file"

    while IFS= read -r -d '' src; do
        rel="${src#$SOURCE/}"
        out="$(target_for "$src")"
        marker="$(skip_marker_for "$src")"
        projection_rel=""
        projected=false
        suppressed=false
        suppressed_reason=""

        if [[ -f "$out" ]]; then
            projected=true
            projection_rel="${out#$TARGET/}"
        fi
        if [[ -f "$marker" ]]; then
            suppressed=true
            suppressed_reason="$(awk -F= '/^reason=/{print $2; exit}' "$marker" 2>/dev/null || true)"
        fi

        header="$(sed -n '1p' "$src")"
        session_id="$(printf '%s\n' "$header" | "$JQ" -r 'select(.type=="session_meta") | .payload.id // ""' 2>/dev/null || true)"
        session_ts="$(printf '%s\n' "$header" | "$JQ" -r 'select(.type=="session_meta") | .payload.timestamp // ""' 2>/dev/null || true)"
        session_cwd="$(printf '%s\n' "$header" | "$JQ" -r 'select(.type=="session_meta") | .payload.cwd // ""' 2>/dev/null || true)"
        [[ -z "$session_ts" ]] && session_ts="$(stat -f '%Sm' -t '%Y-%m-%dT%H:%M:%SZ' "$src" 2>/dev/null || true)"
        project_path="$(canonical_project_path "$session_cwd")"
        project_key="$(project_key_for_path "$project_path")"
        project_sessions_file="$project_records_dir/$project_key.jsonl"

        project_record="$("$JQ" -nc \
            --arg project_key "$project_key" \
            --arg project_path "$project_path" \
            --arg cwd "$session_cwd" \
            --arg source_rel "$rel" \
            --arg source_abs "$src" \
            --arg projection_rel "$projection_rel" \
            --arg projection_abs "$out" \
            --arg started_utc "$session_ts" \
            --arg session_id "$session_id" \
            --arg suppressed_reason "$suppressed_reason" \
            --argjson projected "$projected" \
            --argjson suppressed "$suppressed" \
            '{
                project_key: $project_key,
                project_path: $project_path,
                cwd: $cwd,
                source_rel: $source_rel,
                source_abs: $source_abs,
                projection_rel: (if $projection_rel == "" then null else $projection_rel end),
                projection_abs: (if $projection_rel == "" then null else $projection_abs end),
                started_utc: $started_utc,
                session_id: (if $session_id == "" then null else $session_id end),
                projected: $projected,
                suppressed: $suppressed,
                suppressed_reason: (if $suppressed_reason == "" then null else $suppressed_reason end)
            }'
        )"

        printf '%s\n' "$project_record" >> "$project_sessions_file"
        printf '%s\n' "$project_key" >> "$active_keys_file"

        if [[ "$projected" == "true" ]] && [[ -n "$session_ts" ]]; then
            if [[ -z "$latest_project_ts" || "$session_ts" > "$latest_project_ts" ]]; then
                latest_project_ts="$session_ts"
                latest_project_key="$project_key"
            fi
        fi
    done < <(find "$SOURCE" -type f -name '*.jsonl' -print0)

    sort -u "$active_keys_file" -o "$active_keys_file"

    while IFS= read -r project_key; do
        [[ -z "$project_key" ]] && continue
        project_sessions_file="$project_records_dir/$project_key.jsonl"
        [[ -f "$project_sessions_file" ]] || continue
        project_dir="$PROJECTS_DIR/$project_key"
        mkdir -p "$project_dir"
        sorted_file="$tmp_root/$project_key.sorted.jsonl"

        "$JQ" -cs 'sort_by(.started_utc // "") | reverse | .[]' "$project_sessions_file" > "$sorted_file"

        "$JQ" -cs --arg last_sync_utc "$now_utc" '
            {
              project_key: (.[0].project_key // ""),
              project_path: (.[0].project_path // ""),
              last_sync_utc: $last_sync_utc,
              total_sessions: length,
              projected_sessions: ([.[] | select(.projected == true)] | length),
              sessions: .
            }
        ' "$sorted_file" > "$project_dir/session_index.json"

        projected_sources_file="$tmp_root/$project_key.projected_sources.txt"
        "$JQ" -cs -r --argjson limit "$RECENT_SESSION_LIMIT" '
            [.[] | select(.projected == true and (.source_abs // "") != "") | .source_abs][0:$limit][]
        ' "$sorted_file" > "$projected_sources_file"

        latest_projected_src="$("$JQ" -cs -r '[.[] | select(.projected == true)][0].source_abs // ""' "$sorted_file")"
        latest_project_started_utc="$("$JQ" -cs -r '[.[] | select(.projected == true)][0].started_utc // ""' "$sorted_file")"
        project_path_value="$("$JQ" -cs -r '.[0].project_path // ""' "$sorted_file")"

        user_lines_file="$tmp_root/$project_key.user_lines.txt"
        assistant_lines_file="$tmp_root/$project_key.assistant_lines.txt"
        intent_seen_file="$tmp_root/$project_key.intent_seen.txt"
        intent_out_file="$tmp_root/$project_key.intent_out.txt"
        open_seen_file="$tmp_root/$project_key.open_seen.txt"
        open_out_file="$tmp_root/$project_key.open_out.txt"
        decisions_seen_file="$tmp_root/$project_key.decisions_seen.txt"
        decisions_out_file="$tmp_root/$project_key.decisions_out.txt"
        : > "$intent_seen_file"
        : > "$intent_out_file"
        : > "$open_seen_file"
        : > "$open_out_file"
        : > "$decisions_seen_file"
        : > "$decisions_out_file"
        intent_count=0
        open_count=0
        decision_count=0

        while IFS= read -r src_path; do
            [[ -z "$src_path" || ! -f "$src_path" ]] && continue
            extract_role_lines "$src_path" "user" > "$user_lines_file"
            intent_count="$(collect_unique_lines \
                "$user_lines_file" \
                "$intent_seen_file" \
                "$intent_out_file" \
                "$INTENT_PIN_LIMIT" \
                '(goal|priority|showstopper|top[- ]level problem|primary focus|intent|i (only )?care|i do not want|i dont want|i want|we want|need to|must|critical|important|preserve|without)' \
                "$intent_count")"
            if (( intent_count >= INTENT_PIN_LIMIT )); then
                break
            fi
        done < "$projected_sources_file"

        if [[ -n "$latest_projected_src" && -f "$latest_projected_src" ]]; then
            extract_role_lines "$latest_projected_src" "user" > "$user_lines_file"
            open_count="$(collect_unique_lines \
                "$user_lines_file" \
                "$open_seen_file" \
                "$open_out_file" \
                "$OPEN_LOOP_LIMIT" \
                '([?]|can you|please|need to|still|remaining|next|follow[- ]?up|todo|should|what about)' \
                "$open_count")"

            extract_role_lines "$latest_projected_src" "assistant" > "$assistant_lines_file"
            decision_count="$(collect_unique_lines \
                "$assistant_lines_file" \
                "$decisions_seen_file" \
                "$decisions_out_file" \
                "$DECISION_LIMIT" \
                '(i will|i can|implemented|updated|changed|configured|added|removed|set up|next)' \
                "$decision_count")"
        fi

        current_objective="$(sed -n '1p' "$intent_out_file" | sed -E 's/^[[:space:]]+//; s/[[:space:]]+$//' || true)"
        if [[ -z "$current_objective" && -n "$latest_projected_src" && -f "$latest_projected_src" ]]; then
            candidate_file="$tmp_root/$project_key.objective_candidates.txt"
            extract_role_lines "$latest_projected_src" "user" > "$candidate_file"
            current_objective="$(sed -n '1p' "$candidate_file" | sed -E 's/^[[:space:]]+//; s/[[:space:]]+$//' || true)"
        fi

        intent_json="$("$JQ" -Rsc 'split("\n") | map(select(length > 0))' < "$intent_out_file")"
        open_json="$("$JQ" -Rsc 'split("\n") | map(select(length > 0))' < "$open_out_file")"
        decision_json="$("$JQ" -Rsc 'split("\n") | map(select(length > 0))' < "$decisions_out_file")"
        recent_sessions_json="$("$JQ" -cs --argjson limit "$RECENT_SESSION_LIMIT" '
            [.[] | select(.projected == true and (.projection_rel // "") != "")
            | {path: .projection_rel, started_utc: (.started_utc // "")}][0:$limit]
        ' "$sorted_file")"
        evidence_json="$("$JQ" -cs '
            [.[] | select(.projected == true and (.projection_rel // "") != "") | .projection_rel][0:8]
        ' "$sorted_file")"

        summary="$("$JQ" -nr \
            --arg project_path "$project_path_value" \
            --arg objective "$current_objective" \
            --argjson intent_pins "$intent_json" \
            --argjson open_loops "$open_json" \
            --argjson recent_sessions "$recent_sessions_json" '
            def section($title; $items):
              [$title] + (
                if ($items | length) == 0
                then ["- (none)"]
                else ($items | map("- " + .))
                end
              );
            (
              [
                "Project: " + $project_path,
                "Current objective: " + (if ($objective|length) > 0 then $objective else "(not yet inferred)" end),
                ""
              ]
              + section("Intent pins:"; ($intent_pins[0:8] // []))
              + [""]
              + section("Open loops:"; ($open_loops[0:8] // []))
              + [""]
              + (
                ["Recent sessions:"] + (
                  if ($recent_sessions | length) == 0
                  then ["- (none)"]
                  else (
                    $recent_sessions[0:5]
                    | map("- " + (.started_utc // "unknown") + " " + (.path // ""))
                  )
                  end
                )
              )
            ) | join("\n")
        ')"

        "$JQ" -n \
            --arg bootstrap_version "v${BOOTSTRAP_VERSION}" \
            --arg project_key "$project_key" \
            --arg project_path "$project_path_value" \
            --arg last_sync_utc "$now_utc" \
            --arg summary "$summary" \
            --arg current_objective "$current_objective" \
            --argjson intent_pins "$intent_json" \
            --argjson open_loops "$open_json" \
            --argjson recent_decisions "$decision_json" \
            --argjson recent_sessions "$recent_sessions_json" \
            --argjson evidence_paths "$evidence_json" \
            '{
                bootstrap_version: $bootstrap_version,
                project_key: $project_key,
                project_path: $project_path,
                last_sync_utc: $last_sync_utc,
                current_objective: (if $current_objective == "" then null else $current_objective end),
                summary: $summary,
                intent_pins: $intent_pins,
                open_loops: $open_loops,
                recent_decisions: $recent_decisions,
                recent_sessions: $recent_sessions,
                evidence_paths: $evidence_paths
            }' > "$project_dir/bootstrap.json"

        "$JQ" -n \
            --arg project_key "$project_key" \
            --arg project_path "$project_path_value" \
            --arg updated_utc "$now_utc" \
            --argjson intent_pins "$intent_json" \
            '{
                project_key: $project_key,
                project_path: $project_path,
                updated_utc: $updated_utc,
                intent_pins: $intent_pins
            }' > "$project_dir/intent_pins.json"

        project_doc_path="$(project_doc_path_for "$project_key")"
        if ! should_materialize_project_doc "$project_path_value"; then
            if [[ -d "$(dirname "$project_doc_path")" ]]; then
                rm -rf "$(dirname "$project_doc_path")"
                QMD_INDEX_CHANGED=1
                "$QMD" --index "$INDEX_NAME" context rm "qmd://$COLLECTION_NAME/projects/$project_key" >/dev/null 2>&1 || true
                log "Removed ephemeral project memory doc: projects/$project_key"
            fi
            continue
        fi
        mkdir -p "$(dirname "$project_doc_path")"
        project_doc_tmp="$(mktemp "${project_doc_path}.tmp.XXXXXX")"
        recent_session_lines="$("$JQ" -cs -r '
            [.[] | select(.projected == true and (.projection_rel // "") != "")
            | "- `" + (.started_utc // "unknown") + "` " + (.projection_rel // "")]
            | .[0:8]
            | if length == 0 then "- (none)" else .[] end
        ' "$sorted_file")"
        if [[ -s "$decisions_out_file" ]]; then
            recent_decision_lines="$(sed 's/^/- /' "$decisions_out_file")"
        else
            recent_decision_lines="- (none)"
        fi

        {
            echo "# Project Memory"
            echo
            echo "- project_key: \`$project_key\`"
            echo "- project_path: \`$project_path_value\`"
            if [[ -n "$latest_project_started_utc" ]]; then
                echo "- latest_session_utc: \`$latest_project_started_utc\`"
            fi
            echo
            echo "## Current Objective"
            echo
            if [[ -n "$current_objective" ]]; then
                printf '%s\n' "$current_objective"
            else
                echo "(not yet inferred)"
            fi
            echo
            echo "## Summary"
            echo
            printf '%s\n' "$summary"
            echo
            echo "## Recent Decisions"
            echo
            printf '%s\n' "$recent_decision_lines"
            echo
            echo "## Evidence Paths"
            echo
            "$JQ" -r '
                if length == 0 then "- (none)" else .[] | "- `" + . + "`" end
            ' < <(printf '%s\n' "$evidence_json")
            echo
            echo "## Source Files"
            echo
            echo "- \`.state/projects/$project_key/bootstrap.json\`"
            echo "- \`.state/projects/$project_key/session_index.json\`"
            echo "- \`.state/projects/$project_key/intent_pins.json\`"
            echo
            echo "## Recent Sessions"
            echo
            printf '%s\n' "$recent_session_lines"
        } > "$project_doc_tmp"

        if write_if_changed "$project_doc_path" "$project_doc_tmp"; then
            QMD_INDEX_CHANGED=1
            log "Updated project memory doc: ${project_doc_path#$TARGET/}"
        fi

    done < "$active_keys_file"

    if [[ -d "$PROJECTS_DIR" ]]; then
        while IFS= read -r -d '' project_dir; do
            project_key="$(basename "$project_dir")"
            if ! grep -Fxq -- "$project_key" "$active_keys_file"; then
                rm -rf "$project_dir"
                log "Removed stale project state: $project_key"
            fi
        done < <(find "$PROJECTS_DIR" -mindepth 1 -maxdepth 1 -type d -print0)
    fi

    if [[ -d "$PROJECT_DOCS_DIR" ]]; then
        while IFS= read -r -d '' project_dir; do
            project_key="$(basename "$project_dir")"
            if ! grep -Fxq -- "$project_key" "$active_keys_file"; then
                rm -rf "$project_dir"
                QMD_INDEX_CHANGED=1
                "$QMD" --index "$INDEX_NAME" context rm "qmd://$COLLECTION_NAME/projects/$project_key" >/dev/null 2>&1 || true
                log "Removed stale project memory doc: projects/$project_key"
            fi
        done < <(find "$PROJECT_DOCS_DIR" -mindepth 1 -maxdepth 1 -type d -print0)
    fi

    if [[ -n "$latest_project_key" ]]; then
        printf '%s\n' "$latest_project_key" > "$LATEST_PROJECT_KEY_FILE"
    else
        rm -f "$LATEST_PROJECT_KEY_FILE"
    fi

    rm -rf "$tmp_root"
    log "Project state refresh complete"
}

sync_project_contexts() {
    local project_dir
    local project_key
    local doc_path
    local project_path_value
    local context_uri
    local context_text

    [[ -d "$PROJECT_DOCS_DIR" ]] || return 0

    while IFS= read -r -d '' project_dir; do
        project_key="$(basename "$project_dir")"
        doc_path="$project_dir/project-memory.md"
        [[ -f "$doc_path" ]] || continue

        project_path_value="$(rg -m1 '^- project_path: `' "$doc_path" | sed -E 's/^- project_path: `//; s/`$//' || true)"
        context_uri="qmd://$COLLECTION_NAME/projects/$project_key"
        context_text="Project memory brief for $project_path_value. Prefer this subtree when reconstructing durable intent, recent decisions, and session history for this repo."
        "$QMD" --index "$INDEX_NAME" context add "$context_uri" "$context_text" >/dev/null
    done < <(find "$PROJECT_DOCS_DIR" -mindepth 1 -maxdepth 1 -type d -print0)
}

needs_refresh() {
    local src="$1"
    local out="$2"
    local marker
    marker="$(skip_marker_for "$src")"
    [[ "${FORCE_REBUILD:-0}" == "1" ]] && return 0
    if [[ -f "$out" ]]; then
        [[ ! -s "$out" ]] && return 0
        grep -Fq -- "- projection_version: \`v${PROJECTION_VERSION}\`" "$out" || return 0
        [[ "$src" -nt "$out" ]] && return 0
        return 1
    fi

    if [[ -f "$marker" ]]; then
        grep -Fq -- "projection_version=v${PROJECTION_VERSION}" "$marker" || return 0
        [[ "$src" -nt "$marker" ]] && return 0
        return 1
    fi

    return 0
}

projection_metrics() {
    local src="$1"
    "$JQ" -rs '
        def msgtext($payload):
          (($payload.content // [])
            | map(select(.type=="input_text" or .type=="output_text" or .type=="text") | (.text // ""))
            | join("\n")
            | gsub("\r"; "")
          );
        def strip_noise:
          gsub("(?s)# AGENTS\\.md instructions for .*?</INSTRUCTIONS>"; "")
          | gsub("(?s)<environment_context>.*?</environment_context>"; "")
          | gsub("(?s)<permissions instructions>.*?</permissions instructions>"; "")
          | gsub("(?s)<app-context>.*?</app-context>"; "")
          | gsub("(?s)<collaboration_mode>.*?</collaboration_mode>"; "")
          | gsub("(?m)^[ \\t]+$"; "")
          | gsub("\n{3,}"; "\n\n")
          | sub("^\\s+"; "")
          | sub("\\s+$"; "");
        [
          (any(.[]; .type=="response_item"
            and .payload.type=="message"
            and .payload.role=="developer"
            and (msgtext(.payload) | contains("You are an awaiter")))),
          ([.[] | select(.type=="response_item" and .payload.type=="message" and .payload.role=="user")
             | (msgtext(.payload) | strip_noise)
             | select(length > 0)
           ] | length),
          ([.[] | select(.type=="response_item" and .payload.type=="message" and .payload.role=="assistant")
             | (msgtext(.payload) | strip_noise)
             | select(length > 0)
           ] | length),
          ([.[] | select(.type=="response_item" and .payload.type=="message" and .payload.role=="user")
             | (msgtext(.payload) | strip_noise)
             | select(length > 0 and (test("^/") | not))
           ] | length),
          ([.[] | select(.type=="event_msg" and .payload.type=="context_compacted")] | length)
        ] | @tsv
    ' "$src"
}

render_chat_projection() {
    local src="$1"
    local out="$2"
    local tmp
    local rel="${src#$SOURCE/}"
    local session_id=""
    local session_ts=""
    local is_awaiter="false"
    local user_count=0
    local assistant_count=0
    local non_slash_user_count=0
    local compaction_count=0

    read -r is_awaiter user_count assistant_count non_slash_user_count compaction_count < <(projection_metrics "$src")

    if [[ "$is_awaiter" == "true" ]]; then
        log "Skipping thread (awaiter utility session): $rel"
        return 13
    fi

    if [[ "$assistant_count" -eq 0 ]]; then
        log "Skipping thread (no assistant reply): $rel"
        return 10
    fi
    if [[ "$non_slash_user_count" -eq 0 ]]; then
        log "Skipping thread (slash-command only): $rel"
        return 11
    fi

    tmp="$(mktemp "${out}.tmp.XXXXXX")"

    session_id="$(sed -n '1p' "$src" | "$JQ" -r 'select(.type=="session_meta") | .payload.id // ""' 2>/dev/null || true)"
    session_ts="$(sed -n '1p' "$src" | "$JQ" -r 'select(.type=="session_meta") | .payload.timestamp // ""' 2>/dev/null || true)"

    {
        echo "# Codex Chat Transcript"
        echo
        echo "- projection_version: \`v$PROJECTION_VERSION\`"
        echo "- source: \`$rel\`"
        [[ -n "$session_id" ]] && echo "- session_id: \`$session_id\`"
        [[ -n "$session_ts" ]] && echo "- started_utc: \`$session_ts\`"
        [[ "$compaction_count" -gt 0 ]] && echo "- context_compactions: \`$compaction_count\`"
        echo
        "$JQ" -r '
            def msgtext:
              ((.payload.content // [])
                | map(select(.type=="input_text" or .type=="output_text" or .type=="text") | (.text // ""))
                | join("\n")
                | gsub("\r"; "")
              );
            def strip_noise:
              gsub("(?s)# AGENTS\\.md instructions for .*?</INSTRUCTIONS>"; "")
              | gsub("(?s)<environment_context>.*?</environment_context>"; "")
              | gsub("(?s)<permissions instructions>.*?</permissions instructions>"; "")
              | gsub("(?s)<app-context>.*?</app-context>"; "")
              | gsub("(?s)<collaboration_mode>.*?</collaboration_mode>"; "")
              | gsub("(?m)^[ \\t]+$"; "")
              | gsub("\n{3,}"; "\n\n")
              | sub("^\\s+"; "")
              | sub("\\s+$"; "");
            if (.type == "response_item")
              and (.payload.type == "message")
              and ((.payload.role == "user") or (.payload.role == "assistant"))
            then
              (msgtext | strip_noise) as $txt
              | if ($txt|length) > 0
                then
                  "## " + (.payload.role | ascii_upcase) + "\n\n" + $txt + "\n"
                else empty end
            elif (.type == "event_msg")
              and (.payload.type == "context_compacted")
            then
              "---\n\n> [CONTEXT COMPACTED] Codex compacted earlier turns at `" + (.timestamp // "unknown") + "`.\n"
            else empty end
        ' "$src"
    } > "$tmp"

    if [[ ! -s "$tmp" ]]; then
        rm -f "$tmp"
        log "Skipping thread (empty projection): $rel"
        return 12
    fi

    if [[ -f "$out" ]] && cmp -s "$out" "$tmp"; then
        rm -f "$tmp"
        log "Projection unchanged: $rel"
        return 14
    fi

    mv "$tmp" "$out"
    clear_skip_marker "$src"
    log "Projected thread: $rel"
}

sync_projection_files() {
    local src
    local out
    local rc
    local scanned=0
    local converted=0
    local skipped=0
    local suppressed=0
    local failed=0

    if [[ ! -d "$SOURCE" ]]; then
        log "Source directory not found; skipping projection scan and stale cleanup: $SOURCE"
    else
        while IFS= read -r -d '' src; do
            scanned=$((scanned + 1))
            out="$(target_for "$src")"
            mkdir -p "$(dirname "$out")"
            if needs_refresh "$src" "$out"; then
                if render_chat_projection "$src" "$out"; then
                    converted=$((converted + 1))
                    QMD_INDEX_CHANGED=1
                else
                    rc=$?
                    if [[ "$rc" -eq 14 ]]; then
                        skipped=$((skipped + 1))
                    elif [[ "$rc" -eq 10 || "$rc" -eq 11 || "$rc" -eq 12 || "$rc" -eq 13 ]]; then
                        suppressed=$((suppressed + 1))
                        if [[ -f "$out" ]]; then
                            rm -f "$out"
                            QMD_INDEX_CHANGED=1
                        fi
                        case "$rc" in
                            10) write_skip_marker "$src" "no_assistant_reply" ;;
                            11) write_skip_marker "$src" "slash_command_only" ;;
                            12) write_skip_marker "$src" "empty_projection" ;;
                            13) write_skip_marker "$src" "awaiter_utility_session" ;;
                        esac
                    else
                        failed=$((failed + 1))
                        if [[ -f "$out" ]]; then
                            rm -f "$out"
                            QMD_INDEX_CHANGED=1
                        fi
                        log "ERROR projection failed: ${src#$SOURCE/}"
                    fi
                fi
            else
                skipped=$((skipped + 1))
            fi
        done < <(find "$SOURCE" -type f -name '*.jsonl' -print0)

        # Remove projections when source jsonl no longer exists.
        while IFS= read -r -d '' out; do
            local rel="${out#$TARGET/}"
            if [[ "$rel" == projects/* ]]; then
                continue
            fi
            local src_candidate="${SOURCE}/${rel%.md}.jsonl"
            if [[ ! -f "$src_candidate" ]]; then
                rm -f "$out"
                QMD_INDEX_CHANGED=1
                log "Removed stale projection: $rel"
            fi
        done < <(find "$TARGET" -type f -name '*.md' -print0)

        # Remove suppression markers when source jsonl no longer exists.
        if [[ -d "$STATE_DIR" ]]; then
            while IFS= read -r -d '' out; do
                local rel="${out#$STATE_DIR/}"
                local src_candidate="${SOURCE}/${rel%.skip}.jsonl"
                if [[ ! -f "$src_candidate" ]]; then
                    rm -f "$out"
                    log "Removed stale suppression marker: $rel"
                fi
            done < <(find "$STATE_DIR" -type f -name '*.skip' -print0)
        fi
    fi

    log "Projection sync complete: scanned=$scanned converted=$converted skipped=$skipped suppressed=$suppressed failed=$failed"
}

update_latest_pointer() {
    local latest
    local rel

    latest="$(find "$TARGET" -type f -name '*.md' ! -path "$PROJECT_DOCS_DIR/*" -print | LC_ALL=C sort | tail -n 1)"
    if [[ -z "$latest" ]]; then
        rm -f "$LATEST_PROJECTION_FILE" "$LATEST_QMD_URI_FILE"
        log "No projection files found; cleared latest pointer"
        return 0
    fi

    rel="${latest#$TARGET/}"
    printf '%s\n' "$latest" > "$LATEST_PROJECTION_FILE"
    printf 'qmd://%s/%s\n' "$COLLECTION_NAME" "$rel" > "$LATEST_QMD_URI_FILE"
    log "Updated latest pointer: $rel"
}

sync_qmd_index() {
    local list_output=""

    list_output="$("$QMD" --index "$INDEX_NAME" collection list 2>/dev/null || true)"
    if printf '%s\n' "$list_output" | grep -Eq "qmd://$COLLECTION_NAME/|(^|[[:space:]])$COLLECTION_NAME([[:space:]]|$)"; then
        "$QMD" --index "$INDEX_NAME" update
        return 0
    fi

    if "$QMD" --index "$INDEX_NAME" collection add "$TARGET" --name "$COLLECTION_NAME" --mask '**/*.md'; then
        return 0
    fi

    list_output="$("$QMD" --index "$INDEX_NAME" collection list 2>/dev/null || true)"
    if printf '%s\n' "$list_output" | grep -Eq "qmd://$COLLECTION_NAME/|(^|[[:space:]])$COLLECTION_NAME([[:space:]]|$)"; then
        log "Collection already exists; running update instead."
        "$QMD" --index "$INDEX_NAME" update
        return 0
    fi

    log "ERROR failed to add or locate collection: $COLLECTION_NAME"
    return 1
}

qmd_collection_exists() {
    local list_output=""
    list_output="$("$QMD" --index "$INDEX_NAME" collection list 2>/dev/null || true)"
    printf '%s\n' "$list_output" | grep -Eq "qmd://$COLLECTION_NAME/|(^|[[:space:]])$COLLECTION_NAME([[:space:]]|$)"
}

run_with_heartbeat() {
    local label="$1"
    shift
    local started_at
    local elapsed=0
    local cmd_pid=0

    started_at="$(date +%s)"
    "$@" &
    cmd_pid=$!

    while kill -0 "$cmd_pid" 2>/dev/null; do
        sleep "$EMBED_HEARTBEAT_SECONDS"
        if ! kill -0 "$cmd_pid" 2>/dev/null; then
            break
        fi
        elapsed=$(( $(date +%s) - started_at ))
        log "$label is still running (${elapsed}s elapsed)"
    done

    wait "$cmd_pid"
}

embed_qmd_index() {
    log "Embedding index: $INDEX_NAME"
    log "qmd can pause for a while after it prints the model name. The install is still working."
    if run_with_heartbeat "Embedding for $INDEX_NAME" "$QMD" --index "$INDEX_NAME" embed; then
        log "Embedding complete: $INDEX_NAME"
    else
        log "ERROR embedding failed for index: $INDEX_NAME"
        return 1
    fi
}

main() {
    require_bin "$QMD" "qmd"
    require_bin "$JQ" "jq"

    if ! mkdir "$LOCK_DIR" 2>/dev/null; then
        log "Sync already running; waiting for current run to finish."
        wait_for_existing_sync
        exit $?
    fi
    trap 'rmdir "$LOCK_DIR"' EXIT

    mkdir -p "$TARGET" "$STATE_DIR" "$PROJECTS_DIR"
    log "Starting codex chat projection sync"
    log "Config: SOURCE=$SOURCE TARGET=$TARGET INDEX=$INDEX_NAME COLLECTION=$COLLECTION_NAME"

    sync_projection_files
    update_latest_pointer
    build_project_state

    if qmd_collection_exists; then
        if [[ "$QMD_INDEX_CHANGED" == "1" ]]; then
            sync_qmd_index
            if ! embed_qmd_index; then
                log "Continuing despite embed failure; next run will retry."
            fi
            sync_project_contexts
        else
            log "No projection changes; skipping qmd update and embed"
            sync_project_contexts
        fi
    else
        log "QMD collection missing; building index from current projections"
        sync_qmd_index
        if ! embed_qmd_index; then
            log "Continuing despite embed failure; next run will retry."
        fi
        sync_project_contexts
    fi

    log "Done"
}

main "$@"

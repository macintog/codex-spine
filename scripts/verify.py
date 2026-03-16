#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "lib"))

from codex_spine import (  # noqa: E402
    BLOCK_END,
    BLOCK_START,
    HOME,
    jcodemunch_mcp_overlay_body,
    LIVE_CONFIG_PATH,
    LIVE_QMD_CHAT_LAUNCH_AGENT_PATH,
    LOCAL_CONFIG_OVERLAY,
    MAINTAINED_COMPONENTS_PATH,
    REQUIRED_CLIS,
    cli_available,
    detect_shell_integration_plan,
    detect_private_reference_hits,
    detect_secret_hits,
    enabled_component_names,
    first_nonempty_line,
    managed_links,
    render_config_text,
    render_launch_agent_text,
    runtime_env,
    shell_source_targets,
    text_file_paths,
    validate_public_doc_surface,
)
from component_manager import component_requirement, component_status, resolve_components, validate_maintenance_manifest  # noqa: E402


def fail(errors: list[str]) -> int:
    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)
    return 1


VERIFIER_HARD_FAILURE_CATEGORIES = {
    "behavior-contract": "Concrete runtime, bootstrap, memory, install, or QA behavior.",
    "boundary-and-leak-check": "Secrets, private references, scope leaks, or forbidden internal/public boundary crossings.",
    "shipped-surface-check": "Required shipped docs, files, manifests, and aliases.",
    "stable-routing-anchor": "Stable startup or tooling-routing anchors.",
}
VERIFIER_ADVISORY_CATEGORIES = {
    "advisory-style-or-wording": "Non-blocking wording or style observations.",
    "advisory-operational": "Non-blocking local checkout or operator-state observations.",
}


def tag_verifier_messages(category: str, messages: list[str]) -> list[str]:
    return [f"[{category}] {message}" for message in messages]


CONTRIBUTION_HEDGE_PHRASES = (
    "if installed",
    "if available",
    "if the skill applies",
)
CONTRIBUTION_TOOLING_ANCHORS = (
    "codex-gitea-pr.sh",
    "codex-gitea-push.sh",
    "search_symbols",
    "get_symbol",
)
PUBLIC_ALWAYS_LOADED_DOC_WORD_LIMITS = {
    REPO_ROOT / "codex/AGENTS.md": 360,
}


def word_count(text: str) -> int:
    return len(text.split())


def project_key_for_path(project_path: Path) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", project_path.name.lower()).strip("-") or "project"
    digest = hashlib.sha1(str(project_path).encode("utf-8")).hexdigest()[:12]
    return f"{slug}-{digest}"


def validate_memory_scope_isolation() -> list[str]:
    errors: list[str] = []
    foreign_project_path = "/tmp/foreign-repo"
    foreign_project_key = "foreign-repo-123456789abc"

    with tempfile.TemporaryDirectory() as tmp_dir:
        home = Path(tmp_dir)
        current_repo = (home / "current-repo").resolve()
        current_repo.mkdir(parents=True, exist_ok=True)

        state_root = home / ".cache/qmd/codex_chat/.state"
        foreign_bootstrap = state_root / "projects" / foreign_project_key / "bootstrap.json"
        foreign_bootstrap.parent.mkdir(parents=True, exist_ok=True)
        foreign_bootstrap.write_text(
            json.dumps(
                {
                    "project_key": foreign_project_key,
                    "project_path": foreign_project_path,
                    "last_sync_utc": "2026-03-08T22:00:00Z",
                    "summary": f"Project: {foreign_project_path}\nProject frame: leaked foreign project",
                }
            ),
            encoding="utf-8",
        )
        (state_root / "latest_project_key.txt").write_text(f"{foreign_project_key}\n", encoding="utf-8")

        request = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "bootstrap_context",
                    "arguments": {
                        "cwd": str(current_repo),
                        "refresh_if_stale": False,
                    },
                },
            }
        )
        env = runtime_env()
        env["HOME"] = str(home)
        env["CODEX_CHAT_QMD_LOCK_DIR"] = str(home / "codex-chat-qmd-sync.lock")
        env["CODEX_CHAT_QMD_LOCK_DIR"] = str(home / "codex-chat-qmd-sync.lock")
        result = subprocess.run(
            ["node", str(REPO_ROOT / "bin" / "codex-memory-mcp")],
            input=f"{request}\n",
            check=False,
            capture_output=True,
            text=True,
            env=env,
            timeout=30,
        )
        if result.returncode != 0:
            detail = first_nonempty_line(result.stderr, result.stdout) or f"exit {result.returncode}"
            errors.append(f"memory scope-isolation check failed to run: {detail}")
        else:
            try:
                payload = json.loads(result.stdout.strip())
                summary = payload["result"]["structuredContent"]["summary"]
            except (json.JSONDecodeError, KeyError, TypeError) as exc:
                errors.append(f"memory scope-isolation check returned unparseable output: {exc}")
            else:
                current_repo_text = str(current_repo)
                if current_repo_text not in summary:
                    errors.append("memory scope-isolation check did not return the current project path")
                if "Project frame: Use the current working directory and its durable local docs as the continuity anchor." not in summary:
                    errors.append("memory scope-isolation check did not return the cold-start project frame")
                if foreign_project_path in summary or "leaked foreign project" in summary:
                    errors.append("memory scope-isolation check leaked foreign project context")

    with tempfile.TemporaryDirectory() as tmp_dir:
        home = Path(tmp_dir)
        current_repo = (home / "current-repo").resolve()
        current_repo.mkdir(parents=True, exist_ok=True)

        local_bin = home / ".local/bin"
        local_bin.mkdir(parents=True, exist_ok=True)
        qmd_wrapper = local_bin / "qmd-codex"
        qmd_wrapper.write_text("#!/bin/sh\necho stub-qmd \"$@\"\n", encoding="utf-8")
        qmd_wrapper.chmod(0o755)

        state_root = home / ".cache/qmd/codex_chat/.state"
        state_root.mkdir(parents=True, exist_ok=True)
        (state_root / "latest_projection.txt").write_text("/tmp/foreign.md\n", encoding="utf-8")

        env = runtime_env()
        env["HOME"] = str(home)
        result = subprocess.run(
            [str(REPO_ROOT / "bin" / "qmd-memory-latest.sh"), str(current_repo)],
            check=False,
            capture_output=True,
            text=True,
            env=env,
            timeout=30,
        )
        stderr = result.stderr
        if result.returncode == 0:
            errors.append("qmd-memory-latest scope-isolation check unexpectedly succeeded without current project memory")
        if str(current_repo) not in stderr:
            errors.append("qmd-memory-latest scope-isolation check did not name the current project")
        if foreign_project_path in stderr or "/tmp/foreign.md" in stderr:
            errors.append("qmd-memory-latest scope-isolation check leaked foreign latest-pointer state")

    with tempfile.TemporaryDirectory() as tmp_dir:
        home = Path(tmp_dir)
        project_key = "current-repo-123456789abc"
        state_root = home / ".cache/qmd/codex_chat/.state"
        project_state_root = state_root / "projects" / project_key
        project_state_root.mkdir(parents=True, exist_ok=True)
        (state_root / "latest_project_key.txt").write_text(f"{project_key}\n", encoding="utf-8")
        (project_state_root / "bootstrap.json").write_text(
            json.dumps(
                {
                    "project_key": project_key,
                    "project_path": "/tmp/current-repo",
                    "last_sync_utc": "2026-03-09T22:00:00Z",
                    "project_frame": "Verify durable context.",
                    "summary": "Project: /tmp/current-repo\nProject frame: Verify durable context.\n",
                    "intent_pins": ["Verify the public memory surface."],
                    "open_loops": [],
                    "recent_sessions": [],
                    "evidence_paths": [],
                }
            ),
            encoding="utf-8",
        )

        local_bin = home / ".local/bin"
        local_bin.mkdir(parents=True, exist_ok=True)
        qmd_wrapper = local_bin / "qmd-codex"
        qmd_wrapper.write_text(
            "\n".join(
                [
                    "#!/bin/sh",
                    "cmd=\"$1\"",
                    "shift || true",
                    "case \"$cmd\" in",
                    "  status)",
                    "    cat <<'EOF'",
                    "Index: /tmp/codex_chat.sqlite",
                    "  codex-chat (qmd://codex-chat)",
                    "  Total: 1",
                    "  Vectors: 1",
                    "  Contexts: 1",
                    "EOF",
                    "    ;;",
                    "  get)",
                    f"    if [ \"$1\" = \"qmd://codex-chat/projects/{project_key}\" ]; then",
                    "      cat <<'EOF'",
                    "# Project Memory",
                    "",
                    "Project frame: Verify durable context.",
                    "EOF",
                    "    else",
                    "      printf 'GET:%s\\n' \"$1\"",
                    "    fi",
                    "    ;;",
                    "  query|search|vsearch)",
                    f"    printf '[{{\"file\":\"qmd://codex-chat/projects/{project_key}\",\"score\":0.9}}]'",
                    "    ;;",
                    "  multi-get)",
                    "    cat <<'EOF'",
                    "# Project Memory",
                    "",
                    "Project frame: Verify durable context.",
                    "EOF",
                    "    ;;",
                    "  *)",
                    "    echo \"unsupported command: $cmd\" >&2",
                    "    exit 1",
                    "    ;;",
                    "esac",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        qmd_wrapper.chmod(0o755)

        env = runtime_env()
        env["HOME"] = str(home)

        def rpc(method: str, params: dict | None = None) -> dict:
            request = json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": method,
                    "params": params or {},
                }
            )
            result = subprocess.run(
                ["node", str(REPO_ROOT / "bin" / "codex-memory-mcp")],
                input=f"{request}\n",
                check=False,
                capture_output=True,
                text=True,
                env=env,
                timeout=30,
            )
            if result.returncode != 0:
                detail = first_nonempty_line(result.stderr, result.stdout) or f"exit {result.returncode}"
                raise RuntimeError(detail)
            return json.loads(result.stdout.strip())

        try:
            tools_list = rpc("tools/list")
        except Exception as exc:
            errors.append(f"memory tools/list failed: {exc}")
        else:
            tools = tools_list.get("result", {}).get("tools", [])
            tool_names = {tool.get("name") for tool in tools if isinstance(tool, dict)}
            required_tool_names = {
                "bootstrap_context",
                "status",
                "deep_search",
                "search",
                "vector_search",
                "get",
                "multi_get",
            }
            missing_tools = sorted(required_tool_names - tool_names)
            if missing_tools:
                errors.append(f"memory tools/list is missing expected tools: {', '.join(missing_tools)}")

        try:
            resources_list = rpc("resources/list")
        except Exception as exc:
            errors.append(f"memory resources/list failed: {exc}")
        else:
            resources = resources_list.get("result", {}).get("resources", [])
            if not isinstance(resources, list):
                errors.append("memory resources/list did not return a resources list")
            else:
                encoded = json.dumps(resources)
                if "bootstrap_context" not in encoded:
                    errors.append("memory resources/list did not advertise bootstrap_context")
                if f"qmd://codex-chat/projects/{project_key}" not in encoded:
                    errors.append("memory resources/list did not advertise the project qmd:// context")

        try:
            bootstrap_read = rpc("resources/read", {"uri": f"memory://projects/{project_key}/bootstrap"})
        except Exception as exc:
            errors.append(f"memory resources/read failed for bootstrap summary: {exc}")
        else:
            try:
                bootstrap_text = bootstrap_read["result"]["contents"][0]["text"]
            except (KeyError, IndexError, TypeError) as exc:
                errors.append(f"memory resources/read returned unparseable bootstrap output: {exc}")
            else:
                if "Project frame: Verify durable context." not in bootstrap_text:
                    errors.append("memory resources/read did not return bootstrap content")

        try:
            project_read = rpc("resources/read", {"uri": f"qmd://codex-chat/projects/{project_key}"})
        except Exception as exc:
            errors.append(f"memory resources/read failed for project qmd:// context: {exc}")
        else:
            try:
                project_text = project_read["result"]["contents"][0]["text"]
            except (KeyError, IndexError, TypeError) as exc:
                errors.append(f"memory resources/read returned unparseable project-memory output: {exc}")
            else:
                if "Project frame: Verify durable context." not in project_text:
                    errors.append("memory resources/read did not return project qmd:// content")

        try:
            search_call = rpc(
                "tools/call",
                {
                    "name": "search",
                    "arguments": {
                        "query": "verify resources",
                        "collection": "codex_chat",
                        "intent": "confirm current memory surface",
                    },
                },
            )
        except Exception as exc:
            errors.append(f"memory search tool call failed: {exc}")
        else:
            try:
                search_results = search_call["result"]["structuredContent"]["results"]
            except (KeyError, TypeError) as exc:
                errors.append(f"memory search tool call returned unparseable output: {exc}")
            else:
                if not isinstance(search_results, list) or not search_results:
                    errors.append("memory search tool call returned no results")
                elif search_results[0].get("file") != f"qmd://codex-chat/projects/{project_key}":
                    errors.append("memory search tool call did not use the qmd:// project context")

        try:
            get_call = rpc(
                "tools/call",
                {
                    "name": "get",
                    "arguments": {"file": f"qmd://codex-chat/projects/{project_key}"},
                },
            )
        except Exception as exc:
            errors.append(f"memory get tool call failed: {exc}")
        else:
            try:
                get_text = get_call["result"]["structuredContent"]["text"]
            except (KeyError, TypeError) as exc:
                errors.append(f"memory get tool call returned unparseable output: {exc}")
            else:
                if "Project frame: Verify durable context." not in get_text:
                    errors.append("memory get tool call did not return project content")

        try:
            rejected_get = rpc(
                "tools/call",
                {
                    "name": "get",
                    "arguments": {"file": "/tmp/foreign.md"},
                },
            )
        except Exception as exc:
            errors.append(f"memory get local-path rejection check failed to run: {exc}")
        else:
            if not rejected_get.get("result", {}).get("isError"):
                errors.append("memory get tool unexpectedly accepted a raw local path")

        try:
            rejected_multi_get = rpc(
                "tools/call",
                {
                    "name": "multi_get",
                    "arguments": {"pattern": "/tmp/*.md"},
                },
            )
        except Exception as exc:
            errors.append(f"memory multi_get local-pattern rejection check failed to run: {exc}")
        else:
            if not rejected_multi_get.get("result", {}).get("isError"):
                errors.append("memory multi_get tool unexpectedly accepted a raw local pattern")

        try:
            missing_read = rpc("resources/read", {"uri": "memory://projects/missing-project/bootstrap"})
        except Exception as exc:
            errors.append(f"memory resources/read missing-project check failed to run: {exc}")
        else:
            if not missing_read.get("result", {}).get("isError"):
                errors.append("memory resources/read missing-project check unexpectedly succeeded")

    return errors


def validate_memory_bootstrap_contract() -> list[str]:
    errors: list[str] = []

    with tempfile.TemporaryDirectory() as tmp_dir:
        home = Path(tmp_dir)
        current_repo = (home / "current-repo").resolve()
        current_repo.mkdir(parents=True, exist_ok=True)
        (current_repo / "README.md").write_text(
            "# Example Repo\n\nExample durable context for the current working directory.\n",
            encoding="utf-8",
        )

        local_bin = home / ".local/bin"
        local_bin.mkdir(parents=True, exist_ok=True)
        qmd_wrapper = local_bin / "qmd-codex"
        qmd_wrapper.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        qmd_wrapper.chmod(0o755)
        sync_wrapper = local_bin / "sync-codex-chat-qmd.sh"
        sync_wrapper.write_text(
            f"#!/bin/sh\nexec {shlex.quote(str(REPO_ROOT / 'bin' / 'sync-codex-chat-qmd.sh'))} \"$@\"\n",
            encoding="utf-8",
        )
        sync_wrapper.chmod(0o755)

        sessions_dir = home / ".codex/sessions/2026/03/09"
        sessions_dir.mkdir(parents=True, exist_ok=True)
        session_path = sessions_dir / "rollout-memory-contract.jsonl"
        session_lines = [
            {
                "type": "session_meta",
                "payload": {
                    "id": "memory-contract-test",
                    "timestamp": "2026-03-09T22:00:00Z",
                    "cwd": str(current_repo),
                },
            },
            {
                "timestamp": "2026-03-09T22:00:01Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": "<skill>\n<name>upstream-contributor</name>\nUse this skill for git-hosted work that may be offered back to upstream.\n</skill>",
                        }
                    ],
                },
            },
            {
                "timestamp": "2026-03-09T22:00:02Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": "# Generic Memory Contract Reset\n\n## Summary\n- Redefine memory as continuity, not a task selector.\n- Remove automatic prose recap of prior task work.\n",
                        }
                    ],
                },
            },
            {
                "timestamp": "2026-03-09T22:00:03Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": "Please fix the jcodemunch error next.",
                        }
                    ],
                },
            },
            {
                "timestamp": "2026-03-09T22:00:04Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "assistant",
                    "content": [
                        {
                            "type": "output_text",
                            "text": "I will inspect the current repo and error surface.",
                        }
                    ],
                },
            },
        ]
        session_path.write_text(
            "".join(f"{json.dumps(item)}\n" for item in session_lines),
            encoding="utf-8",
        )

        env = runtime_env()
        env["HOME"] = str(home)
        env["CODEX_CHAT_QMD_LOCK_DIR"] = str(home / "codex-chat-qmd-sync.lock")

        sync_result = subprocess.run(
            [str(REPO_ROOT / "bin" / "sync-codex-chat-qmd.sh"), "--state-only", "--project-path", str(current_repo)],
            check=False,
            capture_output=True,
            text=True,
            env=env,
            timeout=30,
        )
        if sync_result.returncode != 0:
            detail = first_nonempty_line(sync_result.stderr, sync_result.stdout) or f"exit {sync_result.returncode}"
            return [f"memory bootstrap contract sync failed: {detail}"]

        canonical_current_repo = Path(os.path.realpath(current_repo))
        project_key = project_key_for_path(canonical_current_repo)
        bootstrap_path = home / ".cache/qmd/codex_chat/.state/projects" / project_key / "bootstrap.json"
        project_doc_path = home / ".cache/qmd/codex_chat/projects" / project_key / "project-memory.md"

        def rpc(method: str, params: dict | None = None) -> dict:
            request = json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": method,
                    "params": params or {},
                }
            )
            result = subprocess.run(
                ["node", str(REPO_ROOT / "bin" / "codex-memory-mcp")],
                input=f"{request}\n",
                check=False,
                capture_output=True,
                text=True,
                env=env,
                timeout=30,
            )
            if result.returncode != 0:
                detail = first_nonempty_line(result.stderr, result.stdout) or f"exit {result.returncode}"
                raise RuntimeError(detail)
            return json.loads(result.stdout.strip())

        try:
            bootstrap_call = rpc(
                "tools/call",
                {
                    "name": "bootstrap_context",
                    "arguments": {
                        "cwd": str(current_repo),
                        "refresh_if_stale": True,
                    },
                },
            )
        except Exception as exc:
            errors.append(f"memory bootstrap contract RPC failed: {exc}")
            return errors

        structured = bootstrap_call.get("result", {}).get("structuredContent", {})
        try:
            response_text = bootstrap_call["result"]["content"][0]["text"]
        except (KeyError, IndexError, TypeError):
            response_text = ""
        if "current_objective" in structured:
            errors.append("memory bootstrap_context structured output still exposes current_objective")
        if structured.get("project_key") != project_key:
            errors.append("memory bootstrap_context structured output returned the wrong project key")
        if structured.get("project_path") != str(canonical_current_repo):
            errors.append("memory bootstrap_context structured output returned the wrong canonical project path")
        if structured.get("project_frame") != "Example durable context for the current working directory.":
            errors.append("memory bootstrap_context structured output did not preserve project_frame")
        recent_sessions = structured.get("recent_sessions")
        if not isinstance(recent_sessions, list):
            errors.append("memory bootstrap_context structured output returned invalid recent_sessions")
        else:
            for item in recent_sessions:
                if not isinstance(item, dict) or not str(item.get("path", "")).startswith("qmd://codex-chat/"):
                    errors.append("memory bootstrap_context recent_sessions must use qmd://codex-chat/... paths")
                    break
        evidence_paths = structured.get("evidence_paths")
        if not isinstance(evidence_paths, list):
            errors.append("memory bootstrap_context structured output returned invalid evidence_paths")
        else:
            for item in evidence_paths:
                if not isinstance(item, str) or not item.startswith("qmd://codex-chat/"):
                    errors.append("memory bootstrap_context evidence_paths must use qmd://codex-chat/... paths")
                    break
        if "Current objective:" in response_text:
            errors.append("memory bootstrap_context text response still uses Current objective")
        for required_text in ("Project frame:", "Durable constraints:", "Historical open loops:", "Recent sessions:"):
            if required_text not in response_text:
                errors.append(f"memory bootstrap_context text response is missing section: {required_text}")
        for forbidden_text in (
            "Use this skill for git-hosted work",
            "Generic Memory Contract Reset",
            "Please fix the jcodemunch error next.",
        ):
            if forbidden_text in response_text:
                errors.append(f"memory bootstrap_context text response leaked non-durable task text: {forbidden_text}")

        if not bootstrap_path.exists():
            errors.append(f"memory bootstrap contract fixture did not produce bootstrap state: {bootstrap_path}")
        else:
            bootstrap = json.loads(bootstrap_path.read_text(encoding="utf-8"))
            summary = str(bootstrap.get("summary", ""))
            project_frame = str(bootstrap.get("project_frame", ""))
            joined_constraints = "\n".join(bootstrap.get("intent_pins", []))
            joined_loops = "\n".join(bootstrap.get("open_loops", []))

            if bootstrap.get("project_path") != str(canonical_current_repo):
                errors.append("memory bootstrap contract fixture recorded the wrong canonical project path")
            if "current_objective" in bootstrap:
                errors.append("memory bootstrap contract fixture still emitted current_objective in bootstrap state")
            if project_frame != "Example durable context for the current working directory.":
                errors.append("memory bootstrap contract fixture did not prefer durable local docs for project_frame")
            for required_text in ("Project frame:", "Durable constraints:", "Historical open loops:", "Recent sessions:"):
                if required_text not in summary:
                    errors.append(f"memory bootstrap contract summary is missing section: {required_text}")
            if "Current objective:" in summary:
                errors.append("memory bootstrap contract summary still uses Current objective")
            for forbidden_text in (
                "Use this skill for git-hosted work",
                "Generic Memory Contract Reset",
                "Please fix the jcodemunch error next.",
            ):
                if forbidden_text in summary or forbidden_text in project_frame or forbidden_text in joined_constraints or forbidden_text in joined_loops:
                    errors.append(f"memory bootstrap contract leaked non-durable task text: {forbidden_text}")

        if not project_doc_path.exists():
            errors.append(f"memory bootstrap contract fixture did not produce a project memory doc: {project_doc_path}")
        else:
            project_doc = project_doc_path.read_text(encoding="utf-8")
            if "Current objective" in project_doc:
                errors.append("project memory doc still frames context as a current objective")
            for required_text in ("## Project Frame", "## Historical Decisions"):
                if required_text not in project_doc:
                    errors.append(f"project memory doc is missing section: {required_text}")

    return errors


def validate_public_agents_policy_texts(
    agents_text: str, tooling_text: str, *, agents_path: Path, tooling_path: Path
) -> list[str]:
    agents_required_anchors = [
        ("repo entrypoint routing", "README.md"),
        ("tooling guide routing", "codex/TOOLING.md"),
        ("memory bootstrap trigger", "memory.bootstrap_context"),
        ("indexed code navigation trigger", "jcodemunch"),
    ]
    tooling_required_anchors = [
        "## Continuity and Memory",
        "direct memory retrieval",
        "memory.bootstrap_context",
        "qmd-memory-latest.sh",
        "## Code Navigation",
        "jcodemunch",
        "search_symbols",
        "get_symbol",
        "## GitHub Work",
    ]
    errors: list[str] = []
    for label, anchor in agents_required_anchors:
        if anchor not in agents_text:
            errors.append(f"public Codex policy is missing required routing anchor: {agents_path}: {label}")
    for anchor in tooling_required_anchors:
        if anchor not in tooling_text:
            errors.append(f"public Codex tooling guide is missing required routing anchor: {tooling_path}: {anchor}")
    if not any(anchor in tooling_text for anchor in ("`search`", "`deep_search`", "`vector_search`", "`get`", "`multi_get`")):
        errors.append(f"public Codex tooling guide is missing direct memory retrieval tool routing: {tooling_path}")
    lowered_agents = agents_text.lower()
    lowered_tooling = tooling_text.lower()
    for phrase in CONTRIBUTION_HEDGE_PHRASES:
        if phrase in lowered_agents:
            errors.append(f"public Codex policy still contains hedge language: {agents_path}: {phrase}")
        if phrase in lowered_tooling:
            errors.append(f"public Codex tooling guide still contains hedge language: {tooling_path}: {phrase}")
    for forbidden in ("upstream-contributor", "project-continuity", "github-contributor", "project-spine", "skills/"):
        if forbidden in agents_text:
            errors.append(f"public Codex policy references a non-shipped skill surface: {agents_path}: {forbidden}")
        if forbidden in tooling_text:
            errors.append(f"public Codex tooling guide references a non-shipped skill surface: {tooling_path}: {forbidden}")
    for forbidden_phrase in ("qmd_codex", "vsearch", "multi-get"):
        if forbidden_phrase in tooling_text:
            errors.append(
                f"public Codex tooling guide still references deprecated direct qmd_codex guidance: {tooling_path}: {forbidden_phrase}"
            )
    return errors


def validate_public_contribution_guidance_boundaries() -> list[str]:
    errors: list[str] = []
    agents_text = (REPO_ROOT / "codex/AGENTS.md").read_text(encoding="utf-8")

    for anchor in CONTRIBUTION_TOOLING_ANCHORS:
        if anchor in agents_text:
            errors.append(f"public startup guidance still carries tooling-lane detail: {REPO_ROOT / 'codex/AGENTS.md'}: {anchor}")

    return errors


def validate_public_contribution_guidance_size_budgets() -> list[str]:
    warnings: list[str] = []

    for path, limit in PUBLIC_ALWAYS_LOADED_DOC_WORD_LIMITS.items():
        words = word_count(path.read_text(encoding="utf-8"))
        if words > limit:
            warnings.append(f"always-loaded public guidance exceeds its advisory word budget: {path}: {words}>{limit}")

    return warnings


def validate_public_skill_surface_absence() -> list[str]:
    errors: list[str] = []
    skills_root = REPO_ROOT / "skills"
    if skills_root.exists():
        remaining_paths = sorted(
            path for path in skills_root.rglob("*") if path.name != ".DS_Store"
        )
        if remaining_paths:
            errors.append(f"public repo still ships skill content: {remaining_paths[0]}")

    for path in (
        REPO_ROOT / "README.md",
        REPO_ROOT / "ARCHITECTURE.md",
        REPO_ROOT / "SECURITY.md",
        REPO_ROOT / "codex/AGENTS.md",
        REPO_ROOT / "codex/TOOLING.md",
    ):
        text = path.read_text(encoding="utf-8")
        for forbidden in ("skills/github-contributor", "skills/project-spine", "~/.codex/skills", "github-contributor", "project-spine"):
            if forbidden in text:
                errors.append(f"public doc still references a removed skill surface: {path}: {forbidden}")

    return errors


def validate_public_agents_policy() -> list[str]:
    agents_path = REPO_ROOT / "codex/AGENTS.md"
    tooling_path = REPO_ROOT / "codex/TOOLING.md"
    try:
        agents_text = agents_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return [f"missing Codex policy file: {agents_path}"]
    try:
        tooling_text = tooling_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return [f"missing Codex tooling guide: {tooling_path}"]

    return validate_public_agents_policy_texts(
        agents_text,
        tooling_text,
        agents_path=agents_path,
        tooling_path=tooling_path,
    )


def run_public_agents_policy_fixture() -> list[str]:
    errors: list[str] = []

    paraphrased_agents = """# Fixture Codex Policy

- Start with README.md for human-facing orientation and reach for codex/TOOLING.md only when the task enters a deeper operational lane.
- On first turn, materially new requests, repo changes, prior-thread references, or context drift, call memory.bootstrap_context before broader doc reloads.
- When prior wording matters, use the memory lane in codex/TOOLING.md instead of guessing from recap.
- When code understanding would otherwise require broad file scanning, use the jcodemunch lane in codex/TOOLING.md.
"""
    paraphrased_tooling = """# Fixture Tooling Guide

## Continuity and Memory

- Start with memory.bootstrap_context, and use direct memory retrieval with `search`, `deep_search`, `vector_search`, `get`, and `multi_get` when prior wording matters.
- If bootstrap fails, fall back to qmd-memory-latest.sh.

## Code Navigation

- Use jcodemunch for indexed code navigation.
- Start with search_symbols and then get_symbol for precise symbol reads.

## GitHub Work

- Use the GitHub-facing contribution lane when the task enters hosted review or upstream prep.
"""
    fixture_agents_path = Path("/tmp/fixture-codex-AGENTS.md")
    fixture_tooling_path = Path("/tmp/fixture-codex-TOOLING.md")

    paraphrase_errors = validate_public_agents_policy_texts(
        paraphrased_agents,
        paraphrased_tooling,
        agents_path=fixture_agents_path,
        tooling_path=fixture_tooling_path,
    )
    if paraphrase_errors:
        errors.append("public policy routing fixture rejected paraphrased but valid routing docs")

    missing_anchor_errors = validate_public_agents_policy_texts(
        paraphrased_agents.replace("codex/TOOLING.md", "the tooling guide"),
        paraphrased_tooling,
        agents_path=fixture_agents_path,
        tooling_path=fixture_tooling_path,
    )
    if not any("routing anchor" in message for message in missing_anchor_errors):
        errors.append("public policy routing fixture did not reject a missing tooling-guide anchor")

    missing_tool_errors = validate_public_agents_policy_texts(
        paraphrased_agents,
        paraphrased_tooling.replace("search_symbols", "symbol search"),
        agents_path=fixture_agents_path,
        tooling_path=fixture_tooling_path,
    )
    if not any("search_symbols" in message for message in missing_tool_errors):
        errors.append("public policy routing fixture did not reject a missing code-navigation anchor")

    return errors


def validate_jcodemunch_overlay_contract() -> list[str]:
    components = {component.name: component for component in resolve_components()}
    component = components.get("jcodemunch-mcp")
    if component is None:
        return ["missing optional component definition: jcodemunch-mcp"]

    if component.backend.get("kind") != "uvx_tool":
        return []

    overlay = jcodemunch_mcp_overlay_body()
    errors: list[str] = []
    expected_command = f'command = "{component.backend["executable"]}"'
    if expected_command not in overlay:
        errors.append("jcodemunch overlay command drifted from the maintenance manifest")

    expected_prefix = ["tool", "run"] if component.backend["executable"] == "uv" else []
    expected_args = json.dumps(
        [
            *expected_prefix,
            "--from",
            component_requirement(component),
            component.backend.get("tool_name", component.backend["package_name"]),
        ]
    )
    if f"args = {expected_args}" not in overlay:
        errors.append("jcodemunch overlay args drifted from the maintenance manifest")

    return errors


def validate_component_cli_surface() -> list[str]:
    errors: list[str] = []
    for script_name in ("component-enable.py", "update.py"):
        script_path = REPO_ROOT / "scripts" / script_name
        result = subprocess.run(
            ["python3", str(script_path), "--help"],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            detail = first_nonempty_line(result.stderr, result.stdout) or f"exit {result.returncode}"
            errors.append(f"component CLI help check failed for {script_path}: {detail}")
            continue
        help_text = result.stdout
        if "--accept-license" in help_text:
            errors.append(f"hidden QA acceptance bypass leaked into the shipped CLI surface: {script_path}")
    for path in text_file_paths(REPO_ROOT):
        if path == Path(__file__).resolve():
            continue
        text = path.read_text(encoding="utf-8")
        if "--accept-license" in text:
            errors.append(f"hidden QA acceptance bypass leaked into the shipped repo surface: {path}")
    return errors


def validate_memory_public_surface() -> list[str]:
    errors: list[str] = []

    mcp_config_path = REPO_ROOT / "codex/config/20-codex-spine-mcps.toml"
    config_text = mcp_config_path.read_text(encoding="utf-8")
    if "[mcp_servers.memory]" not in config_text:
        errors.append(f"public MCP config is missing the memory server: {mcp_config_path}")
    if "[mcp_servers.qmd_codex]" in config_text:
        errors.append(f"deprecated qmd_codex MCP alias still ships publicly: {mcp_config_path}")

    for doc_path in (
        REPO_ROOT / "README.md",
        REPO_ROOT / "ARCHITECTURE.md",
        REPO_ROOT / "codex/AGENTS.md",
    ):
        text = doc_path.read_text(encoding="utf-8")
        if "qmd_codex" in text:
            errors.append(f"public doc still describes qmd_codex as a shipped public surface: {doc_path}")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-only", action="store_true")
    args = parser.parse_args()

    errors: list[str] = []
    warnings: list[str] = []
    errors.extend(tag_verifier_messages("shipped-surface-check", validate_maintenance_manifest(MAINTAINED_COMPONENTS_PATH)))
    errors.extend(tag_verifier_messages("shipped-surface-check", validate_public_doc_surface()))
    errors.extend(tag_verifier_messages("shipped-surface-check", validate_public_skill_surface_absence()))
    errors.extend(tag_verifier_messages("stable-routing-anchor", validate_public_agents_policy()))
    errors.extend(tag_verifier_messages("behavior-contract", validate_public_contribution_guidance_boundaries()))
    warnings.extend(tag_verifier_messages("advisory-style-or-wording", validate_public_contribution_guidance_size_budgets()))
    errors.extend(tag_verifier_messages("boundary-and-leak-check", validate_memory_public_surface()))
    errors.extend(tag_verifier_messages("behavior-contract", validate_memory_scope_isolation()))
    errors.extend(tag_verifier_messages("behavior-contract", validate_memory_bootstrap_contract()))
    errors.extend(tag_verifier_messages("behavior-contract", validate_jcodemunch_overlay_contract()))
    errors.extend(tag_verifier_messages("behavior-contract", validate_component_cli_surface()))
    errors.extend(tag_verifier_messages("behavior-contract", run_public_agents_policy_fixture()))

    for path in text_file_paths(REPO_ROOT):
        if path == LOCAL_CONFIG_OVERLAY:
            continue
        text = path.read_text(encoding="utf-8")
        secret_hits = detect_secret_hits(text)
        if secret_hits:
            errors.append(f"[boundary-and-leak-check] tracked repo file appears to contain a secret: {path}")
        private_hits = detect_private_reference_hits(text, public_surface=True)
        if private_hits:
            errors.append(
                f"[boundary-and-leak-check] tracked repo file still contains private references: {path}: {', '.join(private_hits)}"
            )

    if args.repo_only:
        if errors:
            return fail(errors)
        for warning in warnings:
            print(f"WARNING: {warning}", file=sys.stderr)
        print("verify: ok (repo-only)")
        return 0

    for link in managed_links():
        if not link.live_path.is_symlink():
            errors.append(f"[behavior-contract] managed path is not a symlink: {link.live_path}")
            continue
        if link.live_path.resolve(strict=False) != link.repo_path.resolve():
            errors.append(f"[behavior-contract] managed symlink points to the wrong target: {link.live_path}")

    shell_plan = detect_shell_integration_plan()
    if shell_plan.warning:
        warnings.append(f"[advisory-operational] {shell_plan.warning}")
    for dotfile, fragment in shell_source_targets(shell_plan).items():
        if not dotfile.exists():
            errors.append(f"[behavior-contract] missing shell file: {dotfile}")
            continue
        content = dotfile.read_text(encoding="utf-8")
        if BLOCK_START not in content or BLOCK_END not in content or str(fragment) not in content:
            errors.append(f"[behavior-contract] missing managed source block in {dotfile}")

    if not LIVE_CONFIG_PATH.exists():
        errors.append(f"[behavior-contract] missing generated config: {LIVE_CONFIG_PATH}")
    else:
        live_text = LIVE_CONFIG_PATH.read_text(encoding="utf-8")
        if live_text != render_config_text():
            errors.append(f"[behavior-contract] live config is out of sync with rendered output: {LIVE_CONFIG_PATH}")

    if not LIVE_QMD_CHAT_LAUNCH_AGENT_PATH.exists():
        errors.append(f"[behavior-contract] missing launch agent: {LIVE_QMD_CHAT_LAUNCH_AGENT_PATH}")
    else:
        if LIVE_QMD_CHAT_LAUNCH_AGENT_PATH.read_text(encoding="utf-8") != render_launch_agent_text():
            errors.append(
                f"[behavior-contract] launch agent is out of sync with rendered template: {LIVE_QMD_CHAT_LAUNCH_AGENT_PATH}"
            )

    enabled = enabled_component_names()
    for component in resolve_components():
        status = component_status(component)
        if component.default_enabled and not status["healthy"]:
            errors.append(f"[behavior-contract] default component is unhealthy: {component.name}: {status['detail']}")
        if component.name in enabled and not status["healthy"]:
            errors.append(f"[behavior-contract] enabled optional component is unhealthy: {component.name}: {status['detail']}")

    wrapper_checks = [
        ("qmd-codex wrapper", [str(HOME / ".local/bin/qmd-codex"), "status"]),
        ("memory MCP launcher", [str(REPO_ROOT / "bin" / "codex-memory-health.sh"), str(REPO_ROOT)]),
    ]
    for label, command in wrapper_checks:
        try:
            result = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
                env=runtime_env(),
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            errors.append(f"[behavior-contract] {label} check failed to start: {exc}")
            continue
        if result.returncode != 0:
            detail = first_nonempty_line(result.stderr, result.stdout) or f"exit {result.returncode}"
            errors.append(f"[behavior-contract] {label} is unhealthy: {detail}")

    for cli_name in REQUIRED_CLIS:
        if not cli_available(cli_name):
            errors.append(f"[behavior-contract] required CLI not found: {cli_name}")

    if errors:
        return fail(errors)

    for warning in warnings:
        print(f"WARNING: {warning}", file=sys.stderr)
    print("verify: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

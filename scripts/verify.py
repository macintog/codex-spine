#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "lib"))

from codex_spine import (  # noqa: E402
    BLOCK_END,
    BLOCK_START,
    COMPONENTS_PATH,
    HOME,
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
    enabled_component_record,
    first_nonempty_line,
    managed_links,
    render_config_text,
    render_launch_agent_text,
    runtime_env,
    shell_source_targets,
    text_file_paths,
    validate_components_registry,
    validate_public_doc_surface,
)
from component_manager import component_status, resolve_components, validate_maintenance_manifest  # noqa: E402


def fail(errors: list[str]) -> int:
    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)
    return 1


def validate_memory_scope_isolation() -> list[str]:
    errors: list[str] = []
    foreign_project_path = "/Users/test/Documents/ForeignRepo"
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
                    "summary": f"Project: {foreign_project_path}\nCurrent objective: leaked foreign project",
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
                if "(cold start)" not in summary:
                    errors.append("memory scope-isolation check did not cold-start the current project")
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
        projection_rel = "2026/03/09/rollout-2026-03-09T10-53-40-019cd316-ec35-7e72-8af8-4aac4e555b3b.md"
        projection_abs = home / ".cache/qmd/codex_chat" / projection_rel
        projection_abs.parent.mkdir(parents=True, exist_ok=True)
        projection_abs.write_text("# Session Memory\n\nRemember the rollout note.\n", encoding="utf-8")

        project_memory = home / ".cache/qmd/codex_chat/projects" / project_key / "project-memory.md"
        project_memory.parent.mkdir(parents=True, exist_ok=True)
        project_memory.write_text("# Project Memory\n\nCurrent objective: verify resources.\n", encoding="utf-8")

        state_root = home / ".cache/qmd/codex_chat/.state/projects" / project_key
        state_root.mkdir(parents=True, exist_ok=True)
        (state_root / "session_index.json").write_text(
            json.dumps(
                {
                    "project_key": project_key,
                    "sessions": [
                        {
                            "projected": True,
                            "projection_rel": projection_rel,
                            "projection_abs": str(projection_abs),
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

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
            resources_list = rpc("resources/list")
        except Exception as exc:
            errors.append(f"memory resources/list failed: {exc}")
        else:
            if resources_list.get("error"):
                errors.append(f"memory resources/list returned error: {resources_list['error']}")
            elif not isinstance(resources_list.get("result", {}).get("resources"), list):
                errors.append("memory resources/list did not return a resources list")

        try:
            templates_list = rpc("resources/templates/list")
        except Exception as exc:
            errors.append(f"memory resources/templates/list failed: {exc}")
        else:
            templates = templates_list.get("result", {}).get("resourceTemplates", [])
            if not templates:
                errors.append("memory resources/templates/list returned no templates")
            elif "memory://" not in json.dumps(templates):
                errors.append("memory resources/templates/list did not advertise memory:// support")

        try:
            session_read = rpc("resources/read", {"uri": f"memory://{project_key}/{projection_rel}"})
        except Exception as exc:
            errors.append(f"memory resources/read failed for projected session: {exc}")
        else:
            try:
                session_text = session_read["result"]["contents"][0]["text"]
            except (KeyError, IndexError, TypeError) as exc:
                errors.append(f"memory resources/read returned unparseable projected session output: {exc}")
            else:
                if "Remember the rollout note." not in session_text:
                    errors.append("memory resources/read did not return projected session content")

        try:
            project_read = rpc("resources/read", {"uri": f"memory://{project_key}/project-memory.md"})
        except Exception as exc:
            errors.append(f"memory resources/read failed for project-memory doc: {exc}")
        else:
            try:
                project_text = project_read["result"]["contents"][0]["text"]
            except (KeyError, IndexError, TypeError) as exc:
                errors.append(f"memory resources/read returned unparseable project-memory output: {exc}")
            else:
                if "Current objective: verify resources." not in project_text:
                    errors.append("memory resources/read did not return project-memory content")

        try:
            missing_read = rpc("resources/read", {"uri": f"memory://{project_key}/missing.md"})
        except Exception as exc:
            errors.append(f"memory resources/read missing-path check failed to run: {exc}")
        else:
            if "error" not in missing_read:
                errors.append("memory resources/read missing-path check unexpectedly succeeded")

    return errors


def validate_public_agents_policy() -> list[str]:
    agents_path = REPO_ROOT / "codex/AGENTS.md"
    try:
        text = agents_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return [f"missing Codex policy file: {agents_path}"]

    required_phrases = [
        "memory.bootstrap_context",
        "qmd_codex",
        "max_recent_sessions=3",
    ]
    errors: list[str] = []
    for phrase in required_phrases:
        if phrase not in text:
            errors.append(f"public Codex policy is missing required memory guidance: {agents_path}: {phrase}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-only", action="store_true")
    args = parser.parse_args()

    errors: list[str] = []
    warnings: list[str] = []
    errors.extend(validate_components_registry(COMPONENTS_PATH))
    errors.extend(validate_maintenance_manifest(MAINTAINED_COMPONENTS_PATH))
    errors.extend(validate_public_doc_surface())
    errors.extend(validate_public_agents_policy())
    errors.extend(validate_memory_scope_isolation())

    for path in text_file_paths(REPO_ROOT):
        if path == LOCAL_CONFIG_OVERLAY:
            continue
        text = path.read_text(encoding="utf-8")
        secret_hits = detect_secret_hits(text)
        if secret_hits:
            errors.append(f"tracked repo file appears to contain a secret: {path}")
        private_hits = detect_private_reference_hits(text, public_surface=True)
        if private_hits:
            errors.append(f"tracked repo file still contains private references: {path}: {', '.join(private_hits)}")

    if args.repo_only:
        if errors:
            return fail(errors)
        print("verify: ok (repo-only)")
        return 0

    for link in managed_links():
        if not link.live_path.is_symlink():
            errors.append(f"managed path is not a symlink: {link.live_path}")
            continue
        if link.live_path.resolve(strict=False) != link.repo_path.resolve():
            errors.append(f"managed symlink points to the wrong target: {link.live_path}")

    shell_plan = detect_shell_integration_plan()
    if shell_plan.warning:
        warnings.append(shell_plan.warning)
    for dotfile, fragment in shell_source_targets(shell_plan).items():
        if not dotfile.exists():
            errors.append(f"missing shell file: {dotfile}")
            continue
        content = dotfile.read_text(encoding="utf-8")
        if BLOCK_START not in content or BLOCK_END not in content or str(fragment) not in content:
            errors.append(f"missing managed source block in {dotfile}")

    if not LIVE_CONFIG_PATH.exists():
        errors.append(f"missing generated config: {LIVE_CONFIG_PATH}")
    else:
        live_text = LIVE_CONFIG_PATH.read_text(encoding="utf-8")
        if live_text != render_config_text():
            errors.append(f"live config is out of sync with rendered output: {LIVE_CONFIG_PATH}")

    if not LIVE_QMD_CHAT_LAUNCH_AGENT_PATH.exists():
        errors.append(f"missing launch agent: {LIVE_QMD_CHAT_LAUNCH_AGENT_PATH}")
    else:
        if LIVE_QMD_CHAT_LAUNCH_AGENT_PATH.read_text(encoding="utf-8") != render_launch_agent_text():
            errors.append(f"launch agent is out of sync with rendered template: {LIVE_QMD_CHAT_LAUNCH_AGENT_PATH}")

    enabled = enabled_component_names()
    for component in resolve_components():
        status = component_status(component)
        if component.default_enabled and not status["healthy"]:
            errors.append(f"default component is unhealthy: {component.name}: {status['detail']}")
        if component.name in enabled and not status["healthy"]:
            errors.append(f"enabled optional component is unhealthy: {component.name}: {status['detail']}")
        if component.name in enabled:
            record = enabled_component_record(component.name)
            if component.backend.get("license_source_url") and not record.get("license_sha256"):
                errors.append(f"enabled licensed component is missing license provenance: {component.name}")

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
            errors.append(f"{label} check failed to start: {exc}")
            continue
        if result.returncode != 0:
            detail = first_nonempty_line(result.stderr, result.stdout) or f"exit {result.returncode}"
            errors.append(f"{label} is unhealthy: {detail}")

    for cli_name in REQUIRED_CLIS:
        if not cli_available(cli_name):
            errors.append(f"required CLI not found: {cli_name}")

    if errors:
        return fail(errors)

    for warning in warnings:
        print(f"WARNING: {warning}", file=sys.stderr)
    print("verify: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

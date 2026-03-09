#!/usr/bin/env python3

from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "lib"))

from codex_spine import (  # noqa: E402
    HOME,
    JCODEMUNCH_MCP_BLOCK_END,
    JCODEMUNCH_MCP_BLOCK_START,
    LEGACY_QMD_CHAT_LAUNCH_AGENT_LABELS,
    LEGACY_QMD_CHAT_LAUNCH_AGENT_NAMES,
    LIVE_CONFIG_PATH,
    LIVE_QMD_CHAT_LAUNCH_AGENT_PATH,
    LOCAL_CONFIG_EXAMPLE,
    LOCAL_CONFIG_OVERLAY,
    LOCAL_ENV_EXAMPLE,
    LOCAL_ENV_FILE,
    detect_shell_integration_plan,
    ensure_example_copy,
    ensure_homebrew,
    ensure_symlink,
    enabled_component_names,
    first_nonempty_line,
    install_missing_brew_formulas,
    jcodemunch_mcp_overlay_body,
    managed_links,
    prepare_generated_config_target,
    replace_managed_block,
    render_config_text,
    render_launch_agent_text,
    sanitize_zshenv,
    shell_source_targets,
    upsert_source_block,
    write_generated_config,
    write_managed_launch_agent,
)
from component_manager import (  # noqa: E402
    component_status,
    ensure_license_acknowledged,
    resolve_components,
    update_component,
)


def run_script(script_name: str, *args: str) -> None:
    subprocess.run([str(REPO_ROOT / "scripts" / script_name), *args], check=True)


def run_sync() -> None:
    subprocess.run([str(REPO_ROOT / "bin" / "sync-codex-chat-qmd.sh")], check=True)


def warn(message: str) -> None:
    print(f"WARNING: {message}", file=sys.stderr)


def maybe_enable_jcodemunch(*, non_interactive: bool) -> bool:
    if os.environ.get("CODEX_SPINE_JCODEMUNCH_CHOICE") != "enable":
        return False
    if "jcodemunch-mcp" in enabled_component_names():
        return False

    components = {component.name: component for component in resolve_components()}
    component = components.get("jcodemunch-mcp")
    if component is None:
        raise RuntimeError("missing optional component definition: jcodemunch-mcp")

    print("\nYou chose to include optional jCodeMunch MCP in this install.")
    print("codex-spine will fetch the pinned upstream terms now and ask for explicit acknowledgement before enabling it.")
    print()
    try:
        ensure_license_acknowledged(
            component,
            accept_license=False,
            non_interactive=non_interactive or not sys.stdin.isatty(),
        )
    except RuntimeError as exc:
        warn(str(exc))
        print("Continuing install without optional jCodeMunch MCP.")
        return False
    package_name = component.backend.get("package_name", component.name)
    print(f"{component.name}: installing/updating {package_name}...", flush=True)
    print(f"$ {shlex.join(component_status(component)['action'])}", flush=True)
    for line in update_component(component):
        print(line)
    replace_managed_block(
        LOCAL_CONFIG_OVERLAY,
        JCODEMUNCH_MCP_BLOCK_START,
        JCODEMUNCH_MCP_BLOCK_END,
        jcodemunch_mcp_overlay_body(),
    )
    return True


def run_bootout(args: list[str], *, label: str) -> None:
    result = subprocess.run(
        ["launchctl", "bootout", *args],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return
    detail = first_nonempty_line(result.stderr, result.stdout)
    if result.returncode in {3, 5}:
        return
    if detail and any(text in detail for text in ("No such process", "Input/output error")):
        return
    if detail:
        warn(f"{label} failed: {detail}")


def run_launchctl(args: list[str], *, label: str) -> bool:
    result = subprocess.run(
        ["launchctl", *args],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return True
    detail = first_nonempty_line(result.stderr, result.stdout) or f"exit {result.returncode}"
    warn(
        f"{label} failed: {detail}. The LaunchAgent plist was still written; rerun `make install` from a normal macOS login session to load launchd state."
    )
    return False


def main() -> int:
    try:
        parser = argparse.ArgumentParser()
        parser.add_argument("--non-interactive", action="store_true")
        args = parser.parse_args()
        non_interactive = args.non_interactive or not sys.stdin.isatty()
        shell_plan = detect_shell_integration_plan()

        if shell_plan.warning:
            warn(shell_plan.warning)

        brew_path = ensure_homebrew(non_interactive=non_interactive)
        config_plan = prepare_generated_config_target(LIVE_CONFIG_PATH, non_interactive=non_interactive)
        installed_formulas = install_missing_brew_formulas(
            brew_path,
            non_interactive=non_interactive,
        )
        if installed_formulas:
            print(f"Installed Homebrew packages: {', '.join(installed_formulas)}")

        ensure_example_copy(LOCAL_CONFIG_EXAMPLE, LOCAL_CONFIG_OVERLAY)
        ensure_example_copy(LOCAL_ENV_EXAMPLE, LOCAL_ENV_FILE)

        for path in [
            HOME / ".codex",
            HOME / ".codex/skills",
            HOME / ".local/bin",
            HOME / "Library/LaunchAgents",
        ]:
            path.mkdir(parents=True, exist_ok=True)

        for link in managed_links():
            ensure_symlink(link.live_path, link.repo_path)

        if shell_plan.supported:
            sanitize_zshenv(HOME / ".zshenv")
            for dotfile, fragment in shell_source_targets(shell_plan).items():
                upsert_source_block(dotfile, fragment)

        print("\nNow we'll install or update the core packages codex-spine manages. This can take a while on the first run.", flush=True)
        run_script("update", "--defaults-only", *(["--non-interactive"] if non_interactive else []))
        maybe_enable_jcodemunch(non_interactive=non_interactive)

        rendered = render_config_text()
        write_generated_config(
            LIVE_CONFIG_PATH,
            rendered,
            allow_unmanaged_replace=config_plan.allow_unmanaged_replace,
        )
        if config_plan.adopted_overlay_path is not None:
            print(f"\nImported the existing Codex config into {config_plan.adopted_overlay_path}")
        if config_plan.backup_path is not None:
            print(f"Backed up the previous live Codex config to {config_plan.backup_path}")

        uid = subprocess.run(["id", "-u"], check=True, capture_output=True, text=True).stdout.strip()
        for legacy_name in LEGACY_QMD_CHAT_LAUNCH_AGENT_NAMES:
            legacy_path = HOME / "Library/LaunchAgents" / legacy_name
            run_bootout([f"gui/{uid}", str(legacy_path)], label=f"launchctl bootout {legacy_name}")
            if legacy_path.exists():
                legacy_path.unlink()

        write_managed_launch_agent(LIVE_QMD_CHAT_LAUNCH_AGENT_PATH, render_launch_agent_text())

        # Warm the transcript projection and qmd index directly before loading the
        # LaunchAgent. Otherwise RunAtLoad can steal the first sync and leave
        # bootstrap showing only a lock wait instead of the real work.
        print("\nNow we'll sync your local Codex transcripts from ~/.codex/sessions into the local qmd index. This can take a while the first time.")
        run_sync()

        run_bootout([f"gui/{uid}", str(LIVE_QMD_CHAT_LAUNCH_AGENT_PATH)], label="launchctl bootout codex-spine.qmd-codex-chat plist")
        for legacy_label in LEGACY_QMD_CHAT_LAUNCH_AGENT_LABELS:
            run_bootout([f"gui/{uid}/{legacy_label}"], label=f"launchctl bootout {legacy_label}")
        run_launchctl(
            ["bootstrap", f"gui/{uid}", str(LIVE_QMD_CHAT_LAUNCH_AGENT_PATH)],
            label="launchctl bootstrap",
        )

        run_script("verify")
        if not shell_plan.supported:
            print("Shell integration was skipped because the detected login shell is not zsh.")
            print("Manual follow-up: add `$HOME/.local/bin` to your shell startup and source the repo shell fragments if desired.")
        if os.environ.get("CODEX_SPINE_JCODEMUNCH_CHOICE") is None and "jcodemunch-mcp" not in enabled_component_names():
            print("Optional next step: enable jCodeMunch MCP for indexed code navigation with `./scripts/component-enable jcodemunch-mcp`.")
        print("install: ok")
        return 0
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except subprocess.CalledProcessError as exc:
        print(f"ERROR: command failed with exit status {exc.returncode}: {' '.join(exc.cmd)}", file=sys.stderr)
        print("See output above for details.", file=sys.stderr)
        return exc.returncode or 1


if __name__ == "__main__":
    raise SystemExit(main())

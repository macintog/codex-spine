#!/usr/bin/env python3

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "lib"))

from codex_spine import (  # noqa: E402
    HOME,
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
    first_nonempty_line,
    install_missing_brew_formulas,
    managed_links,
    render_config_text,
    render_launch_agent_text,
    sanitize_zshenv,
    shell_source_targets,
    upsert_source_block,
    write_generated_config,
    write_managed_launch_agent,
)


def run_script(script_name: str, *args: str) -> None:
    subprocess.run([str(REPO_ROOT / "scripts" / script_name), *args], check=True)


def warn(message: str) -> None:
    print(f"WARNING: {message}", file=sys.stderr)


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
        f"{label} failed: {detail}. The LaunchAgent plist was still written; rerun `make bootstrap` from a normal macOS login session to load launchd state."
    )
    return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--non-interactive", action="store_true")
    args = parser.parse_args()
    non_interactive = args.non_interactive or not sys.stdin.isatty()
    shell_plan = detect_shell_integration_plan()

    if shell_plan.warning:
        warn(shell_plan.warning)

    brew_path = ensure_homebrew(non_interactive=non_interactive)
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

    run_script("update", "--defaults-only", *(["--non-interactive"] if non_interactive else []))

    rendered = render_config_text()
    write_generated_config(LIVE_CONFIG_PATH, rendered)

    uid = subprocess.run(["id", "-u"], check=True, capture_output=True, text=True).stdout.strip()
    for legacy_name in LEGACY_QMD_CHAT_LAUNCH_AGENT_NAMES:
        legacy_path = HOME / "Library/LaunchAgents" / legacy_name
        subprocess.run(["launchctl", "bootout", f"gui/{uid}", str(legacy_path)], check=False)
        if legacy_path.exists():
            legacy_path.unlink()

    write_managed_launch_agent(LIVE_QMD_CHAT_LAUNCH_AGENT_PATH, render_launch_agent_text())
    subprocess.run(["launchctl", "bootout", f"gui/{uid}", str(LIVE_QMD_CHAT_LAUNCH_AGENT_PATH)], check=False)
    for legacy_label in LEGACY_QMD_CHAT_LAUNCH_AGENT_LABELS:
        subprocess.run(["launchctl", "bootout", f"gui/{uid}/{legacy_label}"], check=False)
    if run_launchctl(
        ["bootstrap", f"gui/{uid}", str(LIVE_QMD_CHAT_LAUNCH_AGENT_PATH)],
        label="launchctl bootstrap",
    ):
        run_launchctl(
            ["kickstart", "-k", f"gui/{uid}/codex-spine.qmd-codex-chat"],
            label="launchctl kickstart",
        )

    run_script("verify")
    if not shell_plan.supported:
        print("Shell integration was skipped because the detected login shell is not zsh.")
        print("Manual follow-up: add `$HOME/.local/bin` to your shell startup and source the repo shell fragments if desired.")
    print("bootstrap: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

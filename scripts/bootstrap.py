#!/usr/bin/env python3

from __future__ import annotations

import argparse
import os
import select
import shlex
import subprocess
import sys
import time
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
    _run_live_with_heartbeat,
    component_status,
    ensure_license_acknowledged,
    fetch_license_terms,
    record_license_acknowledgement,
    resolve_components,
    update_component,
)
from install_tui import Step, open_tui  # noqa: E402


def run_script(
    script_name: str,
    *args: str,
    ui=None,
    heartbeat_message: str | None = None,
    heartbeat_interval: float = 5.0,
) -> None:
    command = [str(REPO_ROOT / "scripts" / script_name), *args]
    if ui is not None:
        ui.run_command(
            command,
            heartbeat_message=heartbeat_message,
            heartbeat_interval=heartbeat_interval,
        )
        return
    subprocess.run(command, check=True)


def _drain_command_output(process: subprocess.Popen[str], sink) -> None:
    if process.stdout is None:
        return
    while True:
        ready, _, _ = select.select([process.stdout], [], [], 0)
        if not ready:
            return
        line = process.stdout.readline()
        if not line:
            return
        sink(line.rstrip("\n"))


def run_sync(*, ui=None) -> None:
    command = [str(REPO_ROOT / "bin" / "sync-codex-chat-qmd.sh")]
    if ui is not None:
        ui.run_command(
            command,
            heartbeat_message="Preparing transcript sync and search; this will take a while...",
            heartbeat_interval=0.5,
        )
        return
    _run_live_with_heartbeat(
        command,
        heartbeat_message="Preparing transcript sync and search; this will take a while...",
    )


def warn(message: str, *, ui=None) -> None:
    if ui is not None:
        ui.status("warn", message)
        return
    print(f"WARNING: {message}", file=sys.stderr)


def maybe_enable_jcodemunch(*, non_interactive: bool, ui=None) -> bool:
    if os.environ.get("CODEX_SPINE_JCODEMUNCH_CHOICE") != "enable":
        return False
    if "jcodemunch-mcp" in enabled_component_names():
        if ui is not None:
            ui.status("ok", "Optional jCodeMunch MCP is already enabled.")
        return False

    components = {component.name: component for component in resolve_components()}
    component = components.get("jcodemunch-mcp")
    if component is None:
        raise RuntimeError("missing optional component definition: jcodemunch-mcp")

    if ui is not None:
        try:
            bundle = fetch_license_terms(component)
        except RuntimeError as exc:
            warn(str(exc), ui=ui)
            return False
        if bundle is None:
            raise RuntimeError(f"missing pinned upstream terms for {component.name}")
        if not ui.page_text(
            "Optional jCodeMunch MCP terms",
            bundle["text"],
            prompt_hint="Enter advances; q or Esc cancels",
        ):
            ui.status("info", "Continuing install without optional jCodeMunch MCP.")
            return False
        while True:
            reply = ui.prompt_text_input(
                "Optional jCodeMunch MCP",
                "Type 'accept' to continue, or press Esc to skip:",
                prompt_hint="Type accept and press Enter",
                modal_size=ui.last_modal_size,
            )
            normalized = (reply or "").strip().lower()
            if normalized == "accept":
                break
            if normalized in {"", "skip", "s", "no", "n", "q", "quit"} or reply is None:
                if ui.prompt_yes_no(["Skip optional jCodeMunch MCP for now?"], default=False):
                    ui.status("info", "Continuing install without optional jCodeMunch MCP.")
                    return False
                continue
            ui.show_message(
                ["Type 'accept' to continue, or press Esc to skip."],
                prompt_hint="Press Enter to return",
            )
        record_license_acknowledgement(component, bundle)
    else:
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
            warn(str(exc), ui=ui)
            if ui is not None:
                ui.status("info", "Continuing install without optional jCodeMunch MCP.")
            else:
                print("Continuing install without optional jCodeMunch MCP.")
            return False

    package_name = component.backend.get("package_name", component.name)
    if ui is not None:
        def ui_run_live(args, *, cwd=None, check=True, env=None):
            ui.run_command(args, cwd=cwd, env=env)
            return subprocess.CompletedProcess(args, 0)

        def ui_run_live_with_heartbeat(
            args,
            *,
            heartbeat_message,
            cwd=None,
            check=True,
            env=None,
            heartbeat_interval=5.0,
        ):
            ui.run_command(
                args,
                cwd=cwd,
                env=env,
                heartbeat_message=heartbeat_message,
                heartbeat_interval=heartbeat_interval,
            )
            return subprocess.CompletedProcess(args, 0)

        def ui_progress(message):
            print(message, flush=True)

        ui.status("info", f"Installing optional {component.name}.")
        with ui.capture_output():
            print(f"{component.name}: installing/updating {package_name}...", flush=True)
            print(f"$ {shlex.join(component_status(component)['action'])}", flush=True)
            for line in update_component(
                component,
                run_live_fn=ui_run_live,
                run_live_with_heartbeat_fn=ui_run_live_with_heartbeat,
                progress_fn=ui_progress,
            ):
                print(line)
    else:
        print(f"{component.name}: installing/updating {package_name}...", flush=True)
        print(f"$ {shlex.join(component_status(component)['action'])}", flush=True)
        for line in update_component(component):
            print(line)

    if ui is not None:
        ui.status("ok", "Optional jCodeMunch setup is ready.")
    replace_managed_block(
        LOCAL_CONFIG_OVERLAY,
        JCODEMUNCH_MCP_BLOCK_START,
        JCODEMUNCH_MCP_BLOCK_END,
        jcodemunch_mcp_overlay_body(),
    )
    return True


def run_bootout(args: list[str], *, label: str, ui=None) -> None:
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
        warn(f"{label} failed: {detail}", ui=ui)


def run_launchctl(args: list[str], *, label: str, ui=None) -> bool:
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
        ,
        ui=ui,
    )
    return False
def install_steps() -> list[Step]:
    return [
        Step("Step 1 of 6", "Keep your settings", "Carry over any Codex settings you still want before setup changes anything."),
        Step("Step 2 of 6", "Optional code search", "Choose whether to add optional indexed code navigation."),
        Step("Step 3 of 6", "Required tools", "Install Homebrew if needed, then install Python, ripgrep, Node, pnpm, uv, and jq."),
        Step("Step 4 of 6", "Install Codex tools", "Install qmd and the rest of the codex-spine tools."),
        Step("Step 5 of 6", "Finish setup", "Write your Codex setup, turn on background sync, and prepare search."),
        Step("Step 6 of 6", "Verify install", "Run one last verification."),
    ]


def _carry_preflight_step_statuses(ui) -> None:
    carried_notes = [
        "Your Codex settings are ready for setup.",
        "Optional code search has been decided.",
        "The required tools are ready.",
    ]
    for index, note in enumerate(carried_notes):
        step = ui.steps[index]
        if step.status == "pending":
            step.status = "ok"
        if not step.note:
            step.note = note


def run_install(*, non_interactive: bool, ui=None) -> None:
    shell_plan = detect_shell_integration_plan()
    preflight_completed = os.environ.get("CODEX_SPINE_PREFLIGHT_COMPLETED") == "1"
    config_plan = None

    if shell_plan.warning:
        warn(shell_plan.warning, ui=ui)

    if not preflight_completed:
        if ui is not None:
            ui.set_step(2, note="Checking that the required tools are ready.")
            with ui.capture_output():
                brew_path = ensure_homebrew(non_interactive=non_interactive)
                config_plan = prepare_generated_config_target(LIVE_CONFIG_PATH, non_interactive=non_interactive)
                installed_formulas = install_missing_brew_formulas(
                    brew_path,
                    non_interactive=non_interactive,
                )
            ui.finish_step(2, status="ok", note="The required tools are ready.")
        else:
            brew_path = ensure_homebrew(non_interactive=non_interactive)
            config_plan = prepare_generated_config_target(LIVE_CONFIG_PATH, non_interactive=non_interactive)
            installed_formulas = install_missing_brew_formulas(
                brew_path,
                non_interactive=non_interactive,
            )
            if installed_formulas:
                print(f"Installed Homebrew packages: {', '.join(installed_formulas)}")

    if ui is not None and preflight_completed:
        _carry_preflight_step_statuses(ui)

    if ui is not None:
        ui.set_step(3, note="Getting your Codex files ready and installing qmd.")
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

    if ui is not None:
        run_script(
            "update",
            "--defaults-only",
            *(["--non-interactive"] if non_interactive else []),
            ui=ui,
            heartbeat_message="Installing the main codex-spine tools; this can take a while...",
            heartbeat_interval=0.5,
        )
        maybe_enable_jcodemunch(non_interactive=non_interactive, ui=ui)
        note = "qmd and the rest of the codex-spine tools are ready."
        if not shell_plan.supported:
            note += " Shell setup was skipped because this shell is not zsh."
        ui.finish_step(3, status="ok", note=note)
    else:
        print("\nNow we'll install or update the core packages codex-spine manages. This can take a while on the first run.", flush=True)
        run_script("update", "--defaults-only", *(["--non-interactive"] if non_interactive else []))
        maybe_enable_jcodemunch(non_interactive=non_interactive)

    if config_plan is None:
        config_plan = prepare_generated_config_target(LIVE_CONFIG_PATH, non_interactive=non_interactive)

    if ui is not None:
        ui.set_step(4, note="Writing your settings and warming search.")
    rendered = render_config_text()
    write_generated_config(
        LIVE_CONFIG_PATH,
        rendered,
        allow_unmanaged_replace=config_plan.allow_unmanaged_replace,
    )
    if config_plan.adopted_overlay_path is not None:
        if ui is not None:
            ui.status("ok", f"Imported the existing Codex config into {config_plan.adopted_overlay_path}.")
        else:
            print(f"\nImported the existing Codex config into {config_plan.adopted_overlay_path}")
    if config_plan.backup_path is not None:
        if ui is not None:
            ui.status("ok", f"Backed up the previous live Codex config to {config_plan.backup_path}.")
        else:
            print(f"Backed up the previous live Codex config to {config_plan.backup_path}")

    uid = subprocess.run(["id", "-u"], check=True, capture_output=True, text=True).stdout.strip()
    for legacy_name in LEGACY_QMD_CHAT_LAUNCH_AGENT_NAMES:
        legacy_path = HOME / "Library/LaunchAgents" / legacy_name
        run_bootout([f"gui/{uid}", str(legacy_path)], label=f"launchctl bootout {legacy_name}", ui=ui)
        if legacy_path.exists():
            legacy_path.unlink()

    write_managed_launch_agent(LIVE_QMD_CHAT_LAUNCH_AGENT_PATH, render_launch_agent_text())
    if ui is not None:
        ui.status("info", "macOS may show a one-time Background Items Added notification for sync-codex-chat-qmd.sh.")

    if ui is not None:
        run_sync(ui=ui)
        ui.finish_step(4, status="ok", note="Your Codex setup, background sync, and search are ready.")
    else:
        print("\nNow we'll sync your local Codex transcripts from ~/.codex/sessions into the local qmd index. This can take a while the first time.")
        run_sync()

    if ui is not None:
        ui.set_step(5, note="Starting background sync and the final verification.")
    run_bootout([f"gui/{uid}", str(LIVE_QMD_CHAT_LAUNCH_AGENT_PATH)], label="launchctl bootout codex-spine.qmd-codex-chat plist", ui=ui)
    for legacy_label in LEGACY_QMD_CHAT_LAUNCH_AGENT_LABELS:
        run_bootout([f"gui/{uid}/{legacy_label}"], label=f"launchctl bootout {legacy_label}", ui=ui)
    run_launchctl(
        ["bootstrap", f"gui/{uid}", str(LIVE_QMD_CHAT_LAUNCH_AGENT_PATH)],
        label="launchctl bootstrap",
        ui=ui,
    )

    verify_command = [str(REPO_ROOT / "scripts" / "verify")]
    if ui is not None:
        verify_lines: list[str] = []
        verify_process = subprocess.Popen(
            verify_command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        def pump_verify() -> bool:
            _drain_command_output(verify_process, verify_lines.append)
            if verify_process.poll() is None:
                return ui.pulse_activity(
                    "Final verification is already running; this will finish shortly...",
                    render=False,
                )
            return ui.clear_activity(render=False)

        ui.finish_step(5, status="ok", note="Installation complete.")
        ui.wait_for_acknowledgement(
            [
                "Installation complete.",
                "",
                "One brief verification will finish after you press Enter.",
            ],
            prompt_hint="Press Enter to finish",
            on_tick=pump_verify,
        )
        ui.detached_to_terminal = True
        ui.close()
        ui = None
        while verify_process.poll() is None:
            _drain_command_output(verify_process, verify_lines.append)
            time.sleep(0.05)
        _drain_command_output(verify_process, verify_lines.append)
        for line in verify_lines:
            print(line)
        if verify_process.returncode:
            raise subprocess.CalledProcessError(verify_process.returncode, verify_command)
    else:
        run_script("verify", ui=ui)
    if not shell_plan.supported:
        if ui is not None:
            ui.status("warn", "Shell integration was skipped because the detected login shell is not zsh.")
            ui.status("info", "Manual follow-up: add `$HOME/.local/bin` to your shell startup and source the repo shell fragments if desired.")
        else:
            print("Shell integration was skipped because the detected login shell is not zsh.")
            print("Manual follow-up: add `$HOME/.local/bin` to your shell startup and source the repo shell fragments if desired.")
    elif ui is not None:
        ui.status("info", "Current terminals do not automatically pick up shell changes. Open a new shell when you want the refreshed environment.")
    if os.environ.get("CODEX_SPINE_JCODEMUNCH_CHOICE") is None and "jcodemunch-mcp" not in enabled_component_names():
        if ui is not None:
            ui.status("info", "Optional next step: enable jCodeMunch MCP with `./scripts/component-enable jcodemunch-mcp`.")
        else:
            print("Optional next step: enable jCodeMunch MCP for indexed code navigation with `./scripts/component-enable jcodemunch-mcp`.")
    print("Your Codex is ready to use with improved capabilities.")
    print("install: ok")


def main() -> int:
    ui = None
    try:
        parser = argparse.ArgumentParser()
        parser.add_argument("--non-interactive", action="store_true")
        args = parser.parse_args()
        non_interactive = args.non_interactive or not sys.stdin.isatty()
        title = "codex-spine installer"
        subtitle = ""
        with open_tui(title=title, subtitle=subtitle, steps=install_steps()) as ui:
            run_install(non_interactive=non_interactive, ui=None if non_interactive else ui)
        return 0
    except RuntimeError as exc:
        if ui is not None and not non_interactive and not ui.detached_to_terminal:
            ui.fail_step(ui.current_step, note="Install stopped before completion.")
            ui.show_message(
                [
                    "Managed install stopped:",
                    "",
                    str(exc),
                ],
                prompt_hint="Press Enter to exit",
            )
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except subprocess.CalledProcessError as exc:
        if ui is not None and not non_interactive and not ui.detached_to_terminal:
            ui.fail_step(ui.current_step, note="A managed-runtime command failed.")
            ui.show_message(
                [
                    "A managed-runtime command failed:",
                    "",
                    f"Command: {' '.join(exc.cmd)}",
                    f"Exit status: {exc.returncode}",
                    "",
                    "See the terminal output above for the failing command details.",
                ],
                prompt_hint="Press Enter to exit",
            )
        print(f"ERROR: command failed with exit status {exc.returncode}: {' '.join(exc.cmd)}", file=sys.stderr)
        print("See output above for details.", file=sys.stderr)
        return exc.returncode or 1


if __name__ == "__main__":
    raise SystemExit(main())

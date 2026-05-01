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
    JCODEMUNCH_MCP_BLOCK_END,
    JCODEMUNCH_MCP_BLOCK_START,
    LIVE_CONFIG_PATH,
    LOCAL_CONFIG_EXAMPLE,
    LOCAL_CONFIG_OVERLAY,
    ensure_example_copy,
    munch_mcp_overlay_body,
    prepare_generated_config_target,
    render_config_text,
    replace_managed_block,
    sync_jcodemunch_global_config,
    write_generated_config,
)
from component_manager import (  # noqa: E402
    acknowledgement_group_components,
    ensure_component_acknowledged,
    record_component_enabled,
    resolve_components,
    update_component,
)

def main() -> int:
    try:
        parser = argparse.ArgumentParser()
        parser.add_argument("component")
        parser.add_argument("--non-interactive", action="store_true")
        args = parser.parse_args()

        components = {component.name: component for component in resolve_components()}
        if args.component not in components:
            print(f"ERROR: unknown component: {args.component}", file=sys.stderr)
            return 1

        component = components[args.component]
        if component.default_enabled:
            print(f"{component.name} is already enabled by default")
            return 0

        target_components = acknowledgement_group_components(component, list(components.values()))

        ensure_example_copy(LOCAL_CONFIG_EXAMPLE, LOCAL_CONFIG_OVERLAY)
        ensure_component_acknowledged(
            component,
            non_interactive=args.non_interactive or not sys.stdin.isatty(),
        )
        for target_component in target_components:
            update_component(target_component)
            record_component_enabled(target_component)

        if any(target_component.name == "jcodemunch-mcp" for target_component in target_components):
            replace_managed_block(
                LOCAL_CONFIG_OVERLAY,
                JCODEMUNCH_MCP_BLOCK_START,
                JCODEMUNCH_MCP_BLOCK_END,
                munch_mcp_overlay_body(),
            )
            sync_jcodemunch_global_config()

        config_plan = prepare_generated_config_target(
            LIVE_CONFIG_PATH,
            non_interactive=args.non_interactive or not sys.stdin.isatty(),
        )
        rendered = render_config_text()
        write_generated_config(
            LIVE_CONFIG_PATH,
            rendered,
            allow_unmanaged_replace=config_plan.allow_unmanaged_replace,
        )
        if config_plan.adopted_overlay_path is not None:
            print(f"Imported the existing Codex config into {config_plan.adopted_overlay_path}")
        if config_plan.backup_path is not None:
            print(f"Backed up the previous live Codex config to {config_plan.backup_path}")

        subprocess.run([str(REPO_ROOT / "scripts" / "verify")], check=True)
        print(f"{', '.join(target_component.name for target_component in target_components)}: enabled")
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

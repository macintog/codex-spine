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
    render_config_text,
    replace_managed_block,
    write_generated_config,
)
from component_manager import (  # noqa: E402
    ensure_license_acknowledged,
    resolve_components,
    update_component,
)


def jcodemunch_mcp_overlay_body() -> str:
    return """[mcp_servers.jcodemunch]
command = "__HOME__/.local/bin/jcodemunch-mcp"
args = []
enabled = true"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("component")
    parser.add_argument("--accept-license", action="store_true")
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

    ensure_example_copy(LOCAL_CONFIG_EXAMPLE, LOCAL_CONFIG_OVERLAY)
    ensure_license_acknowledged(
        component,
        accept_license=args.accept_license,
        non_interactive=args.non_interactive or not sys.stdin.isatty(),
    )
    update_component(component)

    if component.name == "jcodemunch-mcp":
        replace_managed_block(
            LOCAL_CONFIG_OVERLAY,
            JCODEMUNCH_MCP_BLOCK_START,
            JCODEMUNCH_MCP_BLOCK_END,
            jcodemunch_mcp_overlay_body(),
        )

    rendered = render_config_text()
    write_generated_config(LIVE_CONFIG_PATH, rendered)

    subprocess.run([str(REPO_ROOT / "scripts" / "verify")], check=True)
    print(f"{component.name}: enabled")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "lib"))

from codex_spine import enabled_component_names  # noqa: E402
from component_manager import (  # noqa: E402
    ensure_license_acknowledged,
    resolve_components,
    update_component,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("components", nargs="*")
    parser.add_argument("--defaults-only", action="store_true")
    parser.add_argument("--accept-license", action="store_true")
    parser.add_argument("--non-interactive", action="store_true")
    args = parser.parse_args()

    resolved = {component.name: component for component in resolve_components()}
    enabled_optional = enabled_component_names()

    if args.components:
        selected_names = args.components
    elif args.defaults_only:
        selected_names = [name for name, component in resolved.items() if component.default_enabled]
    else:
        selected_names = [
            name
            for name, component in resolved.items()
            if component.default_enabled or name in enabled_optional
        ]

    for name in selected_names:
        component = resolved.get(name)
        if component is None:
            print(f"ERROR: unknown component: {name}", file=sys.stderr)
            return 1
        if not component.default_enabled and name not in enabled_optional and not args.components:
            continue
        ensure_license_acknowledged(
            component,
            accept_license=args.accept_license,
            non_interactive=args.non_interactive or not sys.stdin.isatty(),
        )
        for line in update_component(component):
            print(line)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

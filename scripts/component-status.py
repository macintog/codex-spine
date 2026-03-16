#!/usr/bin/env python3

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "lib"))

from codex_spine import enabled_component_names  # noqa: E402
from component_manager import component_status, resolve_components  # noqa: E402


def main() -> int:
    enabled = enabled_component_names()
    for component in resolve_components():
        status = component_status(component)
        component_enabled = component.default_enabled or component.name in enabled
        print(
            f"{component.name}: enabled={'yes' if component_enabled else 'no'} "
            f"installed={'yes' if status['installed'] else 'no'} "
            f"healthy={'yes' if status['healthy'] else 'no'}"
        )
        print(f"  {status['detail']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

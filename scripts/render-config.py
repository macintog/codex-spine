#!/usr/bin/env python3

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "lib"))

from codex_spine import (  # noqa: E402
    LIVE_CONFIG_PATH,
    prepare_generated_config_target,
    render_config_text,
    write_generated_config,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stdout", action="store_true")
    args = parser.parse_args()

    rendered = render_config_text()
    if args.stdout:
        sys.stdout.write(rendered)
        return 0

    backup_path = prepare_generated_config_target(
        LIVE_CONFIG_PATH,
        non_interactive=not sys.stdin.isatty(),
    )
    write_generated_config(LIVE_CONFIG_PATH, rendered)
    if backup_path is not None:
        print(f"Backed up the existing Codex config to {backup_path}")
    print(LIVE_CONFIG_PATH)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

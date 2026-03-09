#!/usr/bin/env python3

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "lib"))

from codex_spine import LIVE_CONFIG_PATH, render_config_text, write_generated_config  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stdout", action="store_true")
    args = parser.parse_args()

    rendered = render_config_text()
    if args.stdout:
        sys.stdout.write(rendered)
        return 0

    write_generated_config(LIVE_CONFIG_PATH, rendered)
    print(LIVE_CONFIG_PATH)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

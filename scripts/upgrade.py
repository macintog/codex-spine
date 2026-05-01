#!/usr/bin/env python3

from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
VERSION_TAG_RE = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")


def run(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=REPO_ROOT, check=check, text=True)


def capture(args: list[str], *, check: bool = True) -> str:
    result = subprocess.run(
        args,
        cwd=REPO_ROOT,
        check=check,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def ensure_git_repo() -> None:
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 or Path(result.stdout.strip()).resolve() != REPO_ROOT:
        raise SystemExit("ERROR: make upgrade must run from a codex-spine git checkout")


def ensure_clean_checkout() -> None:
    status = capture(["git", "status", "--porcelain"], check=True)
    if status:
        raise SystemExit(
            "ERROR: refusing to upgrade a checkout with local changes. "
            "Commit, stash, or remove them first."
        )


def version_key(tag: str) -> tuple[int, int, int]:
    match = VERSION_TAG_RE.match(tag)
    if not match:
        raise ValueError(tag)
    return tuple(int(part) for part in match.groups())


def latest_version_tag() -> str:
    raw_tags = capture(["git", "tag", "--list", "v[0-9]*.[0-9]*.[0-9]*"])
    tags = [tag for tag in raw_tags.splitlines() if VERSION_TAG_RE.match(tag)]
    if not tags:
        raise SystemExit("ERROR: no release tags like v0.5.4 were found after fetch")
    return max(tags, key=version_key)


def current_label() -> str:
    tag = capture(["git", "describe", "--tags", "--exact-match"], check=False)
    if tag:
        return tag
    return capture(["git", "rev-parse", "--short", "HEAD"])


def rev_parse(ref: str) -> str:
    return capture(["git", "rev-parse", f"{ref}^{{commit}}"])


def checkout_target(target_ref: str) -> None:
    current_head = rev_parse("HEAD")
    target_head = rev_parse(target_ref)
    print(f"codex-spine upgrade: current {current_label()} ({current_head[:12]})")
    print(f"codex-spine upgrade: target {target_ref} ({target_head[:12]})")
    if current_head == target_head:
        print("codex-spine upgrade: checkout already at target")
        return
    run(["git", "checkout", "--detach", target_head])


def main() -> int:
    parser = argparse.ArgumentParser(description="Upgrade codex-spine to the newest release tag from origin.")
    parser.parse_args()

    ensure_git_repo()
    ensure_clean_checkout()

    print("codex-spine upgrade: fetching release tags")
    run(["git", "fetch", "--tags", "--prune", "origin"])
    target_ref = latest_version_tag()
    checkout_target(target_ref)

    print("codex-spine upgrade: installing upgraded checkout")
    run(["make", "install"])
    print("codex-spine upgrade: refreshing managed components")
    run(["make", "update"])
    print("codex-spine upgrade: verifying upgraded environment")
    run(["make", "verify"])
    print("upgrade: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

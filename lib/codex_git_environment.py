from __future__ import annotations

from pathlib import Path

from codex_spine import BLOCK_END, BLOCK_START, REPO_ROOT, managed_links as spine_managed_links
from codex_spine import shell_source_targets as spine_shell_source_targets


def shared_git_hooks_path(repo_root: Path = REPO_ROOT) -> Path:
    return repo_root / ".githooks"


def managed_links(repo_root: Path = REPO_ROOT):
    links = spine_managed_links()
    if repo_root == REPO_ROOT:
        return links
    return [
        type(link)(link.live_path, repo_root / link.repo_path.relative_to(REPO_ROOT), link.backup_unmanaged_file, link.replace_empty_unmanaged_file)
        for link in links
    ]


def shell_source_targets(repo_root: Path = REPO_ROOT) -> dict[Path, Path]:
    targets = spine_shell_source_targets()
    if repo_root == REPO_ROOT:
        return targets
    return {live: repo_root / source.relative_to(REPO_ROOT) for live, source in targets.items()}


def active_managed_repo_root() -> tuple[Path, list[str], list[str]]:
    warnings: list[str] = []
    errors: list[str] = []
    roots: set[Path] = set()
    for link in spine_managed_links():
        if not link.live_path.is_symlink():
            continue
        target = link.live_path.resolve(strict=False)
        try:
            suffix = link.repo_path.relative_to(REPO_ROOT)
        except ValueError:
            continue
        if len(target.parts) < len(suffix.parts) or target.parts[-len(suffix.parts) :] != suffix.parts:
            warnings.append(f"managed anchor points outside a codex-spine checkout: {link.live_path} -> {target}")
            continue
        root = target
        for _ in suffix.parts:
            root = root.parent
        roots.add(root.resolve(strict=False))
    if not roots:
        warnings.append(f"could not infer the active managed repo root; using {REPO_ROOT}")
        return REPO_ROOT, warnings, errors
    if len(roots) > 1:
        errors.append("managed live paths point at multiple codex-spine roots: " + ", ".join(map(str, sorted(roots))))
    active = sorted(roots)[0]
    if active != REPO_ROOT:
        warnings.append(f"live environment is managed by {active}, not the current checkout {REPO_ROOT}")
    return active, warnings, errors

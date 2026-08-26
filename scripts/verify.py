#!/usr/bin/env python3

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.pycache_prefix = str(Path(tempfile.gettempdir()) / "codex-spine-pycache")

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "lib"))

from codex_spine import (  # noqa: E402
    ADOPTED_CONFIG_OVERLAY,
    BLOCK_END,
    BLOCK_START,
    HOME,
    LIVE_CONFIG_PATH,
    LIVE_QMD_CHAT_LAUNCH_AGENT_PATH,
    LOCAL_CONFIG_OVERLAY,
    MAINTAINED_COMPONENTS_PATH,
    REQUIRED_CLIS,
    cli_available,
    config_text_matches_rendered_contract,
    deep_merge,
    detect_local_reference_hits,
    detect_secret_hits,
    detect_shell_integration_plan,
    enabled_component_names,
    first_nonempty_line,
    ensure_symlink,
    managed_links,
    render_config_text,
    render_launch_agent_text,
    RETIRED_MANAGED_SKILL_PATHS,
    runtime_env,
    serialize_toml,
    shell_source_targets,
    text_file_paths,
    validate_public_doc_surface,
)
from component_manager import component_status, resolve_components, validate_maintenance_manifest  # noqa: E402
from toml_compat import tomllib  # noqa: E402


def fail(errors: list[str]) -> int:
    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)
    return 1


def tag_verifier_messages(category: str, messages: list[str]) -> list[str]:
    return [f"[{category}] {message}" for message in messages]


PUBLIC_SKILL_DIRS = frozenset(
    {
        "causal-explanation",
        "change-impact",
        "improve-codebase-architecture",
        "project-continuity",
        "skill-authoring-quality",
        "tufte-visualization",
        "yeet",
    }
)
PUBLIC_REQUIRED_SKILL_SENTINELS = (
    ("change-impact", "SKILL.md"),
    ("change-impact", "LICENSE.txt"),
    ("causal-explanation", "SKILL.md"),
    ("causal-explanation", "LICENSE.txt"),
    ("improve-codebase-architecture", "SKILL.md"),
    ("improve-codebase-architecture", "LICENSE.txt"),
    ("project-continuity", "SKILL.md"),
    ("project-continuity", "agents/openai.yaml"),
    ("project-continuity", "references/adoption-procedure.md"),
    ("project-continuity", "scripts/audit-continuity.py"),
    ("skill-authoring-quality", "SKILL.md"),
    ("skill-authoring-quality", "LICENSE.txt"),
    ("tufte-visualization", "SKILL.md"),
    ("tufte-visualization", "agents/openai.yaml"),
    ("tufte-visualization", "references/chart-selection.md"),
    ("tufte-visualization", "references/uncertainty.md"),
    ("tufte-visualization", "references/citations.md"),
    ("yeet", "SKILL.md"),
    ("yeet", "agents/openai.yaml"),
)
PUBLIC_DOC_REQUIRED_ANCHOR_GROUPS = {
    "README.md": (
        ("codex/TOOLING.md",),
        ("`memory` MCP", "memory` MCP", "memory MCP"),
        ("jdocmunch",),
        ("jdatamunch",),
        ("~/.codex/memories/",),
        ("disabled by the base config",),
        ("unless the current user explicitly asks",),
        ("`codex/config/90-local.toml`", "codex/config/90-local.toml"),
        ("`/memories`", "/memories"),
    ),
    "codex/AGENTS.md": (
        ("README.md",),
        ("codex/TOOLING.md",),
        ("Default to silent execution",),
        ("repo-declared closeout mode",),
        ("configured integration task classes",),
        ("generation-check and update the resolver-selected adopted checkpoint",),
        ("before reporting completion",),
        ("workers never write it",),
        ("ask one targeted question",),
        ("unanswered automatic goal continuation is a no-op",),
        ("do not create action queues",),
        ("memory.bootstrap_context",),
        ("jcodemunch",),
        ("jdocmunch",),
        ("jdatamunch",),
        ("~/.codex/memories/",),
        ("disabled by the base config",),
        ("unless the current user explicitly asks",),
        ("`codex/config/90-local.toml`", "codex/config/90-local.toml"),
    ),
    "codex/TOOLING.md": (
        ("`AGENTS.md`",),
        ("`PROJECT_CONTINUITY.md`",),
        ("`CHECKPOINT.md`",),
        ("codex-project-checkpoint update --expected-generation",),
        ("before reporting completion for `yeet`",),
        ("codex-git-safe yeet --apply",),
        ("memory.bootstrap_context",),
        ("search",),
        ("deep_search",),
        ("vector_search",),
        ("get",),
        ("multi_get",),
        ("~/.codex/memories/",),
        ("disabled by the base config",),
        ("unless the current user explicitly asks",),
        ("`codex/config/90-local.toml`", "codex/config/90-local.toml"),
        ("`/memories`", "/memories"),
        ("Intervention Before Workaround",),
        ("automatic goal continuation",),
        ("`memories.disable_on_external_context`", "memories.disable_on_external_context"),
        ("jcodemunch",),
        ("jdocmunch",),
        ("jdatamunch",),
        ("search_symbols",),
        ("get_symbol_source",),
        ("index_folder",),
        ("search_sections",),
        ("describe_dataset",),
    ),
}
LOCAL_ONLY_CONFIG_OVERLAYS = frozenset({ADOPTED_CONFIG_OVERLAY, LOCAL_CONFIG_OVERLAY})


def validate_public_agents_policy_texts(
    readme_text: str,
    agents_text: str,
    tooling_text: str,
    *,
    readme_path: Path,
    agents_path: Path,
    tooling_path: Path,
) -> list[str]:
    errors: list[str] = []
    texts = {
        "README.md": (readme_text, readme_path),
        "codex/AGENTS.md": (agents_text, agents_path),
        "codex/TOOLING.md": (tooling_text, tooling_path),
    }

    for doc_label, anchor_groups in PUBLIC_DOC_REQUIRED_ANCHOR_GROUPS.items():
        text, path = texts[doc_label]
        for anchor_group in anchor_groups:
            if any(anchor in text for anchor in anchor_group):
                continue
            expected = " or ".join(anchor_group)
            errors.append(f"public doc is missing a required routing anchor: {path}: {expected}")

    return errors


def validate_public_skill_surface_contract() -> list[str]:
    errors: list[str] = []
    skills_root = REPO_ROOT / "skills"
    if not skills_root.exists():
        errors.append(f"public repo is missing shipped skill content: {skills_root}")
        return errors

    for skill_dir, relative_path in PUBLIC_REQUIRED_SKILL_SENTINELS:
        sentinel = skills_root / skill_dir / relative_path
        if not sentinel.exists():
            errors.append(f"public repo is missing required shipped skill file: {sentinel}")

    shipped_skill_dirs = {
        path.name
        for path in skills_root.iterdir()
        if path.is_dir()
    }
    unexpected_skill_dirs = sorted(shipped_skill_dirs - PUBLIC_SKILL_DIRS)
    for skill_dir in unexpected_skill_dirs:
        errors.append(f"public repo ships an undeclared skill directory: {skills_root / skill_dir}")

    required_control_anchors = {
        skills_root / "yeet/SKILL.md": (
            "exact `yeet` instruction",
            "codex-git-safe yeet --apply",
            "is terminal; do not ask for or emit a second closeout phrase",
        ),
        skills_root / "project-continuity/SKILL.md": (
            "Bind the latest explicit user-selected task subject",
            "Only the adopted scope's resolved external project checkpoint",
            "cannot create, queue, authorize, or select follow-on work",
        ),
        skills_root / "project-continuity/scripts/audit-continuity.py": (
            "RESERVED_CONTINUATION_NAMES",
            "CONTINUATION_TEXT_SUFFIXES",
            "has_historical_declaration",
            "recursive-continuation-control",
            'result = "stale"',
        ),
        REPO_ROOT / "codex/TOOLING.md": (
            "## Current Task Subject Binding",
            "Completion may report residual findings",
        ),
        REPO_ROOT / "codex/AGENTS.md": (
            "bind the latest explicit user request",
            "Completion is terminal",
            "fresh explicit user request and subject binding",
        ),
    }
    for path, anchors in required_control_anchors.items():
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        for anchor in anchors:
            if anchor not in text:
                errors.append(f"public control-plane guard is missing an anchor: {path}: {anchor}")

    retired_multi_step = skills_root / "multi-step"
    if retired_multi_step.exists():
        errors.append(f"retired public multi-step skill must remain absent: {retired_multi_step}")

    notice_path = REPO_ROOT / "THIRD_PARTY_NOTICES.md"
    if not notice_path.is_file():
        errors.append(f"public repo is missing third-party notices: {notice_path}")
    else:
        notice = notice_path.read_text(encoding="utf-8")
        for anchor in (
            "https://github.com/cursor/plugins",
            "https://github.com/cursor/plugins/tree/60c641e4fad674784b30abcf9f8915dea39df38d/pstack",
            "https://github.com/cursor/plugins/blob/60c641e4fad674784b30abcf9f8915dea39df38d/pstack/LICENSE",
            "https://github.com/mattpocock/skills",
            "https://github.com/mattpocock/skills/blob/885e2ca4d842d139e9aef4e48d366c63cb1b8013/LICENSE",
        ):
            if anchor not in notice:
                errors.append(f"third-party notices are missing an upstream anchor: {notice_path}: {anchor}")

    runtime_paths = (
        REPO_ROOT / "bin/codex-git-safe",
        REPO_ROOT / "bin/codex-gitea-common.sh",
        REPO_ROOT / "bin/codex-gitea-push.sh",
        REPO_ROOT / "bin/codex-gitea-pr.sh",
        REPO_ROOT / "bin/codex-gitea-pr-finalize.sh",
        REPO_ROOT / "lib/codex_git_environment.py",
        REPO_ROOT / "lib/codex_git_safe.py",
        REPO_ROOT / "lib/codex_git_scratch.py",
        REPO_ROOT / ".githooks/pre-commit",
    )
    for runtime_path in runtime_paths:
        if not runtime_path.is_file():
            errors.append(f"public yeet runtime is missing: {runtime_path}")
    helper = REPO_ROOT / "bin/codex-git-safe"
    if helper.is_file():
        runtime_pythons = [Path(sys.executable)]
        minimum_python = Path(os.environ.get("CODEX_SPINE_MINIMUM_PYTHON", "/usr/bin/python3"))
        if minimum_python.is_file():
            version_probe = subprocess.run(
                [str(minimum_python), "-c", "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"],
                check=False,
                capture_output=True,
                text=True,
            )
            if version_probe.returncode == 0 and version_probe.stdout.strip() == "3.9":
                runtime_pythons.append(minimum_python)
        seen_pythons: set[Path] = set()
        for runtime_python in runtime_pythons:
            runtime_python = runtime_python.resolve()
            if runtime_python in seen_pythons:
                continue
            seen_pythons.add(runtime_python)
            result = subprocess.run(
                [str(runtime_python), str(helper), "--help"],
                cwd=str(REPO_ROOT),
                check=False,
                capture_output=True,
                text=True,
            )
            if result.returncode != 0 or "yeet" not in result.stdout:
                detail = (result.stderr or result.stdout or f"exit {result.returncode}").strip()
                errors.append(f"public yeet runtime help failed under {runtime_python}: {detail}")

    for path in (
        REPO_ROOT / "README.md",
        REPO_ROOT / "ARCHITECTURE.md",
        REPO_ROOT / "SECURITY.md",
        REPO_ROOT / "codex/AGENTS.md",
        REPO_ROOT / "codex/TOOLING.md",
    ):
        text = path.read_text(encoding="utf-8")
        for skill_ref in sorted(set(re.findall(r"skills/[A-Za-z0-9._/-]+", text))):
            ref_path = Path(skill_ref)
            if len(ref_path.parts) < 2 or ref_path.parts[0] != "skills":
                errors.append(f"public doc references an invalid skill path: {path}: {skill_ref}")
                continue
            if ref_path.parts[1] not in PUBLIC_SKILL_DIRS:
                errors.append(f"public doc references a non-shipped skill path: {path}: {skill_ref}")

    return errors


def validate_public_agents_policy() -> list[str]:
    readme_path = REPO_ROOT / "README.md"
    agents_path = REPO_ROOT / "codex/AGENTS.md"
    tooling_path = REPO_ROOT / "codex/TOOLING.md"
    try:
        readme_text = readme_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return [f"missing public repo README: {readme_path}"]
    try:
        agents_text = agents_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return [f"missing Codex policy file: {agents_path}"]
    try:
        tooling_text = tooling_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return [f"missing Codex tooling guide: {tooling_path}"]

    return validate_public_agents_policy_texts(
        readme_text,
        agents_text,
        tooling_text,
        readme_path=readme_path,
        agents_path=agents_path,
        tooling_path=tooling_path,
    )


def validate_component_cli_surface() -> list[str]:
    errors: list[str] = []
    components = {component.name: component for component in resolve_components()}
    qmd = components.get("qmd")
    expected_qmd_builds = [
        "better-sqlite3",
        "node-llama-cpp",
        "tree-sitter-go",
        "tree-sitter-javascript",
        "tree-sitter-python",
        "tree-sitter-rust",
        "tree-sitter-typescript",
    ]
    if qmd is None:
        errors.append("qmd is missing from the maintenance manifest")
    elif qmd.backend.get("allow_builds") != expected_qmd_builds:
        errors.append("qmd must keep the reviewed native dependency build allowlist")
    else:
        action = component_status(qmd)["action"]
        expected_flags = [f"--allow-build={package_name}" for package_name in expected_qmd_builds]
        if action[3:-1] != expected_flags:
            errors.append("qmd pnpm install action does not pass the reviewed native dependency build allowlist")

    for script_name in ("component-enable.py", "update.py", "upgrade.py"):
        script_path = REPO_ROOT / "scripts" / script_name
        result = subprocess.run(
            ["python3", str(script_path), "--help"],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            detail = first_nonempty_line(result.stderr, result.stdout) or f"exit {result.returncode}"
            errors.append(f"component CLI help check failed for {script_path}: {detail}")
            continue
        if "--accept-license" in result.stdout:
            errors.append(f"hidden QA acceptance bypass leaked into the shipped CLI surface: {script_path}")

    for path in text_file_paths(REPO_ROOT):
        if path == Path(__file__).resolve():
            continue
        text = path.read_text(encoding="utf-8")
        if "--accept-license" in text:
            errors.append(f"hidden QA acceptance bypass leaked into the shipped repo surface: {path}")

    return errors


def validate_optional_munch_runner_probes() -> list[str]:
    errors: list[str] = []
    components = {component.name: component for component in resolve_components()}
    expected_health_only = {
        "jdocmunch-mcp": ["-h"],
        "jdatamunch-mcp": ["-h"],
    }
    for component_name, expected_health_args in expected_health_only.items():
        component = components.get(component_name)
        if component is None:
            errors.append(f"optional Munch runner is missing from the maintenance manifest: {component_name}")
            continue
        if component.backend.get("version_args"):
            errors.append(f"{component_name} must not use --version as its compatibility probe")
        if component.backend.get("health_args") != expected_health_args:
            errors.append(f"{component_name} must use {expected_health_args!r} as its non-blocking compatibility probe")

    component = components.get("jcodemunch-mcp")
    if component is None:
        errors.append("optional Munch runner is missing from the maintenance manifest: jcodemunch-mcp")
    elif component.backend.get("version_args") != ["--version"]:
        errors.append("jcodemunch-mcp must keep its real --version compatibility probe")

    return errors


def validate_memory_public_surface() -> list[str]:
    errors: list[str] = []

    memory_health_text = (REPO_ROOT / "bin" / "codex-memory-health.sh").read_text(encoding="utf-8")
    if '"reason": "repo_cwd_change"' not in memory_health_text:
        errors.append("memory health probe must supply the required bootstrap_context reason")

    mcp_config_path = REPO_ROOT / "codex/config/20-codex-spine-mcps.toml"
    config_text = mcp_config_path.read_text(encoding="utf-8")
    if "[mcp_servers.memory]" not in config_text:
        errors.append(f"public MCP config is missing the memory server: {mcp_config_path}")
    if "[mcp_servers.qmd_codex]" in config_text:
        errors.append(f"deprecated qmd_codex MCP alias still ships publicly: {mcp_config_path}")

    for doc_path in (
        REPO_ROOT / "README.md",
        REPO_ROOT / "ARCHITECTURE.md",
        REPO_ROOT / "codex/AGENTS.md",
    ):
        text = doc_path.read_text(encoding="utf-8")
        if "qmd_codex" in text:
            errors.append(f"public doc still describes qmd_codex as a shipped public surface: {doc_path}")

    base_config_path = REPO_ROOT / "codex/config/00-base.toml"
    base_config = tomllib.loads(base_config_path.read_text(encoding="utf-8"))
    expected_disabled = (
        (("features", "memories"), False),
        (("memories", "generate_memories"), False),
        (("memories", "use_memories"), False),
    )
    for path, expected in expected_disabled:
        value = base_config
        for key in path:
            value = value.get(key) if isinstance(value, dict) else None
        if value is not expected:
            errors.append(f"public base config must disable built-in memory: {base_config_path}: {'.'.join(path)}")

    config_example_path = REPO_ROOT / "codex/config/90-local.toml.example"
    config_example_text = config_example_path.read_text(encoding="utf-8")
    for anchor in ("[features]", "memories = true", "generate_memories = true", "use_memories = true"):
        if anchor not in config_example_text:
            errors.append(f"public local config example is missing an explicit built-in memory opt-in anchor: {config_example_path}: {anchor}")

    return errors


def validate_agent_platform_defaults() -> list[str]:
    errors: list[str] = []
    config = tomllib.loads(render_config_text())
    if "agents" in config:
        errors.append("agent defaults must remain platform-owned: remove the repo-managed [agents] config")

    agents_root = REPO_ROOT / "codex/agents"
    if agents_root.exists():
        errors.append(f"agent defaults must remain platform-owned: remove custom profiles under {agents_root}")

    policy_text = (REPO_ROOT / "codex/AGENTS.md").read_text(encoding="utf-8")
    for phrase in (
        "Delegate through the named profiles",
        "Terra at medium reasoning",
    ):
        if phrase in policy_text:
            errors.append(f"agent defaults must remain platform-owned: remove legacy policy prose: {phrase}")
    return errors


def validate_managed_link_adoption_policy() -> list[str]:
    errors: list[str] = []
    agents_links = [link for link in managed_links() if link.live_path == HOME / ".codex/AGENTS.md"]
    if len(agents_links) != 1:
        return [f"expected exactly one managed ~/.codex/AGENTS.md link, found {len(agents_links)}"]
    agents_link = agents_links[0]
    if not agents_link.backup_unmanaged_file:
        errors.append("~/.codex/AGENTS.md must back up a pre-existing unmanaged file during first install")
    if not agents_link.replace_empty_unmanaged_file:
        errors.append("~/.codex/AGENTS.md must replace a zero-byte unmanaged file during first install")

    with tempfile.TemporaryDirectory(prefix="codex-spine-link-policy-") as tmp_dir:
        tmp_path = Path(tmp_dir)
        live_path = tmp_path / "home" / ".codex" / "AGENTS.md"
        repo_path = tmp_path / "repo" / "codex" / "AGENTS.md"
        repo_path.parent.mkdir(parents=True)
        repo_path.write_text("managed\n", encoding="utf-8")
        live_path.parent.mkdir(parents=True)
        live_path.write_text("existing\n", encoding="utf-8")

        changed, backup_path = ensure_symlink(live_path, repo_path, backup_unmanaged_file=True)
        if not changed:
            errors.append("managed link adoption fixture did not report a change")
        if backup_path is None or not backup_path.exists():
            errors.append("managed link adoption fixture did not create a backup")
        elif backup_path.read_text(encoding="utf-8") != "existing\n":
            errors.append("managed link adoption fixture backup did not preserve the original file")
        if not live_path.is_symlink() or live_path.resolve(strict=False) != repo_path.resolve():
            errors.append("managed link adoption fixture did not install the managed symlink")

    with tempfile.TemporaryDirectory(prefix="codex-spine-empty-link-policy-") as tmp_dir:
        tmp_path = Path(tmp_dir)
        live_path = tmp_path / "home" / ".codex" / "AGENTS.md"
        repo_path = tmp_path / "repo" / "codex" / "AGENTS.md"
        repo_path.parent.mkdir(parents=True)
        repo_path.write_text("managed\n", encoding="utf-8")
        live_path.parent.mkdir(parents=True)
        live_path.write_text("", encoding="utf-8")

        changed, backup_path = ensure_symlink(
            live_path,
            repo_path,
            backup_unmanaged_file=True,
            replace_empty_unmanaged_file=True,
        )
        if not changed:
            errors.append("empty managed link fixture did not report a change")
        if backup_path is not None:
            errors.append("empty managed link fixture created an unnecessary backup")
        if not live_path.is_symlink() or live_path.resolve(strict=False) != repo_path.resolve():
            errors.append("empty managed link fixture did not install the managed symlink")

    return errors


def app_managed_config_variant(rendered_config: str) -> str:
    rendered_data = tomllib.loads(rendered_config)
    app_managed_data = {
        "plugins": {
            "browser-use@openai-bundled": {
                "enabled": True,
            },
        },
        "marketplaces": {
            "openai-bundled": {
                "source_type": "local",
                "source": "/tmp/codex-app-marketplace",
            },
        },
    }
    return serialize_toml(deep_merge(rendered_data, app_managed_data))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-only", action="store_true")
    args = parser.parse_args()

    errors: list[str] = []
    warnings: list[str] = []
    errors.extend(tag_verifier_messages("shipped-surface-check", validate_maintenance_manifest(MAINTAINED_COMPONENTS_PATH)))
    errors.extend(tag_verifier_messages("shipped-surface-check", validate_public_doc_surface()))
    errors.extend(tag_verifier_messages("shipped-surface-check", validate_public_skill_surface_contract()))
    errors.extend(tag_verifier_messages("stable-routing-anchor", validate_public_agents_policy()))
    errors.extend(tag_verifier_messages("boundary-and-leak-check", validate_memory_public_surface()))
    errors.extend(tag_verifier_messages("behavior-contract", validate_agent_platform_defaults()))
    errors.extend(tag_verifier_messages("behavior-contract", validate_component_cli_surface()))
    errors.extend(tag_verifier_messages("behavior-contract", validate_optional_munch_runner_probes()))
    errors.extend(tag_verifier_messages("behavior-contract", validate_managed_link_adoption_policy()))

    for path in text_file_paths(REPO_ROOT):
        if path in LOCAL_ONLY_CONFIG_OVERLAYS:
            continue
        text = path.read_text(encoding="utf-8")
        secret_hits = detect_secret_hits(text)
        if secret_hits:
            errors.append(f"[boundary-and-leak-check] tracked repo file appears to contain a secret: {path}")
        local_hits = detect_local_reference_hits(text, public_surface=True)
        if local_hits:
            errors.append(
                f"[boundary-and-leak-check] tracked repo file still contains local-only references: {path}: {', '.join(local_hits)}"
            )

    if args.repo_only:
        if errors:
            return fail(errors)
        for warning in warnings:
            print(f"WARNING: {warning}", file=sys.stderr)
        print("verify: ok (repo-only)")
        return 0

    for link in managed_links():
        if not link.live_path.is_symlink():
            errors.append(f"[behavior-contract] managed path is not a symlink: {link.live_path}")
            continue
        if link.live_path.resolve(strict=False) != link.repo_path.resolve():
            errors.append(f"[behavior-contract] managed symlink points to the wrong target: {link.live_path}")

    for retired_path in RETIRED_MANAGED_SKILL_PATHS:
        if retired_path.is_symlink():
            errors.append(f"[behavior-contract] retired managed skill link still exists; rerun make install: {retired_path}")

    shell_plan = detect_shell_integration_plan()
    if shell_plan.warning:
        warnings.append(f"[advisory-operational] {shell_plan.warning}")
    for dotfile, fragment in shell_source_targets(shell_plan).items():
        if not dotfile.exists():
            errors.append(f"[behavior-contract] missing shell file: {dotfile}")
            continue
        content = dotfile.read_text(encoding="utf-8")
        if BLOCK_START not in content or BLOCK_END not in content or str(fragment) not in content:
            errors.append(f"[behavior-contract] missing managed source block in {dotfile}")

    if not LIVE_CONFIG_PATH.exists():
        errors.append(f"[behavior-contract] missing generated config: {LIVE_CONFIG_PATH}")
    else:
        live_text = LIVE_CONFIG_PATH.read_text(encoding="utf-8")
        rendered_config = render_config_text()
        if not config_text_matches_rendered_contract(live_text, rendered_config):
            errors.append(f"[behavior-contract] live config is out of sync with rendered output: {LIVE_CONFIG_PATH}")
        app_managed_variant = app_managed_config_variant(rendered_config)
        if not config_text_matches_rendered_contract(app_managed_variant, rendered_config):
            errors.append("[behavior-contract] app-managed plugin marketplace config should not break verification")

    if not LIVE_QMD_CHAT_LAUNCH_AGENT_PATH.exists():
        errors.append(f"[behavior-contract] missing launch agent: {LIVE_QMD_CHAT_LAUNCH_AGENT_PATH}")
    elif LIVE_QMD_CHAT_LAUNCH_AGENT_PATH.read_text(encoding="utf-8") != render_launch_agent_text():
        errors.append(
            f"[behavior-contract] launch agent is out of sync with rendered template: {LIVE_QMD_CHAT_LAUNCH_AGENT_PATH}"
        )

    enabled = enabled_component_names()
    for component in resolve_components():
        status = component_status(component)
        if component.default_enabled and not status["healthy"]:
            errors.append(f"[behavior-contract] default component is unhealthy: {component.name}: {status['detail']}")
        if component.name in enabled and not status["healthy"]:
            errors.append(f"[behavior-contract] enabled optional component is unhealthy: {component.name}: {status['detail']}")

    wrapper_checks = [
        ("qmd-codex wrapper", [str(HOME / ".local/bin/qmd-codex"), "status"]),
        ("memory MCP launcher", [str(REPO_ROOT / "bin" / "codex-memory-health.sh"), str(REPO_ROOT)]),
    ]
    for label, command in wrapper_checks:
        try:
            result = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
                env=runtime_env(),
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            errors.append(f"[behavior-contract] {label} check failed to start: {exc}")
            continue
        if result.returncode != 0:
            detail = first_nonempty_line(result.stderr, result.stdout) or f"exit {result.returncode}"
            errors.append(f"[behavior-contract] {label} is unhealthy: {detail}")

    for cli_name in REQUIRED_CLIS:
        if not cli_available(cli_name):
            errors.append(f"[behavior-contract] required CLI not found: {cli_name}")

    if errors:
        return fail(errors)

    for warning in warnings:
        print(f"WARNING: {warning}", file=sys.stderr)
    print("verify: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

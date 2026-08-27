# Architecture

This is the deep technical reference for `codex-spine`. Use it when the work requires subsystem boundaries, data flow, or operational invariants rather than install instructions alone.

## Directory Structure

```text
codex-spine/
├── LICENSE
├── THIRD_PARTY_NOTICES.md
├── README.md
├── ARCHITECTURE.md
├── SECURITY.md
├── CHANGELOG.md
├── MAINTAINED_COMPONENTS.toml
├── Makefile                    # Thin public dispatcher for install/verify/update/component-status
├── lib/
│   ├── _vendor/tomllib/        # Vendored TOML parser fallback for older stock Python runtimes
│   ├── codex_spine.py          # Shared bootstrap/verify/config helpers, managed-link logic, and path policy
│   ├── codex_git_safe.py        # Managed worktree and terminal Git transaction engine
│   ├── codex_git_scratch.py     # Durable task-worktree registry and cleanup support
│   ├── codex_git_environment.py # Public adapter between Git lifecycle and installed codex-spine state
│   ├── component_manager.py    # Managed acquisition, status, and optional-component gating
│   ├── install_tui.py          # Fullscreen install UI shared by preflight and main bootstrap
│   └── toml_compat.py          # TOML loader shim that prefers stdlib and falls back to vendored code
├── scripts/
│   ├── bootstrap               # Shell entrypoint for managed install and live-state refresh
│   ├── bootstrap-preflight.py  # Fullscreen first-run preflight under stock macOS python3
│   ├── bootstrap.py            # Main managed installer after runtime handoff
│   ├── verify                  # Validates repo shape, shipped public contracts, and live machine drift
│   ├── render-config           # Renders ~/.codex/config.toml from tracked fragments
│   ├── update                  # Installs or refreshes default and enabled optional components
│   ├── component-status        # Reports managed component health
│   └── component-enable        # Enables optional third-party code-navigation integrations
├── codex/
│   ├── AGENTS.md               # Compact shipped Codex startup and operating guidance
│   ├── TOOLING.md              # On-demand continuity, retrieval, navigation, and Git lifecycle guidance
│   └── config/                 # Managed config fragments rendered into ~/.codex/config.toml
├── skills/
│   ├── project-continuity/     # Reusable continuity skill, starter templates, and adoption reference
│   ├── yeet/                   # Explicit terminal Git transaction contract
│   ├── change-impact/          # Affected-consumer and verification-obligation mapping
│   ├── causal-explanation/     # Evidence-calibrated why/how explanations
│   ├── improve-codebase-architecture/ # Architecture deepening and interface review
│   ├── skill-authoring-quality/ # Portable skill governance and audit workflow
│   └── tufte-visualization/    # Evidence-first visualization skill and references
├── bin/                        # Durable wrappers and managed launcher entrypoints
├── shell/
│   ├── zprofile.codex.sh       # Managed zsh login-shell source fragment
│   ├── zshrc.codex.sh          # Managed zsh interactive-shell source fragment
│   ├── bash_profile.codex.sh   # Manual fallback fragment for non-zsh shell wiring
│   └── codex.local.env.example # Starter local shell env overlay copied into a gitignored live file
├── uv/                         # Managed account-wide uv policy rendered to ~/.config/uv/uv.toml
└── launchd/                    # Managed macOS LaunchAgent definitions
```

## Core Control Flows

### Managed Install

```text
tracked repo policy + config fragments + wrappers
    -> Makefile install dispatcher
    -> scripts/bootstrap
    -> stock Python preflight under macOS-shipped python3
    -> existing-config review + Homebrew/package preflight
    -> continue in the same fullscreen installer session
    -> scripts/bootstrap.py under the current Python runtime
    -> managed config adoption + local example files + managed symlinks
    -> managed ~/.config/uv/uv.toml with a seven-day default quarantine and package-specific overrides for the optional jGravelle Munch suite
    -> managed zsh source blocks when supported, with repo-local manual shell fragments otherwise
    -> default managed component install/update
    -> optional jGravelle Munch suite acknowledgement + enablement when chosen
    -> rendered ~/.codex/config.toml
    -> LaunchAgent render
    -> first transcript sync + qmd index refresh
    -> launchctl bootstrap for background sync
    -> final verify
```

`install` is the mechanism that turns tracked repo state into live user-level machine state. A change to config fragments, wrappers, shell hooks, or LaunchAgent behavior is not really installed until `make install` runs successfully.

`Makefile` is part of the public operator surface, not build-only scaffolding. It is the thin dispatcher for `install`, `verify`, `update`, `upgrade`, and `component-status`, while the shell and Python files under `scripts/` and `lib/` hold the actual implementation.

### Verification

```text
repo state + live machine state
    -> scripts/verify
    -> maintenance manifest validation
    -> public doc, skill, and routing-contract validation
    -> secret and local-reference scanning
    -> symlink, shell, config, and LaunchAgent drift checks
    -> default and enabled-optional component health checks
```

`verify` is the guardrail against drift, broken managed state, and accidental leakage of local paths, secrets, or machine-specific assumptions into the public surface. The shipped repo-only path is behavior-first and boundary-first: it validates shipped skills, the slim public `codex/AGENTS.md` and `codex/TOOLING.md` routing surface, manifests, and other public interfaces without hard-freezing every sentence.

### Memory and Retrieval Flow

```text
Codex transcripts + project-memory material
    -> sync-codex-chat-qmd.sh
    -> projected markdown + refreshed retrieval index under ~/.cache/qmd/codex_chat
    -> codex-memory-mcp public MCP surface backed by the internal qmd-codex adapter
    -> bounded bootstrap, explicit topicless recency, and unified typed historical query
```

This subsystem is the default public core. It is built around [@tobi/qmd](https://github.com/tobi/qmd) and exists to give Codex better startup context and retrieval without requiring manual transcript spelunking. The advertised historical surface is deliberately small: `recent_session` handles only explicit topicless last-conversation questions, while `query` accepts one to three typed `lex`, `vec`, or `hyde` searches and is followed by bounded `get` or `multi_get` evidence. The older three search names remain hidden compatibility aliases for cached clients.

Routing preserves evidence authority: current repository and Git questions stay on the current checkout and refs; explicitly named past projects, decisions, methods, and discussions route to memory before broad scans of an unrelated checkout. Exact names and identifiers take a fast lexical path without reranking, followed by one bounded source retrieval. Semantic search and reranking are the single allowed broadened pass when lexical evidence misses. Retrieved historical evidence is sufficient unless the user asks about the current live state, so Codex does not reopen old filesystem paths merely to corroborate it. Retrieval latency and payload are distinct from the model's whole-turn synthesis cost.

Built-in Codex memories are disabled by the base config. Retained app-managed files under `~/.codex/memories/` are historical generated state, not an operator-facing retrieval lane or an implicit project input. The shipped public contract keeps required rules in `codex/AGENTS.md` or checked-in repo docs, uses the QMD-backed `memory` MCP surface for bootstrap and transcript retrieval, and treats `/memories` plus `codex/config/90-local.toml` as the explicit user-owned opt-in controls.

When project framing files exist in a target repo, the transcript-sync path prefers `PROJECT_CONTINUITY.md` as the durable product frame before lower-level handoff details so startup context stays anchored on purpose instead of only the latest execution state.

### Optional jGravelle Munch MCP Suite Flow

```text
user requests optional indexed code, docs, and data navigation
    -> scripts/component-enable jcodemunch-mcp
    -> retrieve the current upstream terms text once
    -> require explicit accept at enable time
    -> validate the latest compatible upstream uv runner invocations under <2.0
    -> render one local overlay that wires the three MCP servers together
```

The upstream [@jgravelle/jcodemunch-mcp](https://github.com/jgravelle/jcodemunch-mcp), [@jgravelle/jdocmunch-mcp](https://github.com/jgravelle/jdocmunch-mcp), and [@jgravelle/jdatamunch-mcp](https://github.com/jgravelle/jdatamunch-mcp) projects stay a separate license boundary throughout this flow. Optional enablement fails closed if the managed `<2.0` compatibility contract for any suite member cannot be satisfied.

## Public Understanding Surface

`codex-spine` deliberately keeps its public operating surface small.

- `README.md` and `Makefile` are the public operator entrypoints; common commands dispatch into `scripts/`.
- `codex/AGENTS.md` is the compact startup and operating policy for installed public use.
- `codex/TOOLING.md` is the public on-demand guide for continuity, memory retrieval, indexed navigation, and managed Git lifecycle.
- The seven declared trees under `skills/` are reusable public skill payloads.
- `bin/codex-git-safe`, its public library modules, and the bundled Gitea helpers implement the `yeet` terminal transaction. GitHub review mechanics remain connector-owned and can be recorded through `review-import`.
- Repo-specific release, review, and local Git workflows stay outside the installed operating contract unless this repo documents them directly.

That split is intentional. The public repo should explain installed product behavior and reusable workflow patterns without turning its docs into project-management history.

## Public Runtime Payload

Some shipped runtime pieces are easy to miss if you only look at the top-level wrappers.

- `lib/install_tui.py` is shared by `scripts/bootstrap-preflight.py` and `scripts/bootstrap.py` so the interactive install stays in one fullscreen UI model across the handoff from stock macOS Python to the selected runtime.
- `lib/toml_compat.py` and `lib/_vendor/tomllib/` are part of the public runtime contract because `codex-spine` still needs TOML parsing to work on stock macOS Python versions that do not ship stdlib `tomllib`.
- `shell/zprofile.codex.sh` and `shell/zshrc.codex.sh` are the managed zsh integration fragments; `shell/bash_profile.codex.sh` and `shell/codex.local.env.example` are shipped manual fallback surfaces for users who want shell integration without the managed zsh path.
- The repo-local `shell/codex.local.env` and `codex/config/90-local.toml` files are intentionally local-only live overlays copied from shipped examples when missing; they are not part of the tracked public payload.

## Public Skill Payload

The shipped `skills/` tree is part of the public product surface, not incidental example content.

### `skills/project-continuity/`

This tree ships a reusable continuity workflow for long-lived repos:

- `SKILL.md` defines the continuity model itself: durable project authority, volatile handoff, startup packet shape, and self-hosting rules.
- `assets/PROJECT_CONTINUITY.template.md`, the legacy and adopted checkpoint templates/model, `assets/AGENTS.fragment.md`, and `assets/ARCHIVE_NOTE.template.md` provide merge-preserving starter artifacts for repositories that adopt that continuity structure.
- `references/adoption-procedure.md` is the direct procedure for deciding whether a repository should remain `repo-native-only`, use a local overlay, or adopt the packet in-tree.
- `scripts/audit-continuity.py` is a read-only structural, state-anchor, redaction, and pointer audit; `agents/openai.yaml` owns UI metadata and implicit invocation policy.

This skill is reusable scaffolding. It does not mean `codex-spine` itself owns the downstream repo's continuity files.

### `skills/yeet/`

`validated registered task → commit → publish or integrate → prove → retire`

This explicit-only tree ships that terminal transaction contract:

- `SKILL.md` limits `yeet` to the operator's exact instruction and forbids it
  from running product tests or broad gates.
- `bin/codex-git-safe` and `lib/codex_git_safe.py` own the resumable managed
  worktree, commit, review/integration, proof, checkpoint, and retirement flow.
- The bundled Gitea helpers provide a direct hosted-review lane; GitHub review
  creation remains with the installed connector and can be imported into the
  lifecycle record.

Finite ordered implementation work uses Codex's native plan surface. The
retired `multi-step` controller and its recursive packet model do not ship.

### Reasoning and authoring skills

- `skills/change-impact/` maps crossed boundaries, consumers, load-bearing
  assumptions, and finite verification obligations.
- `skills/causal-explanation/` separates observations, causal inference,
  alternatives, and gaps for established why/how questions.
- `skills/improve-codebase-architecture/` finds or implements architecture
  deepening, terminology, symmetry, and interface opportunities.
- `skills/skill-authoring-quality/` audits skill routing, packet structure,
  prompt economy, distribution, provenance, and collision safety.

Adapted packets retain self-contained upstream notices and are indexed in
`THIRD_PARTY_NOTICES.md`.

### `skills/tufte-visualization/`

This tree ships an evidence-first visualization workflow for charts, dashboards, analytical figures, visual tables, maps, and other decision-grade displays:

- `SKILL.md` defines the comparison-first workflow, integrity rules, rendering checks, and delivery contract.
- `agents/openai.yaml` provides the user-facing invocation metadata.
- `references/` carries focused guidance for visual principles, chart selection, uncertainty, accessibility, critique, captions, text equivalents, and source provenance.

This skill is guidance for producing or reviewing evidence displays. It does not add a charting runtime or data source by itself.

## Key Invariants

- [@tobi/qmd](https://github.com/tobi/qmd) and memory are part of the default public core.
- Public skills ship under `skills/` as reusable scaffolding and guidance; the actual continuity packet files still live in the repo being worked in.
- The public skill payload is intentionally declared and verifier-owned: `project-continuity`, `yeet`, `change-impact`, `causal-explanation`, `improve-codebase-architecture`, `skill-authoring-quality`, and `tufte-visualization`, plus only their declared resources. The retired `multi-step` packet is prohibited.
- `memory` is the only public MCP surface for transcript retrieval; `qmd-codex` remains an internal adapter.
- Built-in Codex memories remain disabled by default; retained generated state under `~/.codex/memories/` is historical evidence only, and an intentional user-owned opt-in belongs in `codex/config/90-local.toml` rather than project guidance.
- The optional jGravelle Munch MCP suite is optional but first-class.
- The shipped `codex/TOOLING.md` surface covers continuity, memory, indexed navigation, and managed Git lifecycle; release governance remains out of scope for the installed operating contract.
- Managed shell-dotfile mutation is only tested for `zsh`. Non-`zsh` shells should receive a warning and a core-only install rather than silent best-effort mutation, with the shipped shell fragments kept available for explicit manual wiring.
- launchd, shell, and config surfaces must remain free of personal paths and machine-specific service assumptions.
- `MAINTAINED_COMPONENTS.toml` owns shipped acquisition and update shape; public runtime behavior should not depend on export-control metadata.
- Managed update paths must fail closed when post-update health is red instead of accepting version-only success.

## Security and Trust Boundaries

- `codex-spine` is a user-space workstation tool. It does not require root, install privileged daemons, or expose a network listener.
- Tracked repo content and generated public config are intended to remain secret-free.
- Transcript sync and project-memory material are stored locally under the [@tobi/qmd](https://github.com/tobi/qmd)-backed cache at `~/.cache/qmd/codex_chat`; users should treat that store as sensitive when transcripts contain sensitive material.
- Optional third-party artifacts and retrieved upstream terms text are external inputs. The repo reduces risk through compatibility constraints and explicit opt-in gating, not through sandboxing.

## Storage and Update Model

- Tracked configuration fragments under `codex/config/` are rendered into `~/.codex/config.toml`.
- Existing unmanaged Codex settings can be adopted into `codex/config/80-adopted.toml`, while machine-specific local overrides live in `codex/config/90-local.toml`.
- `bootstrap` also copies `shell/codex.local.env.example` into a gitignored `shell/codex.local.env` when the local env overlay is missing.
- Live integration points are mostly symlink-based so tracked repo changes can propagate through `bootstrap`.
- LaunchAgent state is managed from tracked plist definitions and reloaded during bootstrap.
- Repo-local `.state/` stores optional component enablement records.
- `update` refreshes default components and any already-enabled optional components to the repo’s managed versions or compatibility constraints and stops with an error if the component remains unhealthy afterward.
- `upgrade` is the explicit repo self-update path: it refuses dirty checkouts, fetches release tags, checks out the newest `vX.Y.Z` tag from the selected remote, then reruns install, update, and verify from that upgraded tree.
- Exported skills, docs, and verifier gates are expected to agree as one shipped understanding surface. When they drift, `scripts/verify.py --repo-only` is supposed to catch it before release.

## Why This Doc Exists

`README.md` should explain what `codex-spine` is, how to start, and the core operator workflow for this intentionally simple project. `SECURITY.md` should describe the actual security footprint. `ARCHITECTURE.md` exists for the next level down: how the system is shaped, where responsibilities live, and which invariants maintainers should preserve.

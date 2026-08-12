# Self-Hosting And Git Signposts

Use this reference only when continuity work changes startup docs, tooling guides, skill bodies or assets, generated config, launchers, managed links, exports, or adjacent Git topology.

## Self-Hosting

- Update canonical source, generated consumers, validation, and shipped guidance together.
- Require every live understanding surface to have exactly one canonical owner. Source paths, symlinks, generated consumers, configuration entries, installed copies, and exported copies must resolve coherently to that owner.
- Verify the authoring source and each published surface users inherit.
- Treat installed copies and plugin caches as immutable when their canonical source lives elsewhere; adapt in repo-owned wrappers, overlays, or verifiers.
- Re-read changed startup or routing surfaces in the active thread and state whether current threads, new shells, app restarts, or reboots are affected. Prove instruction discovery and precedence in a fresh run; for skill updates, use a fresh conversation for trigger tests and restart only if the update does not appear.
- Make verifiers fail on behavior contracts, boundary leaks, or shipped-interface drift. Keep exact prose and size budgets advisory unless they define a real interface.

## Git Topology

- Record the authoritative base, protected refs, adjacent checkouts, and the repository's explicitly declared isolation, publication, and closeout semantics.
- Route routine lifecycle mechanics through the installed local Git control plane or a tooling guide the repository explicitly owns. Do not infer mechanics from this reference.
- For review-only work, report Git posture without mutating it.
- When parallel work or scratch state affects the project, signpost which checkout is canonical and which surfaces are preserved, disposable, or downstream.

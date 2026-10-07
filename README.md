# codex-spine

Seven agent skills for work that goes badly when a model freestyles: tracing why something
behaves the way it does, mapping what a change will touch, simplifying architecture, judging
performance tradeoffs with measurements, editing serious prose, writing good skills, and
designing honest charts.

Each skill is a plain folder with a `SKILL.md` and optional references, so it works in Codex and
in other agents that read the same format.

## Skills

| Skill | Use it to |
| --- | --- |
| [`causal-explanation`](skills/causal-explanation) | explain, with sources, why existing behavior, an incident, or a past design decision is the way it is |
| [`change-impact`](skills/change-impact) | map affected consumers and verification obligations before changing interfaces, schemas, config, or lifecycle behavior |
| [`improve-codebase-architecture`](skills/improve-codebase-architecture) | find evidence-backed simplification, module deepening, and naming fixes |
| [`performance-tradeoff`](skills/performance-tradeoff) | measure and judge latency, throughput, memory, and capacity tradeoffs on real hardware |
| [`prose-quality`](skills/prose-quality) | draft, revise, or review writing where editorial quality is part of the deliverable |
| [`skill-authoring-quality`](skills/skill-authoring-quality) | audit or write agent skills and prompt packets for routing, placement, and economy |
| [`tufte-visualization`](skills/tufte-visualization) | create or critique charts, dashboards, and evidence-heavy figures |

## Install

Copy or symlink the skill folders you want into your agent's skills directory:

- Codex: `~/.agents/skills/` (or `~/.codex/skills/`)
- Claude Code: `~/.claude/skills/`

```sh
git clone https://github.com/macintog/codex-spine.git
ln -s "$PWD/codex-spine/skills/change-impact" ~/.agents/skills/change-impact
```

Restart the agent or open a new session so it discovers the skill.

## History

Releases up to v0.5.7 also shipped a managed Codex environment for macOS: transcript memory,
code and document indexing, LaunchAgents, and a Git closeout runtime. That environment was
retired in October 2026; those releases remain available at their tags.

## License

MIT, see [LICENSE](LICENSE). Adapted skills keep their upstream MIT notices; see
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

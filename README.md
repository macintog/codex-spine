# codex-spine

Five agent skills, plus two standing instructions, for work that goes badly when a model freestyles.
Each skill is a plain folder with a `SKILL.md`, so it works in Codex and in other agents that read
the same format.

## Skills

| Skill | Use it to |
| --- | --- |
| [`chart-integrity`](skills/chart-integrity) | create or critique charts and dashboards whose comparisons someone will act on |
| [`improve-codebase-architecture`](skills/improve-codebase-architecture) | audit a codebase for simplification: shallow modules, rules implemented twice, sibling paths that disagree |
| [`performance-tradeoff`](skills/performance-tradeoff) | judge benchmark and resource claims: cold vs warm runs, async timing, overlapping memory counters |
| [`prose-quality`](skills/prose-quality) | edit or review writing without changing claim strength, and remove AI-sounding patterns |
| [`skill-audit`](skills/skill-audit) | prune a skill to what changes behavior, check routing overlap, and vet third-party skills before installing |

## Standing instructions

Two tasks did better as a few always-loaded lines than as skills, because they come up in ordinary
work where a skill would never be triggered. Paste them into `AGENTS.md`, `CLAUDE.md`, or your
agent's global instructions:

```markdown
- When explaining why existing code, behavior, an incident, or a past decision
  is the way it is: code and runtime behavior establish mechanism, not motive.
  Check history (`git log -S`/`-L`, blame, linked PRs/issues, design docs,
  session transcripts) before attributing intent; cite the source for any
  stated reason, label the rest as inference, and say plainly when the
  rationale is unrecorded. For incidents and regressions, name enabling
  conditions as well as the trigger; timing alone is not cause.
- When a change touches a shared contract (function behavior, CLI output,
  config/env key, file or state format, path, hook, schema): find consumers by
  literal strings as well as symbols (other scripts and repos, symlinked
  installs, settings/hook/scheduler entries, data already on disk) and state
  the scope searched. Same signature can still break callers (defaults, key
  absent vs false/null, stdout cleanliness, interpreter version). For persisted
  formats, check old data with new code and new data with old code. For each
  real consumer, say whether it fails loudly or silently and the cheapest check
  that would show it; a passing test clears only the inputs and runtime it ran.
  Report reachable risks only.
```

## How these were chosen

Each candidate went through a three-arm blind test on one model (Claude Opus 5.5): three tasks per
skill, each with a planted trap, run with the long original skill, with a short rewrite, and with no
guidance, then ranked by independent judges that did not know which was which. The short versions
placed first in most tasks; the long originals often placed last because their ceremony leaked into
the answers. What is published is what won. That is a small sample on a single model, so treat it as
evidence for these versions, not a benchmark.

Two earlier skills, `causal-explanation` and `change-impact`, lost to two plain lines and became the
standing instructions above. `yeet` and `project-continuity` were retired with the managed
environment described under History.

## Install

Copy or symlink the skill folders you want into your agent's skills directory:

- Codex: `~/.agents/skills/` (or `~/.codex/skills/`)
- Claude Code: `~/.claude/skills/`

```sh
git clone https://github.com/macintog/codex-spine.git
mkdir -p ~/.agents/skills
ln -s "$PWD/codex-spine/skills/chart-integrity" ~/.agents/skills/chart-integrity
```

For Claude Code, use `~/.claude/skills` in the last two lines instead.

Restart the agent or open a new session so it discovers the skill.

## History

Releases up to v0.5.7 also shipped a managed Codex environment for macOS: transcript memory, code and
document indexing, LaunchAgents, and a Git closeout runtime. That environment was retired in October
2026; those releases remain available at their tags.

## License

MIT, see [LICENSE](LICENSE). Adapted skills keep their upstream MIT notices; see
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

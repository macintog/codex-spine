# Checkpoint

## Current Focus

Get the first standalone `codex-spine` release candidate ready for clean-macOS validation, starting with a clean macOS 15.7.4 install.

## Why It Matters

The product boundary is only real once the exported repo can stand on its own. The next hard gate is not more governance work; it is proving that the standalone repo can bootstrap, verify, render coherent config, run transcript sync, and handle optional `jcode` enablement responsibly.

## Validation Gates

1. clean macOS 15.7.4
2. dirty macOS 15.7.4
3. clean macOS 26.3.1
4. dirty macOS 26.3.1

## Release Path

- Pre-GM iteration happens on private Gitea.
- GitHub is reserved for the first GM-quality public push.
- `CHANGELOG.md` starts with release-candidate history here and must stay current before the public launch.

## Next Safe Step

Run the standalone repo through the first clean 15.7.4 bootstrap and verify pass, then close the gaps that QA exposes before expanding the matrix.

# QA Matrix

Use this checklist for release-candidate validation before any public GitHub push.

## Order

1. clean macOS 15.7.4
2. dirty macOS 15.7.4
3. clean macOS 26.3.1
4. dirty macOS 26.3.1

## Per-Image Checklist

- fresh checkout or known starting state
- `make bootstrap` succeeds
- `make verify` succeeds
- rendered `~/.codex/config.toml` is coherent and private-path free
- shell integration is acceptable
- launchd transcript sync is present and healthy
- QMD and memory work end to end
- `./scripts/component-enable jcode` succeeds with fetched-term acknowledgement
- `make update` behaves deterministically after install

## Notes To Capture

- exact macOS version
- clean or dirty state
- anything preinstalled that changed behavior
- failures, recovery steps, and whether the fix belongs in docs or code

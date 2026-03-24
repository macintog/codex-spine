# macOS-first shell wiring. Linux analog: source a similar fragment from ~/.bash_profile or ~/.profile.
export PATH="$HOME/.local/bin:$PATH"

CODEX_SPINE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
if [ -f "$CODEX_SPINE_ROOT/shell/codex.local.env" ]; then
  . "$CODEX_SPINE_ROOT/shell/codex.local.env"
fi

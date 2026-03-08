# macOS-first shell wiring. Linux analog: source a similar fragment from ~/.profile.
export PATH="$HOME/.local/bin:$PATH"

CODEX_SPINE_ROOT="${${(%):-%x}:A:h:h}"
if [ -f "$CODEX_SPINE_ROOT/shell/codex.local.env" ]; then
  . "$CODEX_SPINE_ROOT/shell/codex.local.env"
fi

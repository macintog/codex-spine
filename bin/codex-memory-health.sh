#!/bin/bash
set -euo pipefail

LAUNCHER="${HOME}/.local/bin/codex-memory-mcp-launcher"
TARGET_CWD="${1:-$PWD}"

if [[ ! -x "$LAUNCHER" ]]; then
  echo "ERROR: missing memory launcher at $LAUNCHER" >&2
  exit 1
fi

python3 - "$LAUNCHER" "$TARGET_CWD" <<'PY'
import json
import subprocess
import sys

launcher, cwd = sys.argv[1], sys.argv[2]
requests = [
    {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "codex-memory-health", "version": "0.1.0"},
        },
    },
    {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": {
            "name": "bootstrap_context",
            "arguments": {
                "cwd": cwd,
                "refresh_if_stale": False,
                "max_recent_sessions": 1,
            },
        },
    },
]
payload = "".join(json.dumps(item, separators=(",", ":")) + "\n" for item in requests)
result = subprocess.run(
    [launcher],
    input=payload,
    text=True,
    capture_output=True,
    check=False,
    timeout=30,
)
if result.returncode != 0:
    detail = (result.stderr or "").strip() or (result.stdout or "").strip() or f"exit {result.returncode}"
    print(f"ERROR: memory launcher failed: {detail}", file=sys.stderr)
    sys.exit(1)

responses: dict[int, dict] = {}
for raw_line in result.stdout.splitlines():
    line = raw_line.strip()
    if not line:
        continue
    try:
        message = json.loads(line)
    except json.JSONDecodeError:
        continue
    message_id = message.get("id")
    if isinstance(message_id, int):
        responses[message_id] = message

initialize = responses.get(1)
if not initialize or "result" not in initialize:
    print("ERROR: memory launcher did not return initialize response", file=sys.stderr)
    sys.exit(1)

call = responses.get(2)
if not call:
    print("ERROR: memory launcher did not return bootstrap_context response", file=sys.stderr)
    sys.exit(1)
if "error" in call:
    print(f"ERROR: memory bootstrap_context RPC failed: {call['error']}", file=sys.stderr)
    sys.exit(1)

tool_result = call.get("result") or {}
if tool_result.get("isError"):
    detail = ""
    content = tool_result.get("content") or []
    if content and isinstance(content[0], dict):
        detail = str(content[0].get("text", "")).strip()
    print(f"ERROR: memory bootstrap_context returned error: {detail or 'unknown'}", file=sys.stderr)
    sys.exit(1)

structured = tool_result.get("structuredContent") or {}
summary = structured.get("summary")
if not isinstance(summary, str) or not summary.strip():
    print("ERROR: memory bootstrap_context returned no summary", file=sys.stderr)
    sys.exit(1)

project_key = structured.get("project_key", "unknown")
last_sync_utc = structured.get("last_sync_utc", "")
print(f"project_key={project_key} last_sync_utc={last_sync_utc}")
PY

#!/usr/bin/env bash

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
bridge_file="${1:-$repo_root/.bridge/bridge.md}"
log_file="${2:-$repo_root/.bridge/monitor.log}"
state_file="${3:-$repo_root/.bridge/codex-monitor.state.json}"

exec python3 "$repo_root/.bridge/codex_bridge_monitor.py" "$bridge_file" "$log_file" "$state_file"

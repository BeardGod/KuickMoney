#!/bin/bash
# Launches the REA MCP server used by the reverse-engineering skill.
# Points REA at a Ghidra install when one is present (installed by
# session-start.sh in cloud sessions, or GHIDRA_INSTALL_DIR set locally).
set -euo pipefail

REA_VERSION="6.5.0"
GHIDRA_HOME="${REA_GHIDRA_HOME:-$HOME/.cache/rea/ghidra}"

if [ -z "${GHIDRA_INSTALL_DIR:-}" ] && [ -x "$GHIDRA_HOME/current/ghidraRun" ]; then
  export GHIDRA_INSTALL_DIR="$GHIDRA_HOME/current"
fi

exec npx -y "rea-agents@$REA_VERSION" mcp

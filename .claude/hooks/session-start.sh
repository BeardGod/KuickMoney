#!/bin/bash
# Prepares the reverse-engineering skill (REA) in Claude Code cloud sessions:
# caches the pinned rea-agents package and installs a pinned Ghidra release for native analysis.
set -uo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

REA_VERSION="6.5.0"
# REA 6.5.0 supports Ghidra 12.1.x. To upgrade, change all three values.
GHIDRA_VERSION="12.1.4"
GHIDRA_URL="https://github.com/NationalSecurityAgency/ghidra/releases/download/Ghidra_12.1.4_build/ghidra_12.1.4_PUBLIC_20260921.zip"
GHIDRA_SHA256="ddac49f903da9d5bac833e5cc79395098b9c33cfd3279be5f31bd00387d2d4db"
GHIDRA_HOME="${REA_GHIDRA_HOME:-$HOME/.cache/rea/ghidra}"

log() { echo "[rea-setup] $*" >&2; }

# 1. Cache the REA package so the MCP server starts without a download.
if npx -y "rea-agents@$REA_VERSION" --version >/dev/null 2>&1; then
  log "rea-agents $REA_VERSION ready"
else
  log "could not fetch rea-agents $REA_VERSION from npm; REA tools will be unavailable"
fi

# 2. Ghidra (optional, needs JDK 21+). The release is pinned by URL and
# SHA-256 because the GitHub API is not reachable from cloud sessions, while
# release downloads from github.com are.
if [ -x "$GHIDRA_HOME/current/ghidraRun" ]; then
  log "Ghidra already installed at $GHIDRA_HOME/current"
elif ! command -v java >/dev/null 2>&1; then
  log "skipping Ghidra: no Java runtime"
else
  tmp=$(mktemp -d)
  log "downloading Ghidra $GHIDRA_VERSION"
  if curl -fsSL --max-time 900 -o "$tmp/ghidra.zip" "$GHIDRA_URL" \
    && echo "$GHIDRA_SHA256  $tmp/ghidra.zip" | sha256sum -c --quiet - \
    && mkdir -p "$GHIDRA_HOME" \
    && unzip -q -o "$tmp/ghidra.zip" -d "$GHIDRA_HOME"; then
    ln -sfn "$GHIDRA_HOME/ghidra_${GHIDRA_VERSION}_PUBLIC" "$GHIDRA_HOME/current"
    log "Ghidra installed at $GHIDRA_HOME/current"
  else
    log "Ghidra download or checksum failed; native analysis falls back to objdump"
  fi
  rm -rf "$tmp"
fi

if [ -n "${CLAUDE_ENV_FILE:-}" ] && [ -x "$GHIDRA_HOME/current/ghidraRun" ]; then
  echo "export GHIDRA_INSTALL_DIR=\"$GHIDRA_HOME/current\"" >> "$CLAUDE_ENV_FILE"
fi
exit 0

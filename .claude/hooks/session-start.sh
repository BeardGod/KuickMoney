#!/bin/bash
# Prepares the reverse-engineering skill (REA) in Claude Code cloud sessions:
# caches the pinned rea-agents package and, when GitHub downloads are allowed
# by the environment's network policy, installs Ghidra for native analysis.
set -uo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

REA_VERSION="6.5.0"
GHIDRA_SERIES="12.1"   # REA 6.5.0 supports Ghidra 12.1.x
GHIDRA_HOME="${REA_GHIDRA_HOME:-$HOME/.cache/rea/ghidra}"

log() { echo "[rea-setup] $*" >&2; }

# 1. Cache the REA package so the MCP server starts without a download.
if npx -y "rea-agents@$REA_VERSION" --version >/dev/null 2>&1; then
  log "rea-agents $REA_VERSION ready"
else
  log "could not fetch rea-agents $REA_VERSION from npm; REA tools will be unavailable"
fi

# 2. Ghidra (optional, needs JDK 21+ and access to github.com).
if [ -x "$GHIDRA_HOME/current/ghidraRun" ]; then
  log "Ghidra already installed at $GHIDRA_HOME/current"
elif ! command -v java >/dev/null 2>&1; then
  log "skipping Ghidra: no Java runtime"
else
  release_json=$(curl -fsS --max-time 15 \
    "https://api.github.com/repos/NationalSecurityAgency/ghidra/releases?per_page=20" 2>/dev/null || true)
  url=$(printf '%s' "$release_json" \
    | grep -o "\"browser_download_url\": *\"[^\"]*ghidra_${GHIDRA_SERIES}[^\"]*_PUBLIC_[0-9]*\.zip\"" \
    | head -1 | sed 's/.*: *"\(.*\)"/\1/')
  if [ -z "$url" ]; then
    log "skipping Ghidra: GitHub releases not reachable (allow github.com, api.github.com and objects.githubusercontent.com in the environment's network settings)"
  else
    tmp=$(mktemp -d)
    log "downloading $(basename "$url")"
    if curl -fsSL --max-time 900 -o "$tmp/ghidra.zip" "$url" \
      && mkdir -p "$GHIDRA_HOME" \
      && unzip -q "$tmp/ghidra.zip" -d "$GHIDRA_HOME"; then
      dir=$(find "$GHIDRA_HOME" -maxdepth 1 -type d -name "ghidra_${GHIDRA_SERIES}*" | sort | tail -1)
      ln -sfn "$dir" "$GHIDRA_HOME/current"
      log "Ghidra installed at $dir"
    else
      log "Ghidra download failed; native analysis will be unavailable"
    fi
    rm -rf "$tmp"
  fi
fi

if [ -n "${CLAUDE_ENV_FILE:-}" ] && [ -x "$GHIDRA_HOME/current/ghidraRun" ]; then
  echo "export GHIDRA_INSTALL_DIR=\"$GHIDRA_HOME/current\"" >> "$CLAUDE_ENV_FILE"
fi
exit 0

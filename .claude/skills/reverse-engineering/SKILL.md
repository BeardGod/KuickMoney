---
name: reverse-engineering
description: Use when asked to reverse engineer, decompile, disassemble, or explain how a shipped app, binary, library, APK, Electron/ASAR bundle, .NET assembly, firmware image, website, network capture, or other artifact works without its source code, or to compare builds or rebuild a feature seen in another product. Not for analyzing an ordinary source repository.
---

# Reverse Engineering with REA

## Overview

[REA (Reverse Engineer Anything)](https://github.com/morluto/rea) is an MCP
server and CLI (`rea-agents` on npm) that inspects shipped artifacts and
runtime behavior and returns **Evidence records**. Every conclusion you report
must trace back to an Evidence ID and must say what was observed, what was
inferred, and what is still unknown.

If the question can be answered by reading source code that is already in the
workspace, use normal repository tools and do not use REA.

## 1. Connect (only when needed)

If `mcp__rea__*` tools are already in the session, go straight to step 2. Don't
run diagnostics before every investigation.

**This repository is already set up:**
- `.mcp.json` registers the `rea` server through `.claude/hooks/rea-mcp.sh`,
  which pins `rea-agents@6.5.0`. `.claude/settings.json` enables it.
- In cloud sessions, `.claude/hooks/session-start.sh` caches the package
  and installs Ghidra 12.1.x into `~/.cache/rea/ghidra/current`. Ghidra
  needs github.com to be reachable, which the environment's network policy
  may block. If it isn't installed, use `inspect_with_objdump` (GNU objdump
  is preinstalled) for native disassembly, symbols, and headers. Tell the
  user that pseudocode needs Ghidra, Hopper, or IDA.
- On a local machine, set `GHIDRA_INSTALL_DIR` before starting Claude Code
  to enable Ghidra.

If they are missing:

1. Diagnose without changing anything:
   `npx -y rea-agents@latest doctor --client claude_code --json`
2. Missing or stale registration → show the user the dry-run plan and get
   approval before writing config:
   `npx -y rea-agents@latest setup --client claude_code --dry-run --json`,
   then the same command with `--yes` in place of `--dry-run --json`.
   For a manual registration that only applies to this project:
   `claude mcp add --scope local rea -- npx -y rea-agents@latest mcp`
3. Registration looks correct but no tools appear → the user must restart
   Claude Code. Running setup again won't fix it.
4. A missing engine (Hopper/Ghidra/IDA, JADX, tshark…) only blocks tasks that
   need that engine. Setup never installs Node, Java, Ghidra, IDA, or JADX, so
   don't install unrelated software.

**CLI fallback without MCP** (no native engine needed):
`npx -y rea-agents@latest analyze-javascript-application /abs/path/to/app --json`

For any other blocker, read `references/connection-and-recovery.md`.

## 2. Choose the first tool by target type

| Target the user supplied | First tool |
|---|---|
| ASAR / extracted JS or Electron app | `analyze_javascript_application` (use `detail: "summary"` if large) |
| Native exe/dll/so/dylib or analysis DB | `open_binary`, then `binary_overview` / `analyze_function` |
| Native binary, no Ghidra/Hopper/IDA | `inspect_with_objdump` (`file_headers`, `symbols`, `disassemble`…) |
| ZIP/APK/IPA/MSIX/DMG member inventory | `open_binary`, then `inspect_artifact` |
| Android APK code / classes / methods | `inspect_android_package` |
| .NET (managed PE/CLI) assembly | `inspect_managed_artifact` |
| Firmware image | `inspect_firmware_regions` (`extract_firmware` into a new absolute dir) |
| Go / Rust binary build metadata | `inspect_go_binary` / `inspect_rust_binary` |
| WASM / EVM bytecode | `inspect_wasm_artifact` / `inspect_evm_interface` |
| SQLite DB snapshot | `inspect_sqlite_database` |
| ELF layout, symbols, mitigations | `inspect_binary_layout` |
| Linux core dump | `inspect_recorded_crash` |
| PE resources/icons | `inspect_pe_resources` |
| HAR / SAZ / mitmproxy / qlog capture | `inspect_web_network_capture` |
| pcap | `inspect_pcap_capture` (summary) or `inspect_packet_capture` (fields) |
| Browser page already open by user | `list_browser_targets` |
| Browser actions to perform | `capture_browser_scenario` |
| Running Electron app | `list_electron_targets` (check `inspect_electron_fuses` before trying `--inspect`) |

If a tool you expect isn't advertised, call `binary_session` with `{}` and read
`result.tool_availability` for the reason. Never call an unadvertised tool. If
the user says "my app" without naming it, ask which app. Don't pick one
yourself.

## 3. Start with the summary

- Use the default or summary result first. Make a follow-up call only when a
  specific question is still unanswered, and never repeat an identical call.
- An oversized or truncated result (`resource_constraint`, `resource:
  "transport"`, or a client-truncated preview) → page it with
  `inspect_analysis_view` using the `parent_evidence_id`. Don't re-run the
  analysis and don't parse the preview as JSON.
- Lost the parent ID → `get_evidence_bundle` with `detail: "summary"` and
  filters. To get everything, use `export_evidence_bundle` to a path.
- Once you have a seed (function, module, IPC channel), follow it with
  `trace_application_feature` instead of running broad bidirectional traces.

## 4. Larger investigations

1. Write a checklist of questions and the evidence each one needs.
2. Reuse the existing session and evidence. Don't open duplicate sessions.
3. Trace each question from its entry point through data and state changes to
   its effect. Check the relevant resources and config too, not just code.
   Don't infer behavior from filenames or strings alone.
4. Use runtime observation only when static evidence can't answer the
   question, and limit it to the declared target and actions.
5. Independent questions can go to parallel workers when the user has allowed
   subagents. Give each one a distinct scope and the existing Evidence IDs.
6. Keep a finding ledger: conclusion → Evidence IDs → observed/inferred →
   search boundary → open unknowns.
7. Before finishing, mark each checklist item answered, partial, or
   unresolved. Don't call the investigation complete while items are open.

## 5. Finish

- Explain findings in plain language and cite Evidence IDs. Static analysis
  is never proof that code was executed.
- When asked to rebuild a feature, separate the **observed behavior** from
  **your own design choices**, then implement and test with normal coding
  tools.
- Close native sessions with `close_binary`.

## Reference guides (read only the one you need)

| Topic | File |
|---|---|
| Native binaries, managed assemblies, archives, firmware, NativeAOT, IDA/Ghidra/Hopper | `references/native-and-artifacts.md` |
| ASAR/JS/Electron, module views, feature tracing, version diffs | `references/javascript-applications.md` |
| Android APK declarations, classes, references | `references/android-applications.md` |
| Browser/Electron runtime capture, Fiddler, static↔runtime reconciliation | `references/runtime-observation.md` |
| Evidence paging, comparisons, unknowns, verification | `references/evidence-workflows.md` |
| Missing tools, client blocks, provider setup | `references/connection-and-recovery.md` |

## Common mistakes

| Mistake | Fix |
|---|---|
| Running REA on a repository whose source you already have | Read the source directly |
| Running `setup` again when tools don't show up | Run `doctor`; if registration is fine, restart the client |
| Re-running a big analysis because the output was cut off | Page it with `inspect_analysis_view` and the parent Evidence ID |
| Presenting decompiled pseudocode as the original source | Label it as recovered/inferred and keep the limitations |
| Saying "X never happens" after a bounded search | State the search boundary |
| Using an example app when the target is ambiguous | Ask the user which app |

## Scope and legality

Analyze only artifacts the user owns or is authorized to inspect (their own
apps, licensed software where the license allows it, CTFs, security research,
interoperability work). Don't help bypass DRM, licensing, or anti-cheat
protections, and don't extract credentials from third-party software.

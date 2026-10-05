# Project OpenCode setup

Use the checked-in OpenCode configuration from the repository root. If OpenCode is launched from a nested working directory (for example `storage/wiki`), set `OPENCODE_CONFIG=/home/jolf/Tesla_RAG/.opencode/opencode.json` for that process so it still loads the project MCP server and plugin.

## Codebase Memory MCP

The official `codebase-memory-mcp` executable is project-local at `.opencode/bin/codebase-memory-mcp` and is intentionally gitignored. Its index/config cache and private daemon rendezvous directory are `.opencode/cache/` (also gitignored), selected with the supported `CBM_CACHE_DIR` and `CBM_RUNTIME_DIR` settings in the MCP configuration. To provision the executable on another Linux x86-64 host, download the official v0.11.0 portable archive, verify its official SHA-256, extract its executable into `.opencode/bin/`, and mark it executable:

```sh
curl -fL -o /tmp/codebase-memory-mcp-linux-amd64-portable.tar.gz \
  https://github.com/DeusData/codebase-memory-mcp/releases/download/v0.11.0/codebase-memory-mcp-linux-amd64-portable.tar.gz
printf '%s  %s\n' 1f9e8293eb2bc5c05cfa27a7e8fc033da6d729ffad525ccfcdaa3fd606306683 /tmp/codebase-memory-mcp-linux-amd64-portable.tar.gz | sha256sum -c -
tar -xzf /tmp/codebase-memory-mcp-linux-amd64-portable.tar.gz -C .opencode/bin
chmod +x .opencode/bin/codebase-memory-mcp
```

The portable build is needed on older Linux distributions; the standard build requires a newer glibc. The MCP server is configured in `opencode.json` with an absolute command path for this checkout. Update that path if the checkout moves.

Before using Codebase Memory, follow the installed `skills/codebase-memory-mcp/SKILL.md`. It describes a code structure graph, not source-of-truth facts. Keep `storage/wiki/` out of indexing: Wiki compilation uses its own source retrieval and article provenance. Only call `list_projects` or `index_status` unless the user has explicitly approved indexing the exact repository path. Do not perform ADR mutations.

## Wiki compiler agent

Use the built-in `plan` agent for Wiki compilation. The runner uses the official client with its default agent instructions, in a Bubblewrap filesystem namespace. Only system libraries, an independent CLI profile, and two approved input copies are mounted. Repository files, secrets, host process environments, and the host SSH agent are unavailable. The source instructions, relevant articles, both verbatim canon files, and output contract are supplied as attachments. The runner never passes `--auto`.

Restrictive agent/tool configuration returned FreeTierError HTTP 403, while the same model answered through the standard client. The isolated standard client completed a live pilot: three public posts, five extracted fact groups, and three updated articles, with zero reported cost and no Codex calls. One editorial wording was corrected during review. A repeated run made zero provider calls and left all articles unchanged. MiMo is the extraction and merge default; Nemotron and LongCat are fallbacks. Existing articles use exact text patches rather than regeneration of the whole article. Provider unavailability is recorded separately from account quota.

Compilation requires Linux, `bubblewrap`, and an installed OpenCode executable on PATH. The isolated client exposes Codebase Memory with `--tool-profile=analysis`; indexing and other mutation tools are unavailable. Its cache is separate from the checkout index. This code inspection MCP is not a historical-fact database, and it does not replace the Wiki source retrieval pipeline.

LongCat now receives the requested stage effort through the official `--variant low|medium` flag. The current official catalog exposes no variants for MiMo or Nemotron; the runner does not claim that those models honor the requested effort. A larger extraction batch is being evaluated in a separate ledger before changing the main queue.

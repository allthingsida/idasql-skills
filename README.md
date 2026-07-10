# idasql-skills

Claude Code, Codex, and Cursor plugin packaging for [idasql](https://github.com/allthingsida/idasql) — a [live SQL](https://github.com/0xeb/libxsql) interface to IDA Pro databases.

## Prerequisites

- **IDA Pro** installed with IDA's directory in your PATH
- **idasql** from [Releases](https://github.com/allthingsida/idasql/releases) placed next to IDA
- Verify: `idasql -h`

## Installation

### Claude Code

```bash
/plugin marketplace add allthingsida/idasql-skills
```

### Codex

Use the plugin packaging, not a flat copy into `~/.codex/skills`. The plugin path preserves the `idasql` namespace so generic skill names like `xrefs`, `data`, and `types` do not collide with other skills.

#### Home-local install

1. Clone this repo anywhere temporary:

```bash
git clone https://github.com/allthingsida/idasql-skills
```

2. Copy the plugin directory into your home plugins folder:

```bash
mkdir -p ~/plugins
cp -R idasql-skills/plugins/idasql ~/plugins/
```

3. Create or update `~/.agents/plugins/marketplace.json` so it contains:

```json
{
  "name": "allthingsida",
  "interface": {
    "displayName": "All Things IDA"
  },
  "plugins": [
    {
      "name": "idasql",
      "source": {
        "source": "local",
        "path": "./plugins/idasql"
      },
      "policy": {
        "installation": "AVAILABLE",
        "authentication": "ON_INSTALL"
      },
      "category": "Reverse Engineering"
    }
  ]
}
```

4. Restart Codex.

The Codex plugin manifest lives at `plugins/idasql/.codex-plugin/plugin.json`, and the skills live under `plugins/idasql/skills/`.

#### Repo-local install

If you want to test directly from a checkout, keep the repo where it is and use the bundled marketplace file at `.agents/plugins/marketplace.json`. Codex should resolve `./plugins/idasql` relative to the repo root.

### Cursor

Prefer the Cursor plugin packaging so skills stay under the `idasql` namespace. The Cursor manifest lives at `plugins/idasql/.cursor-plugin/plugin.json`. The repo marketplace manifest is `.cursor-plugin/marketplace.json`.

#### Local plugin install

1. Clone this repo (or use an existing checkout):

```bash
git clone https://github.com/allthingsida/idasql-skills
```

2. Copy or symlink the plugin into Cursor's local plugins folder:

```bash
# macOS / Linux
mkdir -p ~/.cursor/plugins/local
ln -s "$(pwd)/idasql-skills/plugins/idasql" ~/.cursor/plugins/local/idasql

# Windows (PowerShell, as Administrator for symlink — or copy instead)
New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\.cursor\plugins\local" | Out-Null
Copy-Item -Recurse -Force .\idasql-skills\plugins\idasql "$env:USERPROFILE\.cursor\plugins\local\idasql"
```

3. Restart Cursor, or run **Developer: Reload Window**.
4. Confirm skills appear under **Customize** (or invoke them from chat).

#### Team marketplace

On Cursor Teams/Enterprise, import this repository as a team marketplace via **Dashboard → Plugins → Add Marketplace** (or Import from Repo). The root `.cursor-plugin/marketplace.json` lists the `idasql` plugin under `plugins/idasql`.

#### Flat skills fallback

Flat installs into `~/.cursor/skills` are possible, but only if you manually rename every skill with an `idasql-` prefix (for example `idasql-connect`, `idasql-xrefs`) to avoid collisions with other skills named `data`, `types`, etc. Plugin-based install is preferred.

#### MCP in Cursor

IDASQL MCP is database-bound — start a server for the database you want to analyze, then point Cursor at its SSE URL:

```bash
idasql -s database.i64 --mcp 9500
```

Add to user `~/.cursor/mcp.json` or project `.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "idasql": {
      "url": "http://127.0.0.1:9500/sse"
    }
  }
}
```

A template lives at `plugins/idasql/mcp.json.example`. The MCP tool is `idasql_query`. When MCP is not configured, the `connect` skill prefers Shell (`idasql -q`) or HTTP `POST /query`.

## Compatibility

- `SKILL.md` is the canonical skill contract and remains the source of truth.
- Per-skill Codex UI metadata lives in each skill's optional `agents/openai.yaml` and does not replace `SKILL.md`.
- Claude, Codex, and Cursor plugin packaging live side by side so this repo can support all three without renaming the underlying skills.
- Claude-only frontmatter keys (for example `allowed-tools`) are ignored by Cursor and Codex.

## Skills

| Skill | Description | When to Use |
|-------|-------------|-------------|
| `connect` | Connection, CLI, HTTP, UI context, routing index | Starting a session, CLI options, HTTP server, pragmas |
| `disassembly` | Functions, segments, instructions, blocks | Querying disassembly, instruction analysis, file generation |
| `data` | Strings, bytes, string cross-references | String search, byte access, binary pattern search |
| `grep` | Named entity search | Find functions, labels, types, and members by pattern |
| `xrefs` | Cross-references and imports | Caller/callee analysis, import queries, reference graphs |
| `decompiler` | Full decompiler reference | Decompilation, ctree AST, local variables, union selection |
| `annotations` | Edit and annotate decompilation | Comments, renames, type application, enum/struct editing |
| `types` | Type system mechanics | Structs, unions, enums, parse_decls, type classification |
| `debugger` | Breakpoints and byte patching | Breakpoint CRUD, byte patching, patch inventory |
| `storage` | Persistent key-value storage (netnode) | Store/retrieve data inside the IDB |
| `idapython` | Python execution via SQL | Execute IDAPython snippets and files |
| `functions` | SQL functions reference | Look up any idasql SQL function signature |
| `analysis` | Analysis workflows and scenarios | Security audits, library detection, advanced SQL patterns |
| `re-source` | Recursive source recovery methodology | Decompilation cleanup, structure recovery, annotation workflows |

## Notes

- The supported Codex and Cursor paths are plugin-based installation. Flat installs into `~/.codex/skills` or `~/.cursor/skills` are possible, but only if you manually rename every skill with an `idasql-` prefix to avoid collisions.
- The plugin-based layout keeps the repo’s natural `idasql` ownership model intact.

## Links

- [idasql](https://github.com/allthingsida/idasql) — CLI and plugin
- [libxsql](https://github.com/0xeb/libxsql) — Core SQLite virtual table framework
- [Cursor plugins](https://cursor.com/docs/plugins) — plugin packaging reference

## Author

**Elias Bachaalany** ([@0xeb](https://github.com/0xeb))

## License

This project and all its contents — including skill definitions, reference documentation, and configuration files — are licensed under the [Mozilla Public License 2.0](LICENSE).

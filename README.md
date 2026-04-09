# idasql-skills

Claude Code and Codex plugin packaging for [idasql](https://github.com/allthingsida/idasql) — a [live SQL](https://github.com/0xeb/libxsql) interface to IDA Pro databases.

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

## Compatibility

- `SKILL.md` is the canonical skill contract and remains the source of truth.
- Per-skill Codex UI metadata lives in each skill's optional `agents/openai.yaml` and does not replace `SKILL.md`.
- Codex plugin packaging lives alongside the Claude packaging so this repo can support both without renaming the underlying skills.

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

- The supported Codex path is plugin-based installation. Flat installs into `~/.codex/skills` are possible, but only if you manually rename every skill with an `idasql-` prefix to avoid collisions.
- The plugin-based layout keeps the repo’s natural `idasql` ownership model intact.

## Links

- [idasql](https://github.com/allthingsida/idasql) — CLI and plugin
- [libxsql](https://github.com/0xeb/libxsql) — Core SQLite virtual table framework

## Author

**Elias Bachaalany** ([@0xeb](https://github.com/0xeb))

## License

This project and all its contents — including skill definitions, reference documentation, and configuration files — are licensed under the [Mozilla Public License 2.0](LICENSE).

# idasql-skills

Claude Code skills for [idasql](https://github.com/allthingsida/idasql) — a [live SQL](https://github.com/0xeb/libxsql) interface to IDA Pro databases, with optional Codex app metadata layered on top.

## Prerequisites

- **IDA Pro** installed with IDA's directory in your PATH
- **idasql** from [Releases](https://github.com/allthingsida/idasql/releases) placed next to IDA
- Verify: `idasql -h`

## Installation

```bash
/plugin marketplace add allthingsida/idasql-skills
```

## Compatibility

- `SKILL.md` is the canonical skill contract and remains the source of truth.
- Codex app metadata lives in each skill's optional `agents/openai.yaml` and does not replace `SKILL.md`.

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

## Links

- [idasql](https://github.com/allthingsida/idasql) — CLI and plugin
- [libxsql](https://github.com/0xeb/libxsql) — Core SQLite virtual table framework

## Author

**Elias Bachaalany** ([@0xeb](https://github.com/0xeb))

## License

This project and all its contents — including skill definitions, reference documentation, and configuration files — are licensed under the [Mozilla Public License 2.0](LICENSE).

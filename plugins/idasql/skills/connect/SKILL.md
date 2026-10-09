---
name: connect
description: "Connect to IDA databases and bootstrap sessions. Use when starting analysis, routing to other skills, setting up CLI/HTTP/MCP connections, or reading and changing IDA configuration options."
allowed-tools:
  - Bash
  - Read
  - Glob
  - Grep
---

## CLI Help (verbatim `idasql --help`)

```
idasql v0.0.19 - SQL interface to IDA databases
Copyright (c) 2024-2026 Elias Bachaalany

Usage: idasql -s <file> [-q <query>] [-f <file>] [-i] [--export <file>]

Options:
  -s <file>            IDA database (.idb/.i64) OR raw binary (.exe/.dll/firmware/etc.)
                       - raw binaries trigger fresh idalib analysis and string-list rebuild
                       - legacy 32-bit .idb files upgrade to .i64 and require an explicit reopen
  --token <token>      Auth token for HTTP server mode (MCP has no auth)
  -q <sql>             Execute SQL query or semicolon-separated script
  -f <file>            Execute SQL from file
  -i                   Interactive REPL mode
  -w, --write          Save database on exit (persist changes)
  --export <file>      Export tables to SQL file (local mode only)
  --export-tables=X    Tables to export: * (all, default) or table1,table2,...
  --http [port]        Start HTTP REST server (default: 8080, local mode only)
  --bind <addr>        Bind address for HTTP/MCP server (default: 127.0.0.1)
  --mcp [port]         Start MCP server (default: random port, use in -i mode)
                       Or use .mcp start in interactive mode
  -h, --help           Show this help
  --version            Show version

  idasql link <verb>   ida:// deep links (no database needed):
                       open <uri> | list | status | register | unregister | source | config
                       `idasql link --help` for details

Examples:
  idasql -s test.i64 -q "SELECT name, size FROM funcs LIMIT 10"
  idasql -s test.i64 -f queries.sql
  idasql -s test.i64 -i
  idasql -s test.i64 --export dump.sql
  idasql -s test.i64 --http 8080
  idasql -s sample.exe --http            # raw PE: idalib auto-analyzes, then serves SQL (default port 8080)
  idasql -s firmware.bin -q "SELECT * FROM binary"
  idasql -s test.i64 --mcp 9000
```

**Key takeaway:** `-s` accepts either an existing IDA database **or** a raw binary. No
manual `idat -A -B` / `ida -B` pre-step is needed — point `-s` straight at the
`.exe`/`.dll`/firmware/etc. and idalib creates the database on first open.

---

## Additional Resources

- Canonical schema catalog: [references/schema-catalog.md](references/schema-catalog.md)
- CLI reference, REPL commands, server modes, runtime controls: [references/cli-reference.md](references/cli-reference.md)
  (includes `.pin` autostart: the IDA plugin can auto-start a pinned HTTP/MCP server when a database is opened)

### Autostart pinning (HTTP/MCP)

`.pin http|mcp [bindinterface] [port]` pins a server so the **IDA plugin
auto-starts it when the database opens** (the pin lives in the IDB; CLI changes
persist only with `-w`). The port is **optional**:

- **Fixed port** — `.pin http 0.0.0.0 8080` → autostarts on that stable port every
  launch (use for stable automation).
- **Random port** — `.pin http` (port omitted, stored as `0`) → autostarts on a
  **fresh random port each launch** (a real pinned setting, not "unset"); read the
  chosen port from the live status. `.pin status` shows `<random port each launch>`.

`[bindinterface]` is the host/interface (default `127.0.0.1`). `.pin on|off http|mcp`
toggles autostart without dropping the host/port; `.pin clear [http|mcp|all]` removes
it. `.http start` / `.mcp start` with no port reuse the pinned host/port. Full grammar:
[references/cli-reference.md](references/cli-reference.md).
- Optimization quality gate: [references/optimization-checklist.md](references/optimization-checklist.md)
- HTTP server guide: [references/server-guide.md](references/server-guide.md)

---

## Attach to a Running Server (pasted from IDA)

When the request contains an idasql HTTP server URL — typically pasted from the
clipboard after `.http start` in IDA, e.g.
`idasql HTTP server at http://127.0.0.1:8134` followed by curl lines — the
database is already open in a live IDA session. Talk to that server; do **not**
start `idasql -s` yourself.

1. `curl <url>/help` first: the endpoints and how to discover the schema.
2. Send SQL as the raw body of `POST <url>/query` with `--data-binary`. If the
   pasted text shows an `Authorization: Bearer ...` header, send it with every
   request (only `GET /` and `GET /help` work without it). A `401` means the
   header is missing or wrong.
3. Run the Session Bootstrap orientation queries below over HTTP, then route to
   the domain skill for the task that followed the pasted text.
4. Writes (`UPDATE`/`INSERT`/`DELETE`) change the database open in IDA
   immediately, and the user sees them there. They are saved when the user
   saves in IDA; `--write` does not apply.

## Quick Start Guardrails

- Always provide `-s <file>`. The file can be either an IDA database
  (`.idb` / `.i64`) **or** a raw binary (`.exe`, `.dll`, firmware blob,
  etc.) — raw binaries trigger fresh idalib auto-analysis and string-list
  rebuild. Do **not** pre-create an IDB with `idat -A -B`;
  `idasql -s raw.exe` does it in one shot.
- If `idasql -s legacy.idb ...` exits with code `3` and stdout JSON containing
  `{"status":"upgraded","reopen_with":"..."}`, repeat the same requested
  operation with `-s <reopen_with>`. Server modes exit before binding in this
  case.
- Use `--write` when you want edits persisted on exit, including HTTP/MCP server shutdown.
- SQL inputs to `-q`, HTTP `/query`, MCP `idasql_query`, and plugin CLI
  may be one statement or a semicolon-separated script. Semicolons inside
  quoted strings are safe.
- **All `/query` responses use the canonical script envelope** — single
  statement = array of one:
  `{success, statement_count, results:[{statement_index, success,
  columns, rows, row_count, elapsed_ms, error}], row_count_total,
  elapsed_ms_total, first_error_index}`.
  Fail-fast is the default. Both standalone CLI `--http` and REPL/plugin
  `.http` honor `?continue_on_error=1` in the query string to run every
  statement regardless of earlier failures; both also honor
  `?include_sql=1`. MCP has no corresponding arguments.
- To stop a long-running HTTP query, send `POST /cancel` from another client.
  Cancellation is cooperative and uses the same authentication as `/query`;
  result-bearing statements may return partial rows plus a cancellation warning.
- Discover schema before writing queries:
  - REPL: `.schema <table>`
  - SQL: `PRAGMA table_xinfo(<table>);`
- Start orientation with `SELECT * FROM binary;`.

---

## Schema Catalog

Canonical column shapes and owner-skill mapping live in
`references/schema-catalog.md`. Sourced from `pragma_table_list` +
`pragma_table_xinfo`. Use it before assuming column names for
less-common surfaces.

---

## Session Bootstrap Contract

Use this exact startup flow before deep analysis:

1. Connect to database (`-s`, `-i`, or `--http`), or attach to a running server (see above). `-s` accepts either an existing IDB
   (`.idb`/`.i64`) or a raw binary (`.exe`/`.dll`/firmware/etc.) — never pre-build an
   IDB with `idat`; let `idasql -s raw.exe` do it.
   If a legacy `.idb` upgrades and returns `status:"upgraded"`, restart with the
   JSON `reopen_with` path before running orientation.
2. Run orientation query:
```sql
SELECT * FROM binary;
```
3. Validate key entities exist:
```sql
SELECT COUNT(*) AS funcs FROM funcs;
SELECT COUNT(*) AS xrefs FROM xrefs;
SELECT COUNT(*) AS strings FROM strings;
```
4. Introspect schema for target surfaces before authoring complex SQL:
```sql
PRAGMA table_xinfo(funcs);
PRAGMA table_xinfo(xrefs);
```
5. Route to domain skill using routing matrix below.

---

## Global Agent Contracts

These contracts apply across all idasql skills and should be treated as one shared agent behavior model.

### Read-First Contract
- Read current state first (`SELECT`) before writes (`INSERT`/`UPDATE`/`DELETE`).
- Confirm target precision using stable identifiers (`addr`, `func_addr`, `idx`, `label_num`).

### Anti-Guessing Contract
- Do not assume columns/types for long-tail surfaces.
- Introspect via `.schema` or `PRAGMA table_xinfo(...)` before issuing uncertain queries.

### Anti-Patterns
Habits that look natural but give wrong or slow answers, and what to do instead:

| Don't | Do instead |
|---|---|
| Parse pseudocode text with `LIKE` or a regex to find switch cases, calls, comparisons or loops | Switch cases: `switch_cases` / `switch_tables` (decompiler-free). Code structure: `ctree` and the `ctree_v_calls`, `ctree_v_comparisons`, `ctree_v_loops`, `ctree_v_ifs`, `ctree_v_returns` views. Text search on pseudocode is for finding a phrase, not for structure. |
| Walk a call graph one xref query at a time | One recursive CTE over `disasm_calls` (or the `call_graph` / `shortest_path` tables) returns the whole chain in a single query. |
| Decompile functions just to rank or triage them | `func_summary`: size, blocks, cyclomatic complexity, calls in and out, loops, switches, data reads and writes, frame size, per function, without the decompiler. |
| Scan `funcs` or `names` with `LIKE` to find something by name | The `grep` table (`WHERE pattern = '...'`) searches functions, labels, types and members in one indexed query. |
| Keep analysis progress in your own notes | `netnode_kv` stores it in the database, where the next session finds it. |
| Test "is this address in function F" with `addr >= start AND addr < end_addr` | `func_at(addr)`: functions can have tail chunks outside `[addr, end_addr)`, and one tail can belong to several functions. |

### Mandatory Mutation Loop
1. Read current state.
2. Apply mutation.
3. Refresh if needed (`decompile(..., 1)` for decompiler surfaces).
4. Re-read and verify expected change.

Integer values are exact on every write and scalar argument: `16`, `16.0` and `'16'`
are 16; a fraction, a blob, `NULL` or text like `'0x10'` is refused with the column
named (write hex unquoted: `0x10`). An INSERT's address column also takes `'0x...'`
text or a name.

### Performance Contract
- Always constrain high-cost surfaces (`xrefs`, `instructions`, `ctree*`, `pseudocode`) by key columns.
- For decompiler surfaces, enforce `func_addr = X` unless explicitly asked for broad scans.
- For raw dirtree browsing, prefer `tree = ?` plus `path`, `path LIKE`, or `parent_path`; for normal organization use `funcs.folder_path` and `types.folder_path`.
- `dirtree_entries` is read-only diagnostics. Recursive folder delete and raw recovery/link operations are intentionally not SQL surfaces.

### Failure Recovery Contract
- On `no such table/column`: introspect schema and retry.
- On empty results: validate address range, table freshness (`rebuild_strings()`), and runtime capabilities.
- On timeout: narrow scope, add constraints, paginate, or split query.

### Output Contract
- **Selection** - decide *whether and how much* to surface from user intent. Answer questions directly ("biggest is `main`, 500 bytes"); show supporting rows only when they help the user verify; don't dump full tables unprompted; never surface data fetched only as an intermediate reasoning step.
- **Fidelity** - when you *do* present code/data, show the real artifact (decompilation, actual rows), never a paraphrase.
- **Mechanics** - the HTTP `/query` response is a JSON envelope (`{success, results:[{columns,rows,...}]}`). Consume it directly and render in your reply. Do **not** pipe responses through `python`/`jq` to pre-render a table - that discards the `success`/`elapsed_ms`/`error` fields and makes you reason over a lossy view. The CLI (`-q`/`-f`) already prints a table. Reserve `jq`/`python` for extracting a value to feed a later query. (For direct terminal/pipe use the server can emit `?format=text|csv|tsv`; as an agent, consume `json`.)
- **Links** - on IDA 9.4 builds, make the functions, strings and types you name clickable: generate each link with the `deep_links` table (function links `view='pseudocode'`, addresses `view='disasm'`) and write it as `[exact_name](uri)` outside any code block (see the `deep-links` skill). Never hand-build an `ida://` string.

---

## Skill Routing Matrix (Intent -> Skill)

Use this deterministic mapping for initial routing:

| User intent | Primary skill | Typical first query |
|-------------|---------------|---------------------|
| "what does this binary do?" / triage | `analysis` | `SELECT * FROM entries;` |
| rank functions (biggest, most complex, most called) | `analysis` | `SELECT name, cyclomatic, call_sites_out, callers FROM func_summary ORDER BY cyclomatic DESC LIMIT 20;` |
| disassembly, segments, instructions | `disassembly` | `SELECT * FROM funcs LIMIT 20;` |
| which function contains an address / function chunks | `disassembly` | `SELECT name FROM func_at(0x...);` |
| FLIRT signatures: apply one, list applied, library vs own code | `disassembly` | `SELECT name, title, state, matches FROM signatures;` |
| function/type folders, review buckets, folder lifecycle | `annotations` / `types` | `SELECT addr, name, folder_path FROM funcs WHERE folder_path LIKE 'idasql/%';` |
| xrefs/callers/callees/import dependencies | `xrefs` | `SELECT * FROM xrefs WHERE to_addr = ...;` |
| find functions/types/labels/members by name pattern | `grep` | `SELECT name, kind, addr FROM grep WHERE pattern = 'main' LIMIT 20;` |
| strings/bytes/pattern search | `data` | `SELECT * FROM strings LIMIT 20;` |
| decompile/pseudocode/ctree/lvars | `decompiler` | `SELECT decompile(0x...);` |
| split a merged store/expression ("Split expression") | `decompiler` | `INSERT INTO decompiler_splits(addr, piece_size) VALUES (0x..., 4);` |
| comments/renames/retyping/bookmarks | `annotations` | `SELECT ...` on target row before update |
| type creation/struct/enum/member work | `types` | `SELECT * FROM types LIMIT 20;` |
| breakpoints/patching | `debugger` | `SELECT * FROM breakpoints;` |
| persistent key/value notes | `storage` | `SELECT * FROM netnode_kv LIMIT 20;` |
| SQL function lookup/signature recall | `functions` | `SELECT * FROM pragma_function_list;` |
| enumerate runtime settings / timeouts / queue config | `connect` | `SELECT * FROM runtime_settings;` (writable; change via `UPDATE runtime_settings SET value=... WHERE key=...`) |
| IDA configuration options (`ida.cfg`, `hexrays.cfg`, ...) | `connect` | `SELECT key, value, value_source, persisted FROM ida_config WHERE key = 'LOOKBACK';` |
| the database notepad | `annotations` | `SELECT text FROM notepad;` |
| checkpoint / undo / redo edits, per-turn rollback | `annotations` | `INSERT INTO checkpoints(label) VALUES ('before edits');` then `UPDATE checkpoints SET state='undone' WHERE label='before edits';` |
| SQL from a Python script or plugin inside IDA | `idapython` | `import idasql; idasql.query("SELECT name FROM funcs WHERE size > ?", 100)` |
| live IDA UI context questions | `ui-context` | `SELECT get_ui_context_json();` (when available) |
| clickable links to IDA locations / "open it in IDA" | `deep-links` | `SELECT uri FROM deep_links WHERE resource='functions' AND addr=0x... AND view='pseudocode';` (IDA 9.4 builds) |
| IDA SDK-only logic not in SQL surfaces | `idapython` | `UPDATE runtime_settings SET value='1' WHERE key='enable_idapython'; SELECT idapython_snippet('print(...)');` |
| recursive source/structure recovery | `re-source` | start from function + recurse/handoff |

When prompts span domains, execute in this order:
1. Orientation in `connect`
2. Primary domain skill
3. Adjacent skills for enrichment (for example `xrefs` + `decompiler` + `annotations`)

---

## Cross-Skill Execution Recipes

### Recipe: Unknown binary triage -> suspicious function deep dive -> annotate
1. `analysis`: identify candidates from imports/strings/call patterns.
2. `xrefs`/`disassembly`: map call graph and call sites.
3. `decompiler`: inspect logic and variable semantics.
4. `annotations`: apply comments/renames/types with mutation loop.

### Recipe: String IOC -> reference graph -> patch
1. `data`: locate candidate strings and addresses.
2. `xrefs`: map references to caller functions.
3. `debugger` or `annotations`: patch or annotate specific sites.

### Recipe: Type recovery from pseudocode
1. `decompiler`: inspect lvars, call args, and ctree patterns.
2. `types`: create/refine structs/enums and apply declarations.
3. `annotations`: finalize naming/comments and verify rendered pseudocode.

---

## UI Context Routing

For prompts like "what am I looking at?", "what's selected?", "what is on the screen?", "look at what I'm doing", or references to "this/current/that", use the dedicated `ui-context` skill.

`ui-context` owns:
- `get_ui_context_json()` capture/reuse policy
- temporal reference rules (`this` vs `that`)
- response template, examples, and fallback messaging

Runtime caveat:
- `get_ui_context_json()` is plugin GUI runtime only, not idalib/CLI mode.
- If unavailable, state that UI context is unavailable and continue with non-UI SQL workflows.

---

## binary

Database orientation surface for quick session metadata.
This is metadata-only and not a replacement for UI context capture.

Key/value shape — `(key TEXT, value TEXT, type TEXT)`, one row per metadata
fact, `type ∈ {string, hex, bool, int}`. The shape and the canonical key names
are shared across the tool family, so the same `WHERE key = '…'` query works on
every engine. The `summary` row is emitted first, so `SELECT * FROM binary`
shows the digest up top.

| Key | Type | Description |
|-----|------|-------------|
| `summary` | string | One-line database summary (first row) |
| `tool_name` | string | Always `idasql` |
| `tool_version` | string | IDASQL build version (canonical name) |
| `idasql_version` | string | IDASQL build version (legacy-named duplicate) |
| `processor` | string | Processor/module name |
| `filetype` | string | Loader file-type description (e.g. PE, ELF) |
| `image_base` | hex | Image base address |
| `entry_point` | hex | Entry/start address (was the `start_addr` column) |
| `min_addr` | hex | Minimum address in database |
| `max_addr` | hex | Maximum address in database |
| `is_64bit` | bool | `true`/`false` |
| `bits` | int | Application bitness: 16, 32, or 64 |
| `endianness` | string | `little` or `big` |
| `filename` | string | Bare input filename (no path) |
| `entry_name` | string | Entry symbol name (if known) |
| `funcs_count` | int | Number of detected functions |
| `segments_count` | int | Number of segments |
| `names_count` | int | Number of named addresses |
| `strings_count` | int | Current IDA string-list count |
| `input_file_path` | string | Original input file path recorded in the IDB |
| `idb_path` | string | On-disk path of the IDB/I64 (may differ if moved) |
| `md5` | string | Lowercase hex MD5 of the input file (empty if unavailable) |
| `sha256` | string | Lowercase hex SHA-256 of the input file (empty if unavailable) |

Use the `filename`, `idb_path`, `md5`, or `sha256` keys to confirm which
binary/instance this connection is bound to.

```sql
SELECT * FROM binary;
SELECT key, value FROM binary WHERE key IN ('filename','idb_path','md5','sha256');
SELECT value FROM binary WHERE key = 'idasql_version';
```

For canonical schema and owner mapping, see `references/schema-catalog.md`.

---

## ida_config

IDA's configuration keys: the analysis and display options of `ida.cfg`, the decompiler's `hexrays.cfg`, the GUI's `idagui.cfg`. IDA has no API that lists them, so the rows are the keys those files set, read the way IDA reads them: `IDADIR/cfg` then `IDAUSR/cfg` (later files win, the user's `idauser.cfg` included) and, in `ida.cfg`, the section for the database's processor. A key the files only mention in a comment or in another processor's section is listed when IDA can report its value (`LOOKBACK` on x86, for example).

| Column | Type | Description |
|--------|------|-------------|
| `key` | TEXT | Directive name, case-sensitive (`LOOKBACK`, `MAX_AUTONAME_LEN`, `BLOCK_INDENT`) |
| `file` | TEXT | The file that sets it (`ida.cfg`, `hexrays.cfg`, `idagui.cfg`, `idauser.cfg`) |
| `value` | TEXT | Writable. The value in `.cfg` syntax: a number, `YES`/`NO`, a quoted string. `NULL` when it cannot be known |
| `value_source` | TEXT | `runtime` (IDA reports the current value), `inf` (stored in the database), `session` (IDA cannot report it; what this session applied), `file` (IDA cannot report it; what the files set) |
| `writable` | INT | 1 when an `UPDATE` can reach it here: 0 for `idagui.cfg` keys outside the GUI and for decompiler keys without the decompiler |
| `persisted` | INT | 1 when a change is saved with the database (the `inf` keys); 0 means it lasts until the database is closed |
| `message` | TEXT | IDA's warning from this session's last `UPDATE` of the key (for example a clamp), else `NULL` |

```sql
-- What is set, and what survives a save
SELECT key, value, value_source, persisted FROM ida_config ORDER BY file, key;

-- One key
SELECT value FROM ida_config WHERE key = 'LOOKBACK';

-- Change it: applies LOOKBACK=88 and reads it back
UPDATE ida_config SET value = '88' WHERE key = 'LOOKBACK';

-- YES/NO keys also take 1/0, on/off; string keys are quoted for you
UPDATE ida_config SET value = 'no' WHERE key = 'SHOW_XREF_FUNC';

-- A clamped value is applied; the warning is in message
UPDATE ida_config SET value = '9999' WHERE key = 'LOOKBACK';
SELECT value, message FROM ida_config WHERE key = 'LOOKBACK';   -- 256, "... too high (must be at most 256)"

-- Changes that will be saved with the database
SELECT key, value FROM ida_config WHERE persisted = 1;
```

What persists, plainly:
- **`persisted = 1`** keys (`ANALYSIS`, `MAX_AUTONAME_LEN`, `SHOW_XREFS`, `INDENTION`, the `SHOW_*` and `STRLIT_*` display options, ...) are the database's own settings: a change is saved with the database (`save_database()` or `-w`), and on the next open the database's value beats `ida.cfg`.
- **Every other key** (`LOOKBACK`, the decompiler's keys, colors, ...) lasts until the database is closed; the next open reads the `.cfg` files again.
- Nothing here writes `.cfg` files (IDA offers no API for it). To keep a change across databases, put `KEY = value` in your own `idauser.cfg` (under `IDAUSR/cfg`) or pass `-D KEY=VALUE` to IDA.
- Startup keys (`DATABASE_MEMORY`, `VPAGES`, `WORKDIR`, ...) are accepted but act only when a database is next opened.

Failure and recovery:
- A value IDA rejects fails the `UPDATE` with IDA's own message (`Expected a number`, `Expected YES/NO or ON/OFF values`, ...). Read the row back: a rejected directive can still leave part of it applied.
- `writable = 0`: run the `UPDATE` where that key is read (the GUI plugin for `idagui.cfg`, a database with the decompiler for `hexrays.cfg`).
- `value_source = 'session'`/`'file'`: IDA cannot report the key's current value; a clamp of such a key shows only in `message`.
- One key per row, one `KEY=VALUE` per `UPDATE`: a value with an unquoted `=` is refused (it would start another directive). No `INSERT`/`DELETE`.

Performance: each query re-reads the option files and asks IDA for every value (a few tens of milliseconds). Filter by `key` in the same statement rather than scanning in a loop.

---

## What is IDA and Why SQL?

**IDA Pro** is the industry-standard disassembler and reverse engineering tool. It analyzes compiled binaries (executables, DLLs, firmware) and produces:
- **Disassembly** - Human-readable assembly code
- **Functions** - Detected code boundaries with names
- **Cross-references** - Who calls what, who references what data
- **Types** - Structures, enums, function prototypes
- **Decompilation** - C-like pseudocode (with Hex-Rays plugin)

**IDASQL** exposes all this analysis data through SQL virtual tables, enabling:
- Complex queries across multiple data types (JOINs)
- Aggregations and statistics (COUNT, GROUP BY)
- Pattern detection across the entire binary
- Scriptable analysis without writing IDA plugins or IDAPython scripts

---

## Core Concepts for Binary Analysis

### Addresses (ea_t)
Everything in a binary has an **address** - a memory location where code or data lives. IDA uses `ea_t` (effective address) as unsigned 64-bit integers. SQL shows these as integers; use `printf('0x%X', addr)` for hex display.

Address-taking SQL functions accept:
- integer EA values (preferred for deterministic scripts)
- numeric strings (`'4198400'`, `'0x401000'`)
- symbol names resolved with `get_name_ea(BADADDR, name)` (global names)

Most table predicates should compare address columns to integer EAs such as
`addr = 0x401000`. `applied_types.addr` is an intentional exception for
equality filters/writes: it also accepts numeric strings and symbol names so
type application can target names directly.

Examples:
```sql
SELECT decompile('DriverEntry');
UPDATE applied_types
SET decl = 'NTSTATUS DriverEntry(PDRIVER_OBJECT, PUNICODE_STRING);'
WHERE addr = 'DriverEntry';
SELECT (SELECT comment FROM comments WHERE addr = 0x401000 LIMIT 1);
```

Read address comments from the `comments` table after resolving the target EA.

If a symbol cannot be resolved, SQL functions return an explicit error like:
`Could not resolve name to address: <name>`.

Local label lookup that depends on a specific `from` context is not consulted by default (`BADADDR` resolution). Use explicit numeric EAs when needed.

**High addresses (>= 2^63), e.g. kernel images at `0xFFFFF800...`:** SQL holds
them as negative INTEGERs, so `ORDER BY addr` lists them first. Write them as hex
literals (`0xFFFFF80000100000`) or the negative decimal, never as a decimal
>= 2^63 (SQLite makes that a REAL, which matches nothing). `addr >= <high hex>`
also includes every low address; the high half alone is
`addr BETWEEN <high hex> AND -1`. Details: the disassembly and data skills.

### Functions
IDA groups code into **functions** with:
- `addr` / `start_addr` - Where the function begins (its entry point)
- `end_addr` - Where the **entry chunk** ends (not the whole function)
- `name` - Assigned or auto-generated name (e.g., `main`, `sub_401000`)
- `size` - Total bytes in the function, over all of its chunks
- `chunk_count` - Number of chunks (1 for a contiguous function)

Functions are not always contiguous: a function can own **tail chunks** elsewhere
in memory, and one tail can belong to several functions. So never check "X is in
function f" with an `addr`..`end_addr` range; use `func_at(X)` (owning function(s)
of an address), the owner columns (`blocks.func_addr`, `xrefs.from_func`) for joins,
and `function_chunks` for a function's chunks. Details: the `disassembly` skill.

There will be addresses and disassembly listing not belonging to a function. IDASQL can still get the bytes, disassembly listing ranges, etc.
For single-EA disassembly (code or data), prefer `disasm_at(addr[, context])` over function-scoped queries.

### Cross-References (xrefs)
Binary analysis is about understanding **relationships**:
- **Code xrefs** - Function calls, jumps between code
- **Data xrefs** - Code reading/writing data locations, or data referring to other data (pointers)
- `from_addr` -> `to_addr` represents "address X references address Y"
Use table: `xrefs(from_addr, to_addr, type, is_code)`.

### Segments

Use table: `segments(start_addr, end_addr, name, class, perm)` (full CRUD).
`UPDATE start_addr` rebases a segment, `end_addr` resizes it.

Memory is divided into **segments** with different purposes. For example, a typical PE file, has these segments:

- `.text` - Executable code (typically)
- `.data` - Initialized global data
- `.rdata` - Read-only data (strings, constants)
- `.bss` - Uninitialized data

Of course, segment names and types can vary. You may query the `segments` table to understand memory layout.

### Basic Blocks
Within a function, **basic blocks** are straight-line code sequences:
- No branches in the middle
- Single entry, single exit
- Useful for control flow analysis
Use table: `blocks(start_addr, end_addr, func_addr, size)`.

### Decompilation (Hex-Rays)
The **Hex-Rays decompiler** converts assembly to C-like **pseudocode**:
- **ctree** - The Abstract Syntax Tree of decompiled code
- **lvars** - Local variables detected by the decompiler
- Much easier to analyze than raw assembly

Core decompiler surfaces:
- `decompile(addr)` (**PRIMARY read/display surface**)
  - Returns the entire function as one text block.
  - Each output line is prefixed for address grounding:
    - Addressed line: `/* 401010 */ ...`
    - Non-anchored line: `/*          */ ...` (no address anchor for that line)
  - Use this first when the user asks to "decompile", "show code", "show pseudocode", or "explain function logic".
- `pseudocode` table (**structured/edit surface**)
  - Use for line-level filtering (`func_addr`, `addr`, `line_num`) and comment writes keyed by `addr + comment_placement`.
  - Resolve a writable pseudocode anchor first; do not assume `addr == func_addr`.
  - Not the preferred display surface for full-function code.
- `ctree` and `ctree_call_args` for AST-level analysis
- `ctree_lvars` for local variable rename/type/comment updates
- `decompiler_splits` for Hex-Rays "Split expression" without a window (INSERT/UPDATE `piece_size`/DELETE)

---

## Performance Rules

### CRITICAL: Constraint Pushdown

Some tables have **optimized filters** that use efficient IDA SDK APIs:

| Table | Optimized Filter | Without Filter |
|-------|------------------|----------------|
| `instructions` | `func_addr = X` | O(all instructions) - SLOW |
| `blocks` | `func_addr = X` | O(all blocks) |
| `xrefs` | `to_addr = X` or `from_addr = X` | O(all xrefs) |
| `pseudocode` | `func_addr = X` | **Decompiles ALL functions** |
| `ctree*` | `func_addr = X` | **Decompiles ALL functions** |

**Always filter decompiler tables by `func_addr`!**

### Use Integer Comparisons

```sql
-- SLOW: String comparison
WHERE mnemonic = 'call'

-- FAST: Integer comparison
WHERE itype IN (16, 18)  -- x86 call opcodes
```

### O(1) Random Access

```sql
-- SLOW: O(n) - sorts all rows
SELECT addr FROM funcs ORDER BY RANDOM() LIMIT 1;

-- FAST: O(1) - direct index access
SELECT addr
FROM funcs
WHERE rowid = ABS(RANDOM()) % (SELECT COUNT(*) FROM funcs);
```

### CTE-First Mutation Workflow

For instruction lifecycle edits, use a CTE to identify precise targets first, then mutate.
Delete everything that flows into an instruction in the same statement: a lone instruction
that code still reaches is re-created by auto-analysis, and that DELETE fails and says so.

```sql
WITH target AS (
    SELECT addr
    FROM instructions
    WHERE func_addr = 0x401000
)
DELETE FROM instructions
WHERE addr IN (SELECT addr FROM target);

-- recreate over every chunk of the function (end_addr ends the entry chunk only)
SELECT SUM(make_code_range(chunk_start, chunk_end)) AS created FROM function_chunks WHERE func_addr = 0x401000;
```

This keeps mutation scope explicit and predictable for both humans and agents.

---

## Summary: When to Use What

| Goal | Table/Function |
|------|----------------|
| List all functions | `funcs` (cols: `addr`, `name`, `size`, `end_addr`, `prototype`, `flags`, …, `chunk_count`) → `disassembly` |
| List applied FLIRT signatures and what each found | `signatures` (`name`, `title`, `state`, `matches`) → `disassembly` |
| Apply a FLIRT signature | `INSERT INTO signatures(name) VALUES ('vc32rtf')`; pick from `available_signatures` → `disassembly` |
| Library functions (recognized by a signature) | `funcs WHERE flags & 4` → `disassembly` |
| Function containing an address | `func_at(addr)` (tail chunks included) → `disassembly` |
| A function's chunks | `function_chunks WHERE func_addr = X` → `disassembly` |
| Functions by return type | `funcs WHERE return_is_integral = 1` |
| Functions by arg count | `funcs WHERE arg_count >= N` |
| Void functions | `funcs WHERE return_is_void = 1` |
| Pointer-returning functions | `funcs WHERE return_is_ptr = 1` |
| Functions by calling convention | `funcs WHERE calling_conv = 'fastcall'` |
| Rank or triage functions | `func_summary` (blocks, cyclomatic, calls in/out, callers, loops, switches, data reads/writes, frame size, `uses_chkstk`) → `analysis` |
| Find who calls what | `xrefs` with `kind = 'call'` (`is_code = 1` also includes jumps) |
| Find data references | `xrefs` with `is_code = 0`; `kind` tells `read` / `write` / `offset` apart |
| Stack frame of a function | `function_frames WHERE func_addr = X` (sizes, `stack_base_reg`, `uses_chkstk`) → `disassembly` |
| Analyze imports | `imports` (cols: `addr`, `name`, `ordinal`, `module`) → `xrefs` / `analysis` |
| Find strings | `strings` (cols: `addr`, `length`, `content`) → `data` |
| Configure string types | `rebuild_strings(minlen, types)` |
| Instruction analysis | `instructions WHERE func_addr = X` |
| Recreate deleted instructions | `make_code(addr)`, `make_code_range(start, end)` |
| Apply/clear address type declarations | `applied_types` (`INSERT`, `UPDATE decl`, `DELETE`) |
| Apply/clear call-site prototypes | `UPDATE disasm_calls SET callee_type = ... WHERE addr = X` |
| Create function at EA | `INSERT INTO funcs(addr) VALUES (...)` |
| View function disassembly | `disasm_func(addr)` (every chunk); `disasm_range(start, end)` for an arbitrary range |
| View decompiled code | `decompile(addr)` |
| UI/screen context questions | `ui-context` skill (`get_ui_context_json()`, plugin UI only) |
| Edit decompiler comments | `Resolve writable anchor, then UPDATE pseudocode SET comment = '...' WHERE func_addr = X AND addr = Y` |
| AST pattern matching | `ctree WHERE func_addr = X` |
| Call patterns | `ctree_v_calls`, `disasm_calls` |
| Control flow | `ctree_v_loops`, `ctree_v_ifs` |
| Return value analysis | `ctree_v_returns` |
| Functions returning specific values | `ctree_v_returns WHERE return_num = 0` |
| Pass-through functions | `ctree_v_returns WHERE returns_arg = 1` |
| Wrapper functions | `ctree_v_returns WHERE returns_call_result = 1` |
| Variable analysis | `ctree_lvars WHERE func_addr = X` |
| Type information | `types`, `types_members` |
| Function signatures | `types_func_args` (with type classification) |
| Functions by return type | `types_func_args WHERE arg_index = -1` |
| Typedef-aware type queries | `types_func_args` (surface vs resolved) |
| Hidden pointer types | `types_func_args WHERE is_ptr = 0 AND is_ptr_resolved = 1` |
| Manage breakpoints | `breakpoints` (full CRUD) |
| Modify segments | `segments` (INSERT/UPDATE/DELETE) |
| Rename decompiler labels | `UPDATE ctree_labels SET name=... WHERE func_addr=... AND label_num=...` |
| Split a merged store ("Split expression") | `decompiler_splits` (`INSERT ... (addr, piece_size)`, `DELETE` unsplits) → `decompiler` |
| Delete instructions | `instructions` (DELETE converts to unexplored bytes) |
| Recreate instructions | `make_code`, `make_code_range` |
| Bulk patch from file bytes | `load_file_bytes(path, file_offset, addr, size[, patchable])` |
| EA to physical offset mapping | `bytes.fpos` on mapped byte rows (`NULL` means no file offset) |
| Create types | `types` (INSERT struct/union/enum) |
| Add struct members | `types_members` (INSERT) |
| Add enum values | `types_enum_values` (INSERT) |
| Modify database | `funcs`, `names`, `comments`, `bookmarks` (INSERT/UPDATE/DELETE) |
| Store custom key-value data | `netnode_kv` (full CRUD, persists in IDB) |
| Read or write the database notepad | `notepad` (`UPDATE notepad SET text = ...`) → `annotations` |
| Undo a batch of edits / an agent turn | `checkpoints` (`INSERT` before, `UPDATE ... SET state='undone'` to roll back), `undo_state` → `annotations` |
| Query idasql from IDAPython | `import idasql` (`query` / `rows` / `scalar` / `script`) → `idapython` |
| Read or change IDA options | `ida_config` (`UPDATE ida_config SET value = ... WHERE key = ...`; `persisted` says what is saved) |
| Entity search (structured) | `grep` skill + `grep WHERE pattern = '...'` |

**Remember:** Always use `func_addr = X` constraints on instruction and decompiler tables for acceptable performance.

---

## Error Handling

- **No Hex-Rays license:** Decompiler tables (`pseudocode`, `ctree*`, `ctree_lvars`) will be empty or unavailable
- **No constraint on decompiler tables:** Query will be extremely slow (decompiles all functions)
- **Invalid address:** Containing-function table lookups return no row; use a scalar subquery when you need a nullable scalar result
- **Missing function:** JOINs may return fewer rows than expected

---

## See Also

- `analysis` — first triage after connecting (`func_summary`, imports, strings, entries).
- `grep` — find functions, labels, types and members by name before querying them.
- `functions` — the SQL function catalog when you need a signature.
- `deep-links` — make the functions and addresses you report clickable (IDA 9.4 builds).

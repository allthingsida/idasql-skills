# CLI Reference

Command-line interface, REPL commands, runtime controls, database modification, hex formatting, and server modes.

---

## Command-Line Interface

IDASQL provides SQL access to IDA databases via command line or as a server.

### Invocation Modes

**0. Fresh Analysis from Raw Binary**

`-s` accepts either an existing IDA database **or** a raw binary. When the path does
not end in `.idb`/`.i64`, idalib runs auto-analysis and rebuilds the string list on
first open. No `idat -A -B` / `ida -B` pre-step is needed.

```bash
idasql -s sample.exe --http 8080
idasql -s sample.dll -q "SELECT * FROM binary"
idasql -s firmware.bin -i
```

Add `--write` (or `-w`) if you want the freshly analyzed database persisted on exit.

**Legacy 32-bit `.idb` upgrade**

IDA 9.x idalib upgrades legacy 32-bit `.idb` files to sibling `.i64` files. idasql
does not serve the empty upgraded live session. Instead it exits with code `3` and
prints one stdout JSON object:

```json
{"status":"upgraded","input":"C:/tmp/prog.idb","reopen_with":"C:/tmp/prog.i64","upgrade_log":"C:/tmp/prog.id0.upgrade.log","message":"Database upgraded from 32-bit .idb to 64-bit .i64; reopen with -s <reopen_with>."}
```

Repeat the same command with `-s <reopen_with>`. In `--http` and `--mcp` modes,
the process exits before binding a port.

**1. Query or Script (Local)**
```bash
idasql -s database.i64 -q "SELECT * FROM funcs LIMIT 10"
idasql -s database.i64 -q "SELECT * FROM binary; SELECT COUNT(*) FROM funcs;"
```

**2. SQL File Execution**
```bash
idasql -s database.i64 -f analysis.sql
```

**3. Interactive REPL**
```bash
idasql -s database.i64 -i
```

**4. HTTP Server Mode**
```bash
idasql -s database.i64 --http 8080
# Then query via: curl -X POST http://localhost:8080/query --data-binary "SELECT * FROM funcs"
```

**5. Export Mode**

If the user asks to export the database as SQL, use:
```bash
idasql -s database.i64 --export dump.sql
idasql -s database.i64 --export dump.sql --export-tables=funcs,segments
```

### CLI Options

| Option | Description |
|--------|-------------|
| `-s <file>` | IDA database (`.idb`/`.i64`) **or** raw binary (`.exe`/`.dll`/firmware/etc.) — raw binaries trigger fresh idalib analysis and string-list rebuild; legacy 32-bit `.idb` may return `status:"upgraded"` with `reopen_with` |
| `--token <token>` | Auth token for HTTP server mode (HTTP only; MCP has no auth) |
| `-q <sql>` | Execute SQL query or semicolon-separated script |
| `-f <file>` | Execute SQL from file: each statement's results print; the first failing statement stops the script and prints its error after the results before it (exit 1) |
| `-i` | Interactive REPL mode |
| `-w, --write` | Save database changes on exit, including HTTP/MCP server shutdown |
| `--export <file>` | Export tables to SQL file |
| `--export-tables=X` | Tables to export: `*` (all) or `table1,table2,...` |
| `--http [port]` | Start HTTP REST server (default: 8080, local mode only) |
| `--bind <addr>` | Bind address for HTTP/MCP server (default: 127.0.0.1) |
| `--mcp [port]` | Start MCP server (default: random port, use in -i mode) |
| `-h, --help` | Show help |
| `--version` | Show version |

### `idasql link` (IDA 9.4 builds)

Works with `ida://` deep links. It needs no `-s` database and never
starts idalib, so it is also what a registered URL handler runs.

| Command | What it does |
|---------|--------------|
| `idasql link open [--pid N] [--no-launch] [--skip-analysis] [--timeout S] [--ida-arg A]... -- <uri>` | Open the link in the running IDA 9.4 that has the database open. With none open, start IDA on it (found from the link's `idb_path`, or a configured source), wait for analysis, then navigate |
| `idasql link list [--json]` | Running IDA 9.4 instances, their databases and analysis state |
| `idasql link status [--json]` | Who handles `ida://` here (`idasql`, `hcli`, `other`, `none`), and the previous handler idasql saved |
| `idasql link register` | Make idasql the `ida://` click handler. A handler it replaces (hcli's, say) is saved |
| `idasql link unregister` | Remove idasql's registration and restore the saved handler (never removes another program's) |
| `idasql link source add <name> <dir>` / `list` / `remove <name>` | Folders searched for a database a link names |
| `idasql link config show` / `ida <path>` / `ida-args <arg>...` / `launch-timeout <s>` / `wait-analysis on\|off` | `links.json` in the user config directory |

Exit codes: 0 opened, 1 usage, 2 invalid link, 3 nothing has the database open (and
no launch), 4 several instances match (use `--pid`), 5 IDA refused, 6 launch failed,
7 launch declined.

Quote the link in every shell (`&` separates commands).

### REPL Commands

| Command | Description |
|---------|-------------|
| `.tables` | List all virtual tables |
| `.schema [table]` | Show table schema |
| `.info` | Show database metadata |
| `.quit` / `.exit` | Exit REPL |
| `.help` | Show available commands |
| `.http start` | Start HTTP server (reuses a pinned port when no port is given) |
| `.http stop` | Stop HTTP server |
| `.http` | Show HTTP server status (start if not running) |
| `.pin` / `.pin list` / `.pin status` | Show pinned autostart config |
| `.pin http\|mcp [bindinterface] [port]` | Pin a server; enables autostart. **Omit the port for a fresh random port each launch.** |
| `.pin set http\|mcp [bindinterface] [port]` | Same, explicit form |
| `.pin on\|off http\|mcp` | Enable/disable autostart-on-load (keeps host/port) |
| `.pin clear [http\|mcp\|all]` | Remove pinned config (default `all`) |
| `.pin help` | Show pin help |

> **Autostart pins.** A pin is stored in the IDB (netnode `$ idasql config`).
> The `.pin` command works in both the CLI and the plugin — but **only the IDA
> plugin auto-starts** pinned servers when the database is opened. `.http start`
> / `.mcp start` with no explicit port reuse the pinned host/port. From the CLI,
> `.pin` changes persist only when idasql is started with `-w/--write` (same as
> any other IDB edit).
>
> **Optional port (fixed vs random).** `[bindinterface]` is the host/interface
> (default `127.0.0.1`). The port is **optional**:
> - **Fixed port** — `.pin http 0.0.0.0 8080` pins a stable port; the plugin
>   autostarts on it every launch (good for stable automation).
> - **Random port** — `.pin http` (port omitted, stored as `0`) pins autostart
>   with a **fresh random port each launch**. This is a real pinned setting, not
>   "unset" — discover the chosen port from the live status. `.pin status` shows
>   `<random port each launch>` for such a pin.
>
> ```text
> .pin http                 # autostart HTTP on a random port each launch
> .pin mcp 127.0.0.1 8081   # autostart MCP on a fixed port
> .pin status               # http -> 127.0.0.1:<random port each launch> (autostart on)
> .pin off http             # keep the pin but stop autostarting
> .pin clear all            # remove all pins
> ```

### Performance Strategy

Opening a database has startup overhead (IDALib initialization and auto-analysis wait). For one small query or short script, use `-q`. For iterative work, keep one long-lived session (`-i`, `--http`, or `--mcp`) and run many queries against it.

**One-shot query/script:** Use `-q` directly.
```bash
idasql -s database.i64 -q "SELECT COUNT(*) FROM funcs"
idasql -s database.i64 -q "SELECT * FROM binary; SELECT COUNT(*) FROM funcs;"
```

**Iterative exploration:** Start a server once, then query repeatedly over HTTP. Each HTTP `/query` body may also be a semicolon-separated script; every response uses the canonical `results[]` envelope (a single statement is an array of one).

Opening an IDA database has startup overhead (idalib initialization, auto-analysis). If you plan to run many queries—exploring the database, experimenting with different queries, or iterating on analysis—avoid re-opening the database each time.

**Recommended workflow for iterative analysis:**
```bash
# Terminal 1: Start server (opens database once)
idasql -s database.i64 --http 8080

# Terminal 2: Query repeatedly via HTTP (instant responses)
curl -X POST http://localhost:8080/query --data-binary "SELECT * FROM funcs LIMIT 5"
curl -X POST http://localhost:8080/query --data-binary "SELECT * FROM strings WHERE content LIKE '%error%'"
curl -X POST http://localhost:8080/query --data-binary "SELECT name, size FROM funcs ORDER BY size DESC"
# ... as many queries as needed, no startup cost
```

This approach is significantly faster for iterative analysis since the database remains open and queries go directly through the already-initialized session.
Use `-w` for long-lived HTTP/MCP write sessions when edits should be saved on shutdown; otherwise writes are visible in the current process but must be flushed with `SELECT save_database()`.

---

## Runtime Controls (SQL)

Runtime settings live in the **writable** `runtime_settings` table. Read with
`SELECT`, change with `UPDATE`. The only PRAGMAs are the two imperative timeout-stack
verbs (`timeout_push`/`timeout_pop`):

```sql
-- read
SELECT value FROM runtime_settings WHERE key='query_timeout_ms';
SELECT key, value, type, scope, kind, settable FROM runtime_settings;   -- discover every setting

-- change (UPDATE is the only writer)
UPDATE runtime_settings SET value='60000'  WHERE key='query_timeout_ms';            -- 0 disables
UPDATE runtime_settings SET value='120000' WHERE key='queue_admission_timeout_ms';
UPDATE runtime_settings SET value='64'     WHERE key='max_queue';                   -- 0 = unbounded
UPDATE runtime_settings SET value='1'      WHERE key='hints_enabled';               -- 1/0, on/off
UPDATE runtime_settings SET value='1'      WHERE key='enable_idapython';            -- enable SQL Python
UPDATE runtime_settings SET value='0'      WHERE key='idapython_output_max';        -- cap bytes (0 = unbounded)
UPDATE runtime_settings SET value='1'      WHERE key='enable_deep_link_navigation'; -- let ida_open_link() steer IDA (IDA 9.4; ON in the plugin, OFF in the CLI)
UPDATE runtime_settings SET value='statement' WHERE key='auto_checkpoint';          -- an undo checkpoint per writing statement; 'off' (default)

-- timeout_push/timeout_pop are the only PRAGMAs (imperative stack verbs)
PRAGMA idasql.timeout_push = 15000;              -- push old timeout, set new (stack bounded to 64)
PRAGMA idasql.timeout_pop;                       -- restore previous timeout
```

The `timeout_push` stack is bounded to **64** entries; the 65th push is rejected
(guards against unbounded client-driven growth). Pair each push with a `timeout_pop`.

`runtime_settings` returns one `key`/`value`/`type`/`scope`/`kind`/`settable` row per setting; its
`value` column is writable for value settings via `UPDATE ... WHERE key='<key>'`.
`key`/`type`/`scope`, the read-only rows (`timeout_stack_depth`,
`max_timeout_stack_depth`) and the action verbs (`timeout_push`/`timeout_pop`) reject
writes, and `INSERT`/`DELETE` are rejected.

Recommended defaults for agent harnesses that issue concurrent requests:

```sql
UPDATE runtime_settings SET value='0'     WHERE key='max_queue';                   -- unbounded queue
UPDATE runtime_settings SET value='0'     WHERE key='queue_admission_timeout_ms';  -- wait until completion
UPDATE runtime_settings SET value='60000' WHERE key='query_timeout_ms';            -- still cap execution time
```

When a `SELECT` times out, partial rows may be returned with `warnings` and `timed_out=true`.
For decompiler-heavy queries, `idasql` emits warnings that suggest adding `WHERE func_addr = ...`.

---

## Database Modification

Most write examples are documented next to their tables (`breakpoints`, `segments`, `names`, `instructions`, `types*`, `applied_types`, `disasm_calls`, `dirtree_folders`, `bookmarks`, `comments`, `ctree_lvars`, `ctree_labels`, `decompiler_splits`, `netnode_kv`).
Quick capability matrix:

| Table | INSERT | UPDATE columns | DELETE |
|-------|--------|---------------|--------|
| `breakpoints` | Yes | `enabled`, `type`, `size`, `flags`, `pass_count`, `condition`, `group`, `folder_path` | Yes |
| `funcs` | Yes | `name`, `prototype`, `comment`, `rpt_comment`, `flags`, `folder_path` | Yes |
| `names` | Yes | `name`, `folder_path` | Yes |
| `comments` | Yes | `comment`, `rpt_comment` | Yes |
| `bookmarks` | Yes | `description`, `folder_path` | Yes |
| `segments` | Yes | `start_addr` (rebase), `end_addr` (resize), `name`, `class`, `perm` | Yes |
| `instructions` | — | `operand0_format_spec` .. `operand7_format_spec` | Yes |
| `bytes` | — | `value`, `word`, `dword`, `qword` | Yes (revert patch) |
| `types` | Yes | `name`, `folder_path`, plus type-table write columns | Yes |
| `imports` | — | `folder_path` | — |
| `local_type_bookmarks` | `ordinal`, `description` | `description`, `folder_path` | yes |
| `dirtree_folders` | Yes (all standard dirtrees) | `path` rename/move | Yes, empty folders only |
| `types_members` | Yes | Yes | Yes |
| `types_enum_values` | Yes | Yes | Yes |
| `applied_types` | Yes | `decl` | Yes |
| `disasm_calls` | — | `callee_type` | — |
| `ctree_lvars` | — | `name`, `type`, `comment` | — |
| `ctree_labels` | — | `name` | — |
| `decompiler_splits` | Yes (`addr`, `piece_size`; `func_addr` optional) | `piece_size` | Yes (unsplits) |
| `netnode_kv` | Yes | `value` | Yes |

Instruction creation uses SQL functions rather than `INSERT`:
- `make_code(addr)`
- `make_code_range(start, end)`

Function creation uses table INSERT (calls `add_func()`):
- `INSERT INTO funcs(addr) VALUES (...)`
- `size` (total over all chunks), `end_addr` (end of the entry chunk only) and `chunk_count` are read-only; a function's chunks are listed by `function_chunks`, and `func_at(addr)` finds the function(s) owning an address

Folder organization uses object-table `folder_path` columns and `dirtree_folders`:

```sql
INSERT INTO dirtree_folders(tree, path) VALUES ('funcs', 'idasql/folder-lifecycle-demo');
UPDATE funcs SET folder_path = 'idasql/folder-lifecycle-demo' WHERE addr = 0x401000;
UPDATE names SET folder_path = 'idasql/names/globals' WHERE addr = 0x402000;
UPDATE imports SET folder_path = 'idasql/imports/network' WHERE name LIKE '%socket%';
UPDATE bookmarks SET folder_path = 'idasql/bookmarks/review' WHERE slot = 0;
UPDATE breakpoints SET folder_path = 'idasql/breakpoints/watch' WHERE addr = 0x401000;
UPDATE dirtree_folders SET path = 'idasql/folder-lifecycle-renamed'
WHERE tree = 'funcs' AND path = 'idasql/folder-lifecycle-demo';
UPDATE funcs SET folder_path = NULL WHERE addr = 0x401000;
DELETE FROM dirtree_folders WHERE tree = 'funcs' AND path = 'idasql/folder-lifecycle-renamed';
```

`dirtree_entries` is read-only raw browsing for all standard trees (`funcs`, `local_types`, `names`, `imports`, `idaplace_bookmarks`, `bpts`, `ltypes_bookmarks`). Prefer `tree = ?` plus `path`, `parent_path`, or `inode` filters in raw queries. Its paths are absolute (`/idasql/review`) and compare exactly like SQL: `path = 'idasql/review'` or `path LIKE 'idasql%'` match nothing. `dirtree_folders.path` and object-table `folder_path` values are relative (`idasql/review`).

Folder writes use relative `/` paths. `NULL` or `''` moves object-table folder columns back to root. IDASQL rejects `.`/`..`, duplicate separators, backslashes, non-empty folder deletes, and folder renames whose destination already exists.
Recursive folder delete and raw recovery/link operations are not exposed through SQL.

Bulk byte loading from external files uses:
- `SELECT load_file_bytes(path, file_offset, addr, size[, patchable])`

---

## Hex Address Formatting

IDA uses integer addresses. For display, use `printf()`:

```sql
-- 32-bit format
SELECT printf('0x%08X', addr) as addr FROM funcs;

-- 64-bit format
SELECT printf('0x%016llX', addr) as addr FROM funcs;

-- Auto-width
SELECT printf('0x%X', addr) as addr FROM funcs;
```

---

## Server Modes

IDASQL supports HTTP-based server modes for remote queries: **HTTP REST** and **MCP** (both over HTTP/SSE).

---

### HTTP REST Server (Recommended)

Standard REST API for curl, Python, or any HTTP client.

```bash
idasql -s database.i64 --http              # default port 8080
idasql -s database.i64 --http 9000         # custom port
idasql -s database.i64 --http --token X    # with auth
```

```bash
curl -X POST http://localhost:8080/query --data-binary "SELECT name, size FROM funcs LIMIT 5"
```

For endpoints, Python automation patterns, response format, and compatibility notes, see `references/server-guide.md`.

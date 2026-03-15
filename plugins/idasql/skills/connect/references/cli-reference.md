# CLI Reference

Command-line interface, REPL commands, runtime controls, database modification, hex formatting, and server modes.

---

## Command-Line Interface

IDASQL provides SQL access to IDA databases via command line or as a server.

### Binary Provenance (Required)

When validating behavior that must match the live IDA plugin session, use SDK-path binaries:

- CLI: `%IDASDK%\src\bin\idasql.exe`
- Plugin loaded by IDA: `%IDASDK%\src\bin\plugins\idasql.dll`

Do not use test harness binaries (for example `build/idasql_tests/.../idasql.exe`) to conclude plugin behavior. Those are useful for tests, but plugin-parity checks must run against the SDK-path artifacts.

### Invocation Modes

**1. Single Query (Local)**
```bash
idasql -s database.i64 -q "SELECT * FROM funcs LIMIT 10"
idasql -s database.i64 -c "SELECT COUNT(*) FROM funcs"  # -c is alias for -q
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
# Then query via: curl -X POST http://localhost:8080/query -d "SELECT * FROM funcs"
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
| `-s <file>` | IDA database file (.idb/.i64) |
| `--token <token>` | Auth token for HTTP/MCP server mode |
| `-q <sql>` | Execute single SQL query |
| `-f <file>` | Execute SQL from file |
| `-i` | Interactive REPL mode |
| `-w, --write` | Save database changes on exit |
| `--export <file>` | Export tables to SQL file |
| `--export-tables=X` | Tables to export: `*` (all) or `table1,table2,...` |
| `--http [port]` | Start HTTP REST server (default: 8080, local mode only) |
| `--bind <addr>` | Bind address for HTTP/MCP server (default: 127.0.0.1) |
| `--mcp [port]` | Start MCP server (default: random port, use in -i mode) |
| `--agent` | Enable AI agent mode in interactive REPL |
| `--config [path] [value]` | View/set agent configuration |
| `-h, --help` | Show help |

### REPL Commands

| Command | Description |
|---------|-------------|
| `.tables` | List all virtual tables |
| `.schema [table]` | Show table schema |
| `.info` | Show database metadata |
| `.clear` | Clear session |
| `.quit` / `.exit` | Exit REPL |
| `.help` | Show available commands |
| `.http start` | Start HTTP server on random port |
| `.http stop` | Stop HTTP server |
| `.http status` | Show HTTP server status |
| `.agent` | Start AI agent mode |

### Performance Strategy

Opening a database has startup overhead (IDALib initialization and auto-analysis wait). For one query, use `-q`. For iterative work, keep one long-lived session (`-i`, `--http`, or `--mcp`) and run many queries against it.

**Single queries:** Use `-q` directly.
```bash
idasql -s database.i64 -q "SELECT COUNT(*) FROM funcs"
```

**Multiple queries / exploration:** Start a server once, then query repeatedly over HTTP.

Opening an IDA database has startup overhead (idalib initialization, auto-analysis). If you plan to run many queries—exploring the database, experimenting with different queries, or iterating on analysis—avoid re-opening the database each time.

**Recommended workflow for iterative analysis:**
```bash
# Terminal 1: Start server (opens database once)
idasql -s database.i64 --http 8080

# Terminal 2: Query repeatedly via HTTP (instant responses)
curl -X POST http://localhost:8080/query -d "SELECT * FROM funcs LIMIT 5"
curl -X POST http://localhost:8080/query -d "SELECT * FROM strings WHERE content LIKE '%error%'"
curl -X POST http://localhost:8080/query -d "SELECT name, size FROM funcs ORDER BY size DESC"
# ... as many queries as needed, no startup cost
```

This approach is significantly faster for iterative analysis since the database remains open and queries go directly through the already-initialized session.

---

## Runtime Controls (SQL)

`idasql` exposes runtime settings through pragmas:

```sql
PRAGMA idasql.query_timeout_ms;                  -- get current query timeout
PRAGMA idasql.query_timeout_ms = 60000;          -- set timeout (0 disables)
PRAGMA idasql.queue_admission_timeout_ms = 120000;
PRAGMA idasql.max_queue = 64;                    -- 0 = unbounded
PRAGMA idasql.hints_enabled = 1;                 -- 1/0, on/off
PRAGMA idasql.enable_idapython = 1;              -- 1/0, enable SQL Python execution
PRAGMA idasql.timeout_push = 15000;              -- push old timeout, set new
PRAGMA idasql.timeout_pop;                       -- restore previous timeout
```

Recommended defaults for agent harnesses that issue concurrent requests:

```sql
PRAGMA idasql.max_queue = 0;                     -- unbounded queue
PRAGMA idasql.queue_admission_timeout_ms = 0;    -- wait in queue until completion
PRAGMA idasql.query_timeout_ms = 60000;          -- still cap execution time
```

When a `SELECT` times out, partial rows may be returned with `warnings` and `timed_out=true`.
For decompiler-heavy queries, `idasql` emits warnings that suggest adding `WHERE func_addr = ...`.

---

## Database Modification

Most write examples are documented next to their tables (`breakpoints`, `segments`, `names`, `instructions`, `types*`, `bookmarks`, `comments`, `ctree_lvars`, `ctree_labels`, `netnode_kv`).
Quick capability matrix:

| Table | INSERT | UPDATE columns | DELETE |
|-------|--------|---------------|--------|
| `breakpoints` | Yes | `enabled`, `type`, `size`, `flags`, `pass_count`, `condition`, `group` | Yes |
| `funcs` | Yes | `name`, `prototype`, `comment`, `rpt_comment`, `flags` | Yes |
| `names` | Yes | `name` | Yes |
| `comments` | Yes | `comment`, `rpt_comment` | Yes |
| `bookmarks` | Yes | `description` | Yes |
| `segments` | Yes | `name`, `class`, `perm` | Yes |
| `instructions` | — | `operand0_format_spec` .. `operand7_format_spec` | Yes |
| `bytes` | — | `value` | — |
| `patched_bytes` | — | — | — |
| `types` | Yes | Yes | Yes |
| `types_members` | Yes | Yes | Yes |
| `types_enum_values` | Yes | Yes | Yes |
| `ctree_lvars` | — | `name`, `type`, `comment` | — |
| `ctree_labels` | — | `name` | — |
| `netnode_kv` | Yes | `value` | Yes |

Instruction creation uses SQL functions rather than `INSERT`:
- `make_code(addr)`
- `make_code_range(start, end)`

Function creation uses table INSERT (calls `add_func()`):
- `INSERT INTO funcs(address) VALUES (...)`

Bulk byte loading from external files uses:
- `SELECT load_file_bytes(path, file_offset, address, size[, patchable])`

---

## Hex Address Formatting

IDA uses integer addresses. For display, use `printf()`:

```sql
-- 32-bit format
SELECT printf('0x%08X', address) as addr FROM funcs;

-- 64-bit format
SELECT printf('0x%016llX', address) as addr FROM funcs;

-- Auto-width
SELECT printf('0x%X', address) as addr FROM funcs;
```

---

## Server Modes

IDASQL supports HTTP-based server modes for remote queries: **HTTP REST** and **MCP** (both over HTTP/SSE).

---

### HTTP REST Server (Recommended)

Standard REST API for curl, Python, or any HTTP client.

```bash
idasql -s database.i64 --http              # default port 8081
idasql -s database.i64 --http 9000         # custom port
idasql -s database.i64 --http --token X    # with auth
```

```bash
curl -X POST http://localhost:8081/query -d "SELECT name, size FROM funcs LIMIT 5"
```

For endpoints, Python automation patterns, response format, and compatibility notes, see `references/server-guide.md`.

---
name: idapython
description: "Execute IDAPython via idasql, and query idasql from IDAPython with import idasql. Use when SQL surfaces are insufficient and direct IDA SDK access is needed via Python snippets or scripts, or when a script or plugin inside IDA needs SQL over the open database."
allowed-tools:
  - Bash
  - Read
  - Glob
  - Grep
---

---

## Running IDAPython: the `idapython_runs` table

Each run is a row. `INSERT` runs the code (or a file) and records it; `SELECT` reads what it printed.

```sql
INSERT INTO idapython_runs(code) VALUES ('print("hello from idapython")');
SELECT output, success, error FROM idapython_runs ORDER BY id DESC LIMIT 1;
```

| Column | Type | Meaning |
|--------|------|---------|
| `id` | INTEGER | Run number, increasing (newest = highest). Read the latest with `ORDER BY id DESC LIMIT 1`; `last_insert_rowid()` is not set |
| `code` | TEXT | Python source to run (give exactly one of `code` / `path`) |
| `path` | TEXT | A `.py` file to run instead |
| `sandbox` | TEXT | Optional namespace key: the same key keeps its globals across runs, different keys are isolated; NULL = the default global namespace |
| `show_output` | INTEGER | `0` (default): output is only captured. `1`: also shown in IDA's Output window. Set `1` when the user asked for the run; leave `0` for your own probes |
| `output` | TEXT | Everything the run printed |
| `success` | INTEGER | `1` ran to the end, `0` raised |
| `error` | TEXT | The Python error (traceback), NULL on success |
| `started` | TEXT | UTC start time, ISO 8601 |
| `duration_ms` | INTEGER | How long the run took |

- Only `code` / `path`, `sandbox` and `show_output` can be inserted; the run fills in the rest.
- **A Python error fails the `INSERT`** with that error, and the run is still recorded (read its
  `output` to see what it printed before failing).
- The last 100 runs are kept, in memory, for this session. `DELETE FROM idapython_runs [WHERE ...]`
  removes them.
- `INSERT ... SELECT` runs the code once per source row.

```sql
INSERT INTO idapython_runs(path) VALUES ('C:/temp/script.py');
INSERT INTO idapython_runs(code, sandbox) VALUES ('counter = globals().get("counter", 0) + 1; print(counter)', 'alpha');
INSERT INTO idapython_runs(code, show_output) VALUES ('print("the user sees this in IDA too")', 1);
SELECT id, success, substr(output, 1, 80) AS output FROM idapython_runs ORDER BY id DESC LIMIT 5;
```

### Runtime Guard

Python execution is disabled by default. Enable it with:

```sql
UPDATE runtime_settings SET value='1' WHERE key='enable_idapython';
```

Captured `print` output is **unbounded by default**. To bound a runaway or very
chatty run (so it can't exhaust memory / the response), set an optional byte cap;
`0` restores unbounded:

```sql
UPDATE runtime_settings SET value='65536' WHERE key='idapython_output_max';  -- cap at 64 KiB
UPDATE runtime_settings SET value='0'     WHERE key='idapython_output_max';  -- unbounded (default)
```

Output past the cap is dropped with a `...[idapython output truncated at N bytes]...` marker.

`idapython_echo` (default `0`) shows **every** run's output in IDA's Output window, whatever its
`show_output`:

```sql
UPDATE runtime_settings SET value='1' WHERE key='idapython_echo';
```

To confirm the current values of `enable_idapython`, `idapython_output_max` and
`idapython_echo`, query
`SELECT * FROM runtime_settings WHERE scope = 'idasql'`. The table is the
canonical writable runtime-control surface: read it with `SELECT`, and change
settable `value` cells with an exact-key `UPDATE`. Use
`SELECT * FROM runtime_settings` to include shared controls. See the `connect`
skill.

### Three Python Contexts (Important)

- **Host-side Python client** (outside IDA): use `requests.post(.../query, data=sql)` to send SQL over HTTP. The body may be one statement or a semicolon-separated script; every response uses the canonical `results[]` envelope (a single statement is an array of one — read `results[i].rows`). Use this for loops, bulk updates, and automation orchestration. See `connect` skill HTTP client patterns.
- **IDAPython via SQL** (inside IDA): `INSERT INTO idapython_runs(code | path)` when you need direct IDA SDK APIs in-process.
- **SQL from IDAPython** (inside IDA): `import idasql` in the IDA console, a script, a plugin, or a snippet queries the open database in-process (below). Never call the HTTP server from Python running inside IDA: the request waits for IDA's main thread, which is busy running that Python, and the call deadlocks.

Example contrast:

```python
# Host-side Python (outside IDA): sends SQL over HTTP
import requests
requests.post("http://127.0.0.1:8080/query", data="SELECT COUNT(*) FROM funcs")
```

```sql
-- IDAPython (inside IDA): executes Python in IDA runtime
INSERT INTO idapython_runs(code) VALUES ('import idaapi; print(idaapi.get_kernel_version())');
SELECT output FROM idapython_runs ORDER BY id DESC LIMIT 1;
```

### Sandbox Behavior

Each sandbox key creates an isolated Python namespace:
- Variables set in one sandbox are not visible in another
- The same sandbox key reuses its namespace across runs (state persists within a session)
- Without a sandbox key, code runs in the default global namespace

### Error Propagation

When a Python script raises an exception, the `INSERT` fails with it, and the run is recorded:
```sql
-- This will return an error: "NameError: name 'undefined_var' is not defined"
INSERT INTO idapython_runs(code) VALUES ('print(undefined_var)');
SELECT success, error FROM idapython_runs ORDER BY id DESC LIMIT 1;   -- 0, the traceback
```

---

## Calling idasql from Python (`import idasql`)

Python that runs inside IDA (the console, a script or plugin, an `idapython_runs` row) can query the open
database directly. idasql injects a small `idasql` module through IDAPython; idasql itself does not
link Python, and without IDAPython nothing changes.

```python
import idasql
idasql.available()                                  # True when an idasql engine is loaded
n = idasql.scalar("SELECT COUNT(*) FROM funcs")     # first cell of the first row, typed, or None
r = idasql.query("SELECT addr, name, size FROM funcs WHERE size > ? ORDER BY size DESC", 100)
for f in r:                                         # Row = tuple with attribute access
    print(hex(f.addr), f.name, f.size)
r.columns, r.rows, r.warnings, r.elapsed_ms, r.timed_out, r.partial
r.dicts()                                           # list of dicts
idasql.rows("SELECT * FROM segments")               # query(...).dicts()
idasql.query("SELECT ? + ?", [40, 2])               # one list/tuple = the parameter sequence
results = idasql.script("SELECT 1; SELECT 2 AS two") # several statements: one Result each
try:
    idasql.query("SELECT * FROM no_such_table")
except idasql.Error as e:
    print(e.message, e.sql)
```

| Value | Python type |
|-------|-------------|
| INTEGER | `int` (addresses come back as numbers) |
| REAL | `float` |
| TEXT | `str` (embedded NULs kept) |
| BLOB | `bytes` |
| NULL | `None` |

Parameters (`?`) are bound by SQLite, never formatted into the SQL: a quote in a name is data.
Python `int`, `float`, `str`, `bytes`, `bool` and `None` are accepted; integers up to 2^64-1 are
passed as their signed 64-bit value (how SQL holds high addresses).

Rules:

- **Main thread only.** In the GUI a call from another Python thread is forwarded to IDA's main
  thread and waits for it. Under idalib (`idasql` CLI, `--http`, `--mcp`) nothing services such a
  request, so it fails at once with `idasql.Error` instead of hanging.
- **SQL -> Python -> SQL works.** Inside an `idapython_runs` run, `import idasql` queries the same
  database; the inner query shares the outer statement's deadline and cancellation.
- **Python -> SQL -> Python is refused.** An `idapython_runs` INSERT issued through `idasql` fails
  with a clear error: IDAPython is not re-entrant from there.
- **Writes are writes.** Changes made through `idasql` are visible to every later query, roll back
  with checkpoints (see the `annotations` skill), and count as writes for the checkpoint redo guard.
- **Settings follow transactions.** `UPDATE runtime_settings` from Python takes effect when the
  statement that ran the Python commits (the run's `INSERT`, or the enclosing `BEGIN`); Python in the
  same run already reads the new value.
- **Lifetime.** When the database closes or the plugin unloads, a kept `idasql.query` raises
  `idasql.Error`. A different module already imported as `idasql` is never replaced (the bridge
  module carries `_idasql_bridge_version`).

Inside a run:

```sql
UPDATE runtime_settings SET value='1' WHERE key='enable_idapython';
INSERT INTO idapython_runs(code) VALUES ('
import idasql
big = idasql.query("SELECT addr, name FROM funcs WHERE size > ? ORDER BY size DESC LIMIT 5", 64)
for f in big:
    print(hex(f.addr), f.name)
');
```

---

## When to Use IDAPython vs SQL

| Use Case | Best Tool | Why |
|----------|-----------|-----|
| Query/filter/aggregate data | SQL | JOINs, CTEs, GROUP BY, window functions — SQL is purpose-built for this |
| Cross-table analysis | SQL | JOINing `funcs`, `xrefs`, `strings`, `ctree` is natural in SQL |
| Reporting and counting | SQL | COUNT, SUM, AVG, GROUP_CONCAT — no Python loop needed |
| Complex algorithms | IDAPython | Graph algorithms, custom pattern matching, ML pipelines |
| IDA SDK APIs not in idasql | IDAPython | Some IDA SDK features aren't exposed as SQL tables/functions |
| UI automation | IDAPython | Opening views, navigating cursor, triggering IDA actions |
| Existing scripts | IDAPython | Reuse existing `.py` scripts without rewriting in SQL |

**General rule:** Start with SQL. If you find yourself wanting nested loops, recursive algorithms, or IDA APIs that aren't exposed via idasql, reach for an `idapython_runs` INSERT as a bridge.

---

## Practical Use Cases

### Run a custom analysis script

```sql
-- Enable Python execution first
UPDATE runtime_settings SET value='1' WHERE key='enable_idapython';

-- Run a script that collects custom metrics
-- (in SQL this one is SELECT COUNT(*) FROM funcs WHERE flags & 4; prefer SQL when it can)
INSERT INTO idapython_runs(code) VALUES ('
import idautils, idc
count = 0
for func_addr in idautils.Functions():
    if idc.get_func_attr(func_addr, idc.FUNCATTR_FLAGS) & 0x4:  # FUNC_LIB
        count += 1
print(f"Library functions: {count}")
');
```

### Access IDA SDK APIs not exposed through idasql

```sql
-- Example: get processor-specific register names
INSERT INTO idapython_runs(code) VALUES ('
import ida_idp
for i in range(ida_idp.ph_get_regnames().__len__()):
    name = ida_idp.ph_get_regnames()[i]
    if name:
        print(f"{i}: {name}")
');
```

### Bridge pattern: Python produces JSON, SQL processes it

When you need Python's power for extraction but SQL's power for analysis (inside a Python script,
`import idasql` does the same without the JSON round trip):

```sql
-- Python extracts data as JSON
INSERT INTO idapython_runs(code) VALUES ('
import json, idautils, idc
result = []
for addr in idautils.Functions():
    flags = idc.get_func_attr(addr, idc.FUNCATTR_FLAGS)
    if flags & 0x4:  # FUNC_LIB
        result.append({"addr": addr, "name": idc.get_func_name(addr)})
print(json.dumps(result))
');

-- Then process the run's JSON output in SQL
SELECT json_extract(j.value, '$.name') AS name, json_extract(j.value, '$.addr') AS addr
FROM json_each((SELECT output FROM idapython_runs ORDER BY id DESC LIMIT 1)) AS j;
```

---

## See Also

- Check the relevant SQL skill first (`disassembly`, `decompiler`, `types`, `data`, `xrefs`, `annotations`, `debugger`) — fall through to IDAPython only when no SQL surface exists for the task.
- `functions` — the SQL function catalog; verify a scalar/helper doesn't already exist before scripting.

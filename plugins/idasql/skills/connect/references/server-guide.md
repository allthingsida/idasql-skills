# HTTP REST Server Guide

Standard REST API that works with curl, Python, any HTTP client, or LLM tools.

## Starting the Server

```bash
# Default port 8080
idasql -s database.i64 --http

# Custom port and bind address
idasql -s database.i64 --http 9000 --bind 0.0.0.0

# With authentication
idasql -s database.i64 --http 8080 --token mysecret
```

## HTTP Endpoints

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/` | GET | No | Server greeting |
| `/help` | GET | No | API documentation (for LLM discovery) |
| `/query` | POST | Yes* | Execute SQL query or semicolon-separated script |
| `/cancel` | POST | Yes* | Cooperatively cancel query requests that are already in flight |
| `/status` | GET | Yes* | Health check |
| `/shutdown` | POST | Yes* | Stop server |

*Auth required only if `--token` was specified.

Raw SQL is the portable request body in every server mode:
`--data-binary "SELECT …"`. The REPL/plugin `.http` server additionally accepts an
`application/json` object with a string `sql` field and optional Boolean
`continue_on_error` / `include_sql` fields. Standalone CLI `--http` treats every
body as raw SQL, so do not send the JSON object form when a client must work
across both modes. The response is JSON in either mode.

## Example with curl

```bash
# Get API documentation
curl http://localhost:8080/help

# Execute SQL query
curl -X POST http://localhost:8080/query --data-binary "SELECT name, size FROM funcs LIMIT 5"

# Execute a short SQL script
curl -X POST http://localhost:8080/query --data-binary "SELECT * FROM binary; SELECT COUNT(*) FROM funcs;"

# Continue after a failed statement (standalone CLI and REPL/plugin servers)
curl -X POST "http://localhost:8080/query?continue_on_error=1&include_sql=1" \
     --data-binary "SELECT * FROM missing_table; SELECT COUNT(*) FROM funcs;"

# REPL/plugin .http only: equivalent JSON request options
curl -X POST http://localhost:8080/query \
     -H "Content-Type: application/json" \
     -d '{"sql":"SELECT * FROM binary; SELECT COUNT(*) FROM funcs;","continue_on_error":true,"include_sql":true}'

# With authentication
curl -X POST http://localhost:8080/query \
     -H "Authorization: Bearer mysecret" \
     --data-binary "SELECT * FROM funcs"

# Check status
curl http://localhost:8080/status

# From another client, request cancellation of a long-running query
curl -X POST -d '' http://localhost:8080/cancel
```

## Cooperative Cancellation

`POST /cancel` advances the server's cancellation epoch. Query requests that
started before that POST observe the request when their current operation next
polls for cancellation; later queries start cleanly. Send the same bearer token
or `X-XSQL-Token` used for `/query` when authentication is enabled.

Cancellation is cooperative, so response latency depends on the table or SQL
operation being executed. A cancelled result-bearing statement can remain a
partial success with `partial: true` and a warning containing `cancelled`; it is
not reported as `timed_out`. A cancelled statement that has no result rows can
return a hard `Query cancelled` error.

## Python Automation Patterns

Use `curl` for quick/manual queries. Use a short Python script when you need loops, batching, and reusable workflows.

```python
import requests

URL = "http://127.0.0.1:8080/query"
HEADERS = {}  # If --token is enabled: {"Authorization": "Bearer mysecret"}

def post_sql(sql: str):
    r = requests.post(URL, headers=HEADERS, data=sql, timeout=30)
    r.raise_for_status()
    j = r.json()
    ok = j.get("success")
    if ok is None:
        # Compatibility: some builds omit "success" on successful responses.
        ok = "error" not in j
    if not ok:
        raise RuntimeError(f"SQL failed: {j.get('error')} | {sql}")
    return j

# Pattern 1: single query (single statement is results[0])
results = post_sql("SELECT name, size FROM funcs LIMIT 5").get("results", [])
rows = results[0].get("rows", []) if results else []
print(rows)

# Pattern 1b: semicolon-separated script
script_payload = post_sql("SELECT * FROM binary; SELECT COUNT(*) FROM funcs;")
for statement in script_payload.get("results", []):
    print(statement.get("columns", []), statement.get("rows", []))
```

```python
import requests

URL = "http://127.0.0.1:8080/query"
HEADERS = {}  # If --token is enabled: {"Authorization": "Bearer mysecret"}

def post_sql(sql: str):
    r = requests.post(URL, headers=HEADERS, data=sql, timeout=30)
    r.raise_for_status()
    j = r.json()
    ok = j.get("success")
    if ok is None:
        # Compatibility: some builds omit "success" on successful responses.
        ok = "error" not in j
    if not ok:
        raise RuntimeError(f"SQL failed: {j.get('error')} | {sql}")
    return j

# Pattern 2: batch mutation + refresh
func = 0x180021137
# Each addr below must already be a resolved writable pseudocode anchor from a
# prior inspection pass. Do not use guessed function-entry eas.
updates = [
    (0x180021798, "key%5 selects junk prefix byte"),
    (0x1800217C4, "store thunk address in IAT slot"),
]

for addr, comment in updates:
    safe = comment.replace("'", "''")
    sql = (
        "UPDATE pseudocode SET comment = '{c}' "
        "WHERE func_addr = {f} AND addr = {addr};"
    ).format(c=safe, f=func, addr=addr)
    post_sql(sql)

# Refresh and re-read for verification
post_sql(f"SELECT decompile({func}, 1);")
check = post_sql(f"SELECT addr, comment FROM pseudocode WHERE func_addr = {func};")
check_rows = check.get("results", [{}])[0].get("rows", [])
print(f"Verified rows: {len(check_rows)}")
```

```python
import requests

URL = "http://127.0.0.1:8080/query"

def post_sql(sql: str):
    r = requests.post(URL, data=sql, timeout=30)
    r.raise_for_status()
    j = r.json()
    ok = j.get("success")
    if ok is None:
        ok = "error" not in j
    if not ok:
        raise RuntimeError(f"SQL failed: {j.get('error')} | {sql}")
    return j

# Pattern 3: pseudocode dump reading results[0].rows
sql = (
    "SELECT line_num, printf('0x%X', addr) AS addr, line "
    "FROM pseudocode WHERE func_addr = 0x180004344"
)
payload = post_sql(sql)
rows = payload.get("results", [{}])[0].get("rows", [])
for line_num, addr, line in rows:
    print(f"{str(line_num):>3} | {addr:18} | {line}")
```

## Light Guardrails for Scripted Clients

- Check for errors on every request and fail fast on first SQL error.
- Treat missing `success` on success responses as compatible (`ok = j.get("success", "error" not in j)`).
- Include the SQL text (or context) in error messages for quick debugging.
- Use explicit request timeouts.
- After batch writes, refresh/re-read (`decompile(..., 1)` or targeted `SELECT`) to verify effects.

This same pattern works in any language with HTTP support (JavaScript, PowerShell, Go, Rust, etc.).

## Response Format (JSON)

**Every `/query` response uses the canonical script envelope** — even a single
statement is returned as an array of one under `results[]`. There is no
separate top-level `rows`/`columns` shape and no `statements[]` key.

```json
{
  "success": true,
  "statement_count": 1,
  "results": [
    {"statement_index": 0, "success": true,
     "columns": ["name", "size"], "rows": [["main", "500"]],
     "row_count": 1, "elapsed_ms": 0, "error": null}
  ],
  "row_count_total": 1,
  "elapsed_ms_total": 0,
  "first_error_index": null
}
```

A semicolon-separated script returns one entry per statement in `results[]`:

```json
{
  "success": true,
  "statement_count": 2,
  "results": [
    {"statement_index": 0, "success": true, "columns": ["summary"], "rows": [["..."]], "row_count": 1, "error": null},
    {"statement_index": 1, "success": true, "columns": ["COUNT(*)"], "rows": [["42"]], "row_count": 1, "error": null}
  ],
  "row_count_total": 2,
  "first_error_index": null
}
```

On a statement error, that entry's `success` is `false` and `error` carries the
message; top-level `success` is `false` and `first_error_index` points at the
first failing statement. Fail-fast is the default — both standalone CLI and
REPL/plugin HTTP servers honor `?continue_on_error=1` to run every statement
regardless. Add `?include_sql=1` when each result should echo its statement.

## Compatibility Notes

- The shape is identical regardless of statement count \u2014 always read
  `results[i].columns` / `results[i].rows`, never a top-level `rows`.
- Check per-statement status via `results[i].success` / `results[i].error`, or
  `first_error_index` for the first failure.
- Invalid/non-UTF8 bytes in query results are escaped in JSON-safe form (for
  example `\u0097`) rather than crashing the response.

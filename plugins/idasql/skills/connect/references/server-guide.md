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
| `/` | GET | No | Welcome message |
| `/help` | GET | No | API documentation (for LLM discovery) |
| `/query` | POST | Yes* | Execute SQL query or semicolon-separated script (body = raw SQL) |
| `/status` | GET | Yes* | Health check |
| `/shutdown` | POST | Yes* | Stop server |

*Auth required only if `--token` was specified.

## Example with curl

```bash
# Get API documentation
curl http://localhost:8080/help

# Execute SQL query
curl -X POST http://localhost:8080/query -d "SELECT name, size FROM funcs LIMIT 5"

# Execute a short SQL script
curl -X POST http://localhost:8080/query -d "SELECT * FROM welcome; SELECT COUNT(*) FROM funcs;"

# With authentication
curl -X POST http://localhost:8080/query \
     -H "Authorization: Bearer mysecret" \
     -d "SELECT * FROM funcs"

# Check status
curl http://localhost:8080/status
```

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

# Pattern 1: single query
rows = post_sql("SELECT name, size FROM funcs LIMIT 5").get("rows", [])
print(rows)

# Pattern 1b: semicolon-separated script
script_payload = post_sql("SELECT * FROM welcome; SELECT COUNT(*) FROM funcs;")
for statement in script_payload.get("statements", []):
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
# Each ea below must already be a resolved writable pseudocode anchor from a
# prior inspection pass. Do not use guessed function-entry eas.
updates = [
    (0x180021798, "key%5 selects junk prefix byte"),
    (0x1800217C4, "store thunk address in IAT slot"),
]

for ea, comment in updates:
    safe = comment.replace("'", "''")
    sql = (
        "UPDATE pseudocode SET comment = '{c}' "
        "WHERE func_addr = {f} AND ea = {ea};"
    ).format(c=safe, f=func, ea=ea)
    post_sql(sql)

# Refresh and re-read for verification
post_sql(f"SELECT decompile({func}, 1);")
check = post_sql(f"SELECT ea, comment FROM pseudocode WHERE func_addr = {func};")
print(f"Verified rows: {len(check.get('rows', []))}")
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

# Pattern 3: pseudocode dump without KeyError('rows')
sql = (
    "SELECT line_num, printf('0x%X', ea) AS ea, line "
    "FROM pseudocode WHERE func_addr = 0x180004344"
)
payload = post_sql(sql)
for line_num, ea, line in payload.get("rows", []):
    print(f"{str(line_num):>3} | {ea:18} | {line}")
```

## Light Guardrails for Scripted Clients

- Check for errors on every request and fail fast on first SQL error.
- Treat missing `success` on success responses as compatible (`ok = j.get("success", "error" not in j)`).
- Include the SQL text (or context) in error messages for quick debugging.
- Use explicit request timeouts.
- After batch writes, refresh/re-read (`decompile(..., 1)` or targeted `SELECT`) to verify effects.

This same pattern works in any language with HTTP support (JavaScript, PowerShell, Go, Rust, etc.).

## Response Format (JSON)

Single statements keep the standard response shape:

```json
{"success": true, "columns": ["name", "size"], "rows": [["main", "500"]], "row_count": 1}
```

Semicolon-separated scripts return one result object per statement:

```json
{"success": true, "statements": [{"columns": ["summary"], "rows": [["..."]], "row_count": 1}, {"columns": ["COUNT(*)"], "rows": [["42"]], "row_count": 1}], "statement_count": 2}
```

```json
{"success": false, "error": "no such table: bad_table"}
```

## Compatibility Notes

- Most builds include `success` in both success and error responses.
- Some builds may omit `success` on successful responses and return only `columns`, `rows`, and `row_count`.
- Multi-statement support is additive: clients that only send one SQL statement can continue to read top-level `rows`.
- Clients that send scripts must read `statements[]`; each entry has its own `columns`, `rows`, and `row_count`.
- Invalid/non-UTF8 bytes in query results are escaped in JSON-safe form (for example `\u0097`) rather than crashing the response.
- In clients, check for `error` first, then consume rows with `payload.get("rows", [])` to avoid `KeyError`.

---
name: idapython
description: "Execute IDAPython via idasql. Use when SQL surfaces are insufficient and direct IDA SDK access is needed via Python snippets or scripts."
allowed-tools:
  - Bash
  - Read
  - Glob
  - Grep
---

---

## Python Execution SQL Functions

| Function | Description |
|----------|-------------|
| `idapython_snippet(code[, sandbox])` | Execute Python snippet and return captured output text |
| `idapython_file(path[, sandbox])` | Execute Python file and return captured output text |

### Runtime Guard

Python execution is disabled by default. Enable it with:

```sql
PRAGMA idasql.enable_idapython = 1;
```

### Examples

```sql
SELECT idapython_snippet('print("hello from idapython")');
SELECT idapython_file('C:/temp/script.py');
SELECT idapython_snippet('counter = globals().get("counter", 0) + 1; print(counter)', 'alpha');
```

### Notes

- Disabled by default until pragma is enabled
- Python exceptions propagate as SQL errors
- `sandbox` isolates/persists Python globals by sandbox key

### Two Python Contexts (Important)

- **Host-side Python client** (outside IDA): use `requests.post(.../query, data=sql)` to batch SQL over HTTP. Use this for loops, bulk updates, and automation orchestration. See `connect` skill HTTP client patterns.
- **IDAPython via SQL** (inside IDA): use `idapython_snippet()` / `idapython_file()` when you need direct IDA SDK APIs in-process.

Example contrast:

```python
# Host-side Python (outside IDA): sends SQL over HTTP
import requests
requests.post("http://127.0.0.1:8081/query", data="SELECT COUNT(*) FROM funcs")
```

```sql
-- IDAPython (inside IDA): executes Python in IDA runtime
SELECT idapython_snippet('import idaapi; print(idaapi.get_kernel_version())');
```

### Sandbox Behavior

Each sandbox key creates an isolated Python namespace:
- Variables set in one sandbox are not visible in another
- The same sandbox key reuses its namespace across calls (state persists within a session)
- Without a sandbox key, code runs in the default global namespace

### Error Propagation

When a Python script raises an exception, it propagates as a SQL error:
```sql
-- This will return an error: "NameError: name 'undefined_var' is not defined"
SELECT idapython_snippet('print(undefined_var)');
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

**General rule:** Start with SQL. If you find yourself wanting nested loops, recursive algorithms, or IDA APIs that aren't exposed via idasql, reach for `idapython_snippet()` as a bridge.

---

## Practical Use Cases

### Run a custom analysis script

```sql
-- Enable Python execution first
PRAGMA idasql.enable_idapython = 1;

-- Run a script that collects custom metrics
SELECT idapython_snippet('
import idautils, idc
count = 0
for func_ea in idautils.Functions():
    if idc.get_func_attr(func_ea, idc.FUNCATTR_FLAGS) & 0x4:  # FUNC_LIB
        count += 1
print(f"Library functions: {count}")
');
```

### Access IDA SDK APIs not exposed through idasql

```sql
-- Example: get processor-specific register names
SELECT idapython_snippet('
import ida_idp
for i in range(ida_idp.ph_get_regnames().__len__()):
    name = ida_idp.ph_get_regnames()[i]
    if name:
        print(f"{i}: {name}")
');
```

### Bridge pattern: Python produces JSON, SQL processes it

When you need Python's power for extraction but SQL's power for analysis:

```sql
-- Python extracts data as JSON
SELECT idapython_snippet('
import json, idautils, idc
result = []
for ea in idautils.Functions():
    flags = idc.get_func_attr(ea, idc.FUNCATTR_FLAGS)
    if flags & 0x4:  # FUNC_LIB
        result.append({"ea": ea, "name": idc.get_func_name(ea)})
print(json.dumps(result))
');

-- Then process the JSON output in SQL using json_each()
-- (copy the output from above into the query)
```

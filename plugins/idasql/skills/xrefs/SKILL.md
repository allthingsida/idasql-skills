---
name: xrefs
description: "Analyze IDA cross-references. Use when asked about callers, callees, imports, data refs, call graphs, or dependency chains."
metadata:
  argument-hint: "[function-name or address]"
allowed-tools:
  - Bash
  - Read
  - Glob
  - Grep
---

---

## Trigger Intents

Use this skill when user asks:
- "Who calls this?" / "What does this call?"
- "Where is this string/import referenced?"
- "Show call graph dependencies."

Route to:
- `grep` for candidate entity lookup by name/pattern before relationship analysis
- `analysis` for broader triage context
- `decompiler` for semantic interpretation after graph narrowing
- `disassembly` for instruction-level call-site proof

---

## Do This First (Warm-Start Sequence)

```sql
-- 1) Core relation volume
SELECT COUNT(*) AS xref_count FROM xrefs;

-- 2) Top imports (dependency hints)
SELECT module, COUNT(*) AS import_count
FROM imports
GROUP BY module
ORDER BY import_count DESC;

-- 3) Most called functions
SELECT printf('0x%X', to_ea) AS callee, COUNT(*) AS callers
FROM xrefs
WHERE is_code = 1
GROUP BY to_ea
ORDER BY callers DESC
LIMIT 20;
```

Interpretation guidance:
- Use relation counts to prioritize hotspots before expensive deep analysis.
- Prefer indexed filters (`to_ea`/`from_ea`) for fast response.

---

## Failure and Recovery

- Full-scan query too slow:
  - Add `to_ea = X` or `from_ea = X` constraints.
- Target unresolved by name:
  - Resolve/verify address first (`name_at`, explicit EA literals).
- Sparse results:
  - Pivot through `imports`, `strings`, or `disasm_calls` joins.

---

## Handoff Patterns

1. `xrefs` -> `decompiler` for top candidate function semantics.
2. `xrefs` -> `analysis` for campaign-level synthesis.
3. `xrefs` -> `annotations` to persist relationship findings.

---

## xrefs
Cross-references - the most important table for understanding code relationships.

| Column | Type | Description |
|--------|------|-------------|
| `from_ea` | INT | Source address (who references) |
| `to_ea` | INT | Target address (what is referenced) |
| `type` | INT | Xref type code |
| `is_code` | INT | 1=code xref (call/jump), 0=data xref |
| `from_func` | INT | Pre-computed containing function address (0 when not in a function) |

```sql
-- Who calls function at 0x401000?
SELECT printf('0x%X', from_ea) as caller FROM xrefs WHERE to_ea = 0x401000 AND is_code = 1;

-- What does function at 0x401000 reference?
SELECT printf('0x%X', to_ea) as target FROM xrefs WHERE from_ea >= 0x401000 AND from_ea < 0x401100;
```

---

## imports
Imported functions from external libraries.

| Column | Type | Description |
|--------|------|-------------|
| `address` | INT | Import address (IAT entry) |
| `name` | TEXT | Import name |
| `module` | TEXT | Module/DLL name |
| `ordinal` | INT | Import ordinal |

```sql
-- Imports from kernel32.dll
SELECT name FROM imports WHERE module LIKE '%kernel32%';
```

---

## Convenience Views

### callers
Who calls each function. Uses `name_at()` scalar for caller name resolution (no JOIN needed).

| Column | Type | Description |
|--------|------|-------------|
| `func_addr` | INT | Target function address |
| `caller_addr` | INT | Xref source address |
| `caller_name` | TEXT | Calling function name (via `name_at()`) |
| `caller_func_addr` | INT | Calling function start (from `from_func`) |

Underlying query:
```sql
SELECT x.to_ea as func_addr, x.from_ea as caller_addr,
       COALESCE(name_at(x.from_func), printf('sub_%X', x.from_func)) as caller_name,
       x.from_func as caller_func_addr
FROM xrefs x WHERE x.is_code = 1 AND x.from_func != 0
```

```sql
-- Who calls function at 0x401000?
SELECT caller_name, printf('0x%X', caller_addr) as from_addr
FROM callers WHERE func_addr = 0x401000;

-- Most called functions
SELECT printf('0x%X', func_addr) as addr, COUNT(*) as callers
FROM callers GROUP BY func_addr ORDER BY callers DESC LIMIT 10;
```

### callees
What each function calls. Inverse of callers view. Uses `from_func` for efficient function-level grouping.

| Column | Type | Description |
|--------|------|-------------|
| `func_addr` | INT | Calling function address (from `from_func`) |
| `func_name` | TEXT | Calling function name (via `name_at()`) |
| `callee_addr` | INT | Called address |
| `callee_name` | TEXT | Called function/symbol name (via `name_at()`) |

```sql
-- What does main call?
SELECT callee_name, printf('0x%X', callee_addr) as addr
FROM callees WHERE func_name LIKE '%main%';

-- Functions making most calls
SELECT func_name, COUNT(*) as call_count
FROM callees GROUP BY func_addr ORDER BY call_count DESC LIMIT 10;
```

### string_refs
Pre-joined view of string cross-references with containing function info.

| Column | Type | Description |
|--------|------|-------------|
| `string_addr` | INT | Address of the string |
| `string_value` | TEXT | String content |
| `string_length` | INT | String length |
| `ref_addr` | INT | Address of the referencing instruction |
| `func_addr` | INT | Containing function address |
| `func_name` | TEXT | Containing function name |

```sql
-- Strings referenced by a specific function
SELECT string_value, func_name FROM string_refs WHERE func_addr = 0x401000;

-- Find functions referencing password-related strings
SELECT string_value, func_name FROM string_refs WHERE string_value LIKE '%password%';

-- Most referenced strings
SELECT string_value, COUNT(*) as ref_count
FROM string_refs GROUP BY string_addr ORDER BY ref_count DESC LIMIT 10;
```

### data_refs
Cached table of data (non-code) cross-references with containing function info.
Whole-program aggregates are supported.

| Column | Type | Description |
|--------|------|-------------|
| `from_addr` | INT | Source address of the reference |
| `to_addr` | INT | Target data address |
| `from_func_addr` | INT | Containing function address |
| `from_func_name` | TEXT | Containing function name |
| `ref_type` | INT | Xref type code |

```sql
-- Data references from a specific function
SELECT * FROM data_refs WHERE from_func_addr = 0x401000;

-- Functions with most data references
SELECT from_func_name, COUNT(*) as data_ref_count
FROM data_refs GROUP BY from_func_addr ORDER BY data_ref_count DESC LIMIT 10;
```

---

## call_graph
Table-valued function for BFS call graph traversal. Uses HIDDEN parameters for traversal control.

| Column | Type | Description |
|--------|------|-------------|
| `func_addr` | INT | Function address in the graph |
| `func_name` | TEXT | Function name |
| `depth` | INT | BFS depth from start |
| `parent_addr` | INT | Parent function address in the traversal |
| `start` | INT | **HIDDEN** — Starting function address |
| `direction` | TEXT | **HIDDEN** — `'down'` (callees), `'up'` (callers), or `'both'` |
| `max_depth` | INT | **HIDDEN** — Maximum traversal depth |

**Always provide WHERE constraints for all 3 hidden parameters.**

```sql
-- Forward call tree from main
SELECT func_name, depth FROM call_graph
WHERE start = (SELECT address FROM funcs WHERE name = 'main')
  AND direction = 'down' AND max_depth = 5;

-- All transitive callers
SELECT func_name, depth FROM call_graph
WHERE start = 0x405000 AND direction = 'up' AND max_depth = 10;

-- Bidirectional exploration
SELECT func_name, depth FROM call_graph
WHERE start = 0x401000 AND direction = 'both' AND max_depth = 3;

-- Join with string_refs to find strings reachable from a function
SELECT DISTINCT sr.string_value, sr.func_name
FROM call_graph cg
JOIN string_refs sr ON sr.func_addr = cg.func_addr
WHERE cg.start = 0x401000 AND cg.direction = 'down' AND cg.max_depth = 3;

-- Imported APIs reachable from a function's call tree
SELECT DISTINCT i.module, i.name as api
FROM call_graph cg
JOIN disasm_calls dc ON dc.func_addr = cg.func_addr
JOIN imports i ON dc.callee_addr = i.address
WHERE cg.start = 0x401000 AND cg.direction = 'down' AND cg.max_depth = 5
ORDER BY i.module, i.name;
```

Performance: BFS with visited set. O(reachable functions). Always constrain hidden params.
Use this pattern when the destination is an import.

---

## shortest_path
Table-valued function for finding the shortest call path between two functions. Uses bidirectional BFS.

| Column | Type | Description |
|--------|------|-------------|
| `step` | INT | Step number in the path (0 = source) |
| `func_addr` | INT | Function address at this step |
| `func_name` | TEXT | Function name at this step |
| `from_addr` | INT | **HIDDEN** — Source function address |
| `to_addr` | INT | **HIDDEN** — Destination function address |
| `max_depth` | INT | **HIDDEN** — Maximum search depth |

**Always provide WHERE constraints for all 3 hidden parameters.**
Both endpoints must resolve to functions. Imported API addresses from `imports`
are not valid `shortest_path` endpoints.

```sql
-- Find shortest call path between two functions
SELECT step, func_name FROM shortest_path
WHERE from_addr = (SELECT address FROM funcs WHERE name = 'main')
  AND to_addr = (SELECT address FROM funcs WHERE name = 'target_func')
  AND max_depth = 20;

-- Check reachability between two functions
SELECT COUNT(*) > 0 as reachable FROM shortest_path
WHERE from_addr = 0x401000 AND to_addr = 0x405000 AND max_depth = 20;

-- Annotate path steps with call count and string refs
SELECT sp.step, sp.func_name,
       (SELECT COUNT(*) FROM disasm_calls dc WHERE dc.func_addr = sp.func_addr) as calls_made,
       (SELECT COUNT(*) FROM string_refs sr WHERE sr.func_addr = sp.func_addr) as strings_used
FROM shortest_path sp
WHERE sp.from_addr = 0x401000 AND sp.to_addr = 0x405000 AND sp.max_depth = 20
ORDER BY sp.step;
```

Performance: Bidirectional BFS. O(b^(d/2)) where b is branching factor and d is path length. Returns empty result set if no path exists within max_depth.

---

## SQL Functions — Cross-References

| Function | Description |
|----------|-------------|
| `xrefs_to(addr)` | JSON array of xrefs TO address |
| `xrefs_from(addr)` | JSON array of xrefs FROM address |

---

## grep

Use `grep` to resolve internal symbols, types, and members before doing relationship analysis. Use `imports` when the callee may exist only as an imported API.
Canonical usage lives in `../grep/SKILL.md`.
For canonical schema and owner mapping, see `../connect/references/schema-catalog.md` (`grep`).

```sql
-- Resolve internal functions with grep
SELECT name, kind, address
FROM grep
WHERE pattern = 'main%' AND kind = 'function'
ORDER BY name;

-- Resolve imported APIs with imports
SELECT module, name, address
FROM imports
WHERE name LIKE 'CreateFile%'
ORDER BY module, name;

-- Then pivot into callers/callees/xrefs
SELECT caller_name, printf('0x%X', caller_addr) AS from_addr
FROM callers
WHERE func_addr = (
    SELECT address
    FROM imports
    WHERE name = 'CreateFileW'
    ORDER BY name
    LIMIT 1
);
```

---

## Performance Rules

### Constraint Pushdown

The `xrefs` table has **optimized filters** using efficient IDA SDK APIs:

| Filter | Cost | Behavior |
|--------|------|----------|
| `to_ea = X` | 0.5 | O(xrefs to X) — fast, uses IDA's xref index |
| `from_ea = X` | 0.5 | O(xrefs from X) — fast, uses IDA's xref index |
| `from_func = X` | 1.0 | O(callees of X) — uses XrefsFromFuncIterator |
| No equality filter on `to_ea` / `from_ea` / `from_func` | — | Falls back to a cache of xrefs to function entry points only — avoid relying on it for complete import/data/non-function coverage |

**Always filter xrefs by `to_ea`, `from_ea`, or `from_func`. Avoid unconstrained scans.**

```sql
-- FAST: xrefs to a specific target
SELECT * FROM xrefs WHERE to_ea = 0x401000;

-- FAST: xrefs from a specific source
SELECT * FROM xrefs WHERE from_ea = 0x401000;

-- FAST: all xrefs originating from a function
SELECT * FROM xrefs WHERE from_func = 0x401000;

-- INCOMPLETE/avoid: unconstrained scan falls back to a function-entry cache
SELECT * FROM xrefs WHERE is_code = 1;
```

---

## Common Xref Patterns

### Find Most Called Functions

```sql
SELECT f.name, COUNT(*) as caller_count
FROM funcs f
JOIN xrefs x ON f.address = x.to_ea
WHERE x.is_code = 1
GROUP BY f.address
ORDER BY caller_count DESC
LIMIT 10;
```

### Find Functions Calling a Specific API

```sql
SELECT DISTINCT func_at(from_ea) as caller
FROM xrefs
WHERE to_ea = (SELECT address FROM imports WHERE name = 'CreateFileW');
```

### String Cross-Reference Analysis

```sql
SELECT s.content, func_at(x.from_ea) as used_by
FROM strings s
JOIN xrefs x ON s.address = x.to_ea
WHERE s.content LIKE '%password%';
```

### Import Dependency Map

```sql
-- Which modules does each function depend on?
SELECT f.name as func_name, i.module, COUNT(*) as api_count
FROM funcs f
JOIN disasm_calls dc ON dc.func_addr = f.address
JOIN imports i ON dc.callee_addr = i.address
GROUP BY f.address, i.module
ORDER BY f.name, api_count DESC;
```

### Data Section References

```sql
-- Functions referencing data sections
SELECT
    f.name,
    s.name as segment,
    COUNT(*) as data_refs
FROM funcs f
JOIN xrefs x ON x.from_ea BETWEEN f.address AND f.end_ea
JOIN segments s ON x.to_ea BETWEEN s.start_ea AND s.end_ea
WHERE s.class = 'DATA' AND x.is_code = 0
GROUP BY f.address, s.name
ORDER BY data_refs DESC
LIMIT 20;
```

---

## Advanced Xref Patterns (CTEs and Recursive Queries)

> **Prefer `call_graph` over manual CTEs.** The `call_graph` table uses C++ BFS with a visited set — correct BFS depths, no duplicate expansion on diamond-shaped call graphs, and early termination.

**Before** (recursive CTE — no visited tracking, exponential on diamond graphs):
```sql
WITH RECURSIVE call_chain(root, current_func, depth) AS (
    SELECT 0x401000, callee_addr, 1
    FROM disasm_calls WHERE func_addr = 0x401000
    UNION ALL
    SELECT cc.root, dc.callee_addr, cc.depth + 1
    FROM call_chain cc
    JOIN disasm_calls dc ON dc.func_addr = cc.current_func
    WHERE cc.depth < 10
)
SELECT DISTINCT current_func, MIN(depth) FROM call_chain GROUP BY current_func;
```

**After** (call_graph table — C++ BFS with visited set, correct depths):
```sql
SELECT func_addr, func_name, depth FROM call_graph
WHERE start = 0x401000 AND direction = 'down' AND max_depth = 10;
```

### Recursive Call Graph — Forward Traversal

> **Note:** For targeted traversal, prefer the `call_graph` table which uses C++ BFS with visited tracking. Use recursive CTEs only when you need custom join logic (e.g., filtering by callee properties at each step).

Find all functions reachable from a starting function (up to depth 5):

```sql
-- Preferred: use call_graph table
SELECT func_name, depth FROM call_graph
WHERE start = (SELECT address FROM funcs WHERE name = 'main')
  AND direction = 'down' AND max_depth = 5;

-- Manual CTE (when custom filtering is needed at each step):
WITH RECURSIVE cg AS (
    SELECT address as func_addr, name, 0 as depth
    FROM funcs WHERE name = 'main'

    UNION ALL

    SELECT f.address, f.name, cg.depth + 1
    FROM cg
    JOIN disasm_calls dc ON dc.func_addr = cg.func_addr
    JOIN funcs f ON f.address = dc.callee_addr
    WHERE cg.depth < 5
      AND dc.callee_addr != 0
)
SELECT DISTINCT func_addr, name, MIN(depth) as min_depth
FROM cg
GROUP BY func_addr
ORDER BY min_depth, name;
```

### Recursive Call Graph — Reverse (Who Calls This?)

> **Note:** For targeted traversal, prefer the `call_graph` table with `direction = 'up'`. Use recursive CTEs only when you need custom join logic.

Trace callers transitively up to depth 5:

```sql
-- Preferred: use call_graph table
SELECT func_name, depth FROM call_graph
WHERE start = 0x401000 AND direction = 'up' AND max_depth = 5;

-- Manual CTE (when custom filtering is needed at each step):
WITH RECURSIVE callers_cte AS (
    SELECT DISTINCT dc.func_addr, 1 as depth
    FROM disasm_calls dc
    WHERE dc.callee_addr = 0x401000

    UNION ALL

    SELECT DISTINCT dc.func_addr, c.depth + 1
    FROM callers_cte c
    JOIN disasm_calls dc ON dc.callee_addr = c.func_addr
    WHERE c.depth < 5
)
SELECT func_at(func_addr) as caller, MIN(depth) as distance
FROM callers_cte
GROUP BY func_addr
ORDER BY distance, caller;
```

### CTE: Functions That Both Call malloc AND Check NULL

```sql
WITH malloc_callers AS (
    SELECT DISTINCT func_addr
    FROM disasm_calls
    WHERE callee_name LIKE '%malloc%'
),
null_checkers AS (
    SELECT DISTINCT func_addr
    FROM ctree_v_comparisons
    WHERE rhs_num = 0 AND op_name = 'cot_eq'
)
SELECT f.name
FROM funcs f
JOIN malloc_callers m ON f.address = m.func_addr
JOIN null_checkers n ON f.address = n.func_addr;
```

### CTE: Memory Allocation Without Free (Potential Leaks)

```sql
WITH allocators AS (
    SELECT func_addr, COUNT(*) as alloc_count
    FROM disasm_calls
    WHERE callee_name LIKE '%alloc%' OR callee_name LIKE '%malloc%'
    GROUP BY func_addr
),
freers AS (
    SELECT func_addr, COUNT(*) as free_count
    FROM disasm_calls
    WHERE callee_name LIKE '%free%'
    GROUP BY func_addr
)
SELECT f.name,
       COALESCE(a.alloc_count, 0) as allocations,
       COALESCE(r.free_count, 0) as frees
FROM funcs f
LEFT JOIN allocators a ON f.address = a.func_addr
LEFT JOIN freers r ON f.address = r.func_addr
WHERE a.alloc_count > 0 AND COALESCE(r.free_count, 0) = 0
ORDER BY allocations DESC;
```

### EXISTS: Functions With at Least One String Reference

More efficient than JOIN + DISTINCT for existence checks:

```sql
SELECT f.name
FROM funcs f
WHERE EXISTS (
    SELECT 1 FROM xrefs x
    JOIN strings s ON x.to_ea = s.address
    WHERE x.from_ea BETWEEN f.address AND f.end_ea
);
```

### EXISTS: Leaf Functions (No Outgoing Calls)

```sql
SELECT f.name, f.size
FROM funcs f
WHERE NOT EXISTS (
    SELECT 1 FROM disasm_calls dc
    WHERE dc.func_addr = f.address
)
ORDER BY f.size DESC;
```

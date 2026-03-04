---
name: xrefs
description: "Analyze IDA cross-references: callers, callees, imports, data refs, grep search."
---

---

## Trigger Intents

Use this skill when user asks:
- "Who calls this?" / "What does this call?"
- "Where is this string/import referenced?"
- "Show call graph dependencies."
- "Find entities by name/pattern."

Route to:
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
Who calls each function. Use this instead of manual xref JOINs.

| Column | Type | Description |
|--------|------|-------------|
| `func_addr` | INT | Target function address |
| `caller_addr` | INT | Xref source address |
| `caller_name` | TEXT | Calling function name |
| `caller_func_addr` | INT | Calling function start |

```sql
-- Who calls function at 0x401000?
SELECT caller_name, printf('0x%X', caller_addr) as from_addr
FROM callers WHERE func_addr = 0x401000;

-- Most called functions
SELECT printf('0x%X', func_addr) as addr, COUNT(*) as callers
FROM callers GROUP BY func_addr ORDER BY callers DESC LIMIT 10;
```

### callees
What each function calls. Inverse of callers view.

| Column | Type | Description |
|--------|------|-------------|
| `func_addr` | INT | Calling function address |
| `func_name` | TEXT | Calling function name |
| `callee_addr` | INT | Called address |
| `callee_name` | TEXT | Called function/symbol name |

```sql
-- What does main call?
SELECT callee_name, printf('0x%X', callee_addr) as addr
FROM callees WHERE func_name LIKE '%main%';

-- Functions making most calls
SELECT func_name, COUNT(*) as call_count
FROM callees GROUP BY func_addr ORDER BY call_count DESC LIMIT 10;
```

---

## SQL Functions — Cross-References

| Function | Description |
|----------|-------------|
| `xrefs_to(addr)` | JSON array of xrefs TO address |
| `xrefs_from(addr)` | JSON array of xrefs FROM address |

---

## grep

Structured entity-search surface.
For canonical schema and owner mapping, see `../connect/references/schema-catalog.md` (`grep`).

| Surface | Description |
|---------|-------------|
| `grep` table | Structured rows for composable SQL search |
| `grep(pattern, limit, offset)` | JSON array for quick agent/tool output |

Searches functions, labels, segments, structs, unions, enums, members, and enum members.
Pattern rules:
- Plain text = case-insensitive contains (`pattern = 'main'`)
- `%` / `_` wildcards supported (`pattern = 'sub%'`)
- `*` is accepted and normalized to `%`

```sql
-- Structured table search: prefix
SELECT name, kind, address
FROM grep
WHERE pattern = 'sub%'
LIMIT 10;

-- Structured table search: contains
SELECT name, kind, full_name
FROM grep
WHERE pattern = 'main'
LIMIT 20;

-- JSON form with pagination
SELECT grep('sub%', 10, 0);
SELECT grep('sub%', 10, 10);

-- Parse JSON result from grep()
SELECT json_extract(value, '$.name') as name,
       printf('0x%llX', json_extract(value, '$.address')) as addr
FROM json_each(grep('init', 50, 0))
WHERE json_extract(value, '$.kind') = 'function';
```

### Entity Search Table (grep) — Full Reference

The `grep` virtual table is the primary structured entity-search surface.

#### Usage

```sql
-- Basic search
SELECT * FROM grep WHERE pattern = 'sub%' LIMIT 10;

-- Filter by kind
SELECT * FROM grep WHERE pattern = 'EH%' AND kind = 'struct';

-- JOIN with other tables
SELECT g.name, f.size
FROM grep g
LEFT JOIN funcs f ON g.address = f.address
WHERE g.pattern = 'sub%' AND g.kind = 'function';
```

#### Parameters

| Parameter | Description |
|-----------|-------------|
| `pattern` | Search pattern (required) |

#### Columns

| Column | Type | Description |
|--------|------|-------------|
| `name` | TEXT | Entity name |
| `kind` | TEXT | function/label/segment/struct/union/enum/member/enum_member |
| `address` | INT | Address (for functions, labels, segments) |
| `ordinal` | INT | Type ordinal (for types, members) |
| `parent_name` | TEXT | Parent type (for members) |
| `full_name` | TEXT | Fully qualified name |

For JSON output instead of rows, use `grep(pattern, limit, offset)`.

---

## Performance Rules

### Constraint Pushdown

The `xrefs` table has **optimized filters** using efficient IDA SDK APIs:

| Filter | Behavior |
|--------|----------|
| `to_ea = X` | O(xrefs to X) — fast, uses IDA's xref index |
| `from_ea = X` | O(xrefs from X) — fast, uses IDA's xref index |
| No filter | O(all xrefs in database) — **SLOW** |

**Always filter xrefs by `to_ea` or `from_ea`!**

```sql
-- FAST: xrefs to a specific target
SELECT * FROM xrefs WHERE to_ea = 0x401000;

-- FAST: xrefs from a specific source
SELECT * FROM xrefs WHERE from_ea = 0x401000;

-- SLOW: scanning all xrefs (avoid unless necessary)
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

### Recursive Call Graph — Forward Traversal

Find all functions reachable from a starting function (up to depth 5):

```sql
WITH RECURSIVE call_graph AS (
    -- Base case: start from main
    SELECT address as func_addr, name, 0 as depth
    FROM funcs WHERE name = 'main'

    UNION ALL

    -- Recursive case: follow calls
    SELECT f.address, f.name, cg.depth + 1
    FROM call_graph cg
    JOIN disasm_calls dc ON dc.func_addr = cg.func_addr
    JOIN funcs f ON f.address = dc.callee_addr
    WHERE cg.depth < 5
      AND dc.callee_addr != 0  -- Skip indirect calls
)
SELECT DISTINCT func_addr, name, MIN(depth) as min_depth
FROM call_graph
GROUP BY func_addr
ORDER BY min_depth, name;
```

### Recursive Call Graph — Reverse (Who Calls This?)

Trace callers transitively up to depth 5:

```sql
WITH RECURSIVE callers_cte AS (
    -- Base: direct callers of target
    SELECT DISTINCT dc.func_addr, 1 as depth
    FROM disasm_calls dc
    WHERE dc.callee_addr = 0x401000

    UNION ALL

    -- Recursive: who calls the callers
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

---
name: re-source
description: "Re-source IDA binaries. Use when asked for recursive annotation, structure recovery, type reconstruction, or bottom-up program understanding."
metadata:
  argument-hint: "[function-name or address]"
allowed-tools:
  - Bash
  - Read
  - Glob
  - Grep
---

For structure recovery patterns, see: `references/struct-recovery-patterns.md`

This skill teaches a **methodology** for recovering source-level understanding from compiled binaries using idasql. It orchestrates the other skills into a systematic workflow.

---

## Core Workflow: Recursive Re-Sourcing

### 1. Start at a Function

Pick a function — an entry point, a function referenced by an interesting string, or a callee of a known function.

```sql
-- Decompile the target function
SELECT decompile(0x401000);

-- Or by name
SELECT decompile('DriverEntry');
```

### 2. Annotate the Function

Use the `annotations` skill to edit the decompilation into something readable:

```sql
-- Rename local variables to meaningful names
SELECT rename_lvar(0x401000, 0, 'driver_object');
SELECT rename_lvar(0x401000, 1, 'registry_path');

-- Apply types to arguments/locals
UPDATE ctree_lvars SET type = 'PDRIVER_OBJECT'
WHERE func_addr = 0x401000 AND idx = 0;

-- Inspect pseudocode anchors before writing comments
SELECT line_num, ea, line, comment
FROM pseudocode
WHERE func_addr = 0x401000
ORDER BY line_num;

-- Add inline comments explaining logic
-- Example below uses a previously resolved writable anchor, not the function entry row.
UPDATE pseudocode SET comment = 'initialize dispatch table'
WHERE func_addr = 0x401000 AND ea = 0x401020;

-- Verify changes
SELECT decompile(0x401000, 1);
```

### 3. Set a Function Comment

Write a concise summary describing what the function does. This makes the function indexable for later queries.
For exact trigger semantics (`function summary` / `func-summary` / singular `add function comment`), follow the `annotations` skill's Function Summary contract.

```sql
SELECT address, name, comment, rpt_comment
FROM funcs
WHERE address = 0x401000;

UPDATE funcs
SET rpt_comment = 'DriverEntry: initializes driver dispatch routines and device object'
WHERE address = 0x401000;
```

### 4. Recurse into Callees

Follow calls inside the function. Annotate each callee the same way, building understanding bottom-up.

```sql
-- List callees to visit
SELECT callee_name, printf('0x%X', callee_addr) as addr
FROM disasm_calls WHERE func_addr = 0x401000;

-- Or map the full call subtree at once (BFS with depth tracking)
SELECT func_name, depth FROM call_graph
WHERE start = 0x401000 AND direction = 'down' AND max_depth = 5;

-- Decompile each callee
SELECT decompile(0x401050);

-- Annotate and recurse...
```

### 5. Recurse into Callers

Follow callers to build the bigger picture: how is this function used?

```sql
-- Who calls this function?
SELECT caller_name, printf('0x%X', caller_addr) as addr
FROM callers WHERE func_addr = 0x401000;

-- Or map ALL transitive callers at once
SELECT func_name, depth FROM call_graph
WHERE start = 0x401000 AND direction = 'up' AND max_depth = 10;

-- Find the shortest path from an entry point to this function
SELECT step, func_name FROM shortest_path
WHERE from_addr = (SELECT address FROM funcs WHERE name = 'main')
  AND to_addr = 0x401000 AND max_depth = 20;

-- Decompile callers to see usage context
SELECT decompile(0x400F00);
```

### 6. Structure Recovery

The hardest part. Decompiled code often shows casts like `*(DWORD *)(a1 + 0x10)` — these are structure field accesses.

#### Step-by-step Process

**a) Identify offset patterns in a single function:**
```sql
-- Look at the decompiled code for cast patterns
SELECT decompile(0x401000);

-- Query ctree for pointer arithmetic (field accesses)
SELECT ea, op_name, num_value
FROM ctree WHERE func_addr = 0x401000
  AND op_name IN ('cot_add', 'cot_idx')
  AND num_value IS NOT NULL;
```

**b) Cross-function correlation — find more fields:**
```sql
-- Find all callers that pass the same struct pointer
SELECT DISTINCT func_at(dc.func_addr) as caller
FROM disasm_calls dc
WHERE dc.callee_addr = 0x401000;

-- Decompile each caller and look for more offset accesses
-- Each caller may reveal different fields of the same struct
```

**c) Callee correlation — let callees reveal field types:**
```sql
-- What does the function call with the struct pointer?
SELECT COALESCE(call_obj_name, call_helper_name) AS callee_name,
       arg_idx, arg_op, arg_num_value
FROM ctree_call_args
WHERE func_addr = 0x401000
  AND arg_var_name = 'a1';
-- If callee expects HANDLE, the field at that offset is a HANDLE
```

**d) Build the struct incrementally:**
```sql
-- Create the struct
INSERT INTO types (name, kind) VALUES ('MY_CONTEXT', 'struct');

-- Get the ordinal
SELECT ordinal FROM types WHERE name = 'MY_CONTEXT';

-- Add fields as you discover them
INSERT INTO types_members (type_ordinal, member_name, member_type)
VALUES (42, 'handle', 'HANDLE');
INSERT INTO types_members (type_ordinal, member_name, member_type)
VALUES (42, 'buffer_ptr', 'void *');
INSERT INTO types_members (type_ordinal, member_name, member_type)
VALUES (42, 'buffer_size', 'unsigned int');
```

**e) Apply the recovered struct:**
```sql
-- Apply to function prototype
UPDATE funcs SET prototype = 'int __fastcall process_context(MY_CONTEXT *ctx);'
WHERE address = 0x401000;

-- Or apply to a local variable
UPDATE ctree_lvars SET type = 'MY_CONTEXT *'
WHERE func_addr = 0x401000 AND idx = 0;

-- Re-decompile to verify clean rendering
SELECT decompile(0x401000, 1);
```

### 7. Track Progress

Use `netnode_kv` to persist progress across sessions:

```sql
-- Mark a function as fully annotated
INSERT INTO netnode_kv(key, value)
VALUES('re_source:0x401000', '{"status":"done","summary":"DriverEntry init"}');

-- Check progress
SELECT key, value FROM netnode_kv WHERE key LIKE 're_source:%';
```

---

## Advanced Re-Sourcing Patterns (CTEs)

### Transitive caller discovery

Find all functions that transitively pass a struct through a chain of calls — who ultimately provides the data?

> **Prefer `call_graph` for simple traversal:** `SELECT func_name, depth FROM call_graph WHERE start = 0x401000 AND direction = 'up' AND max_depth = 5` replaces the CTE below. Use the CTE only when you need to JOIN caller context (e.g. offset accesses) at each step.

```sql
-- Recursive CTE: walk callers up to 5 levels
WITH RECURSIVE caller_chain AS (
    -- Base: direct callers of the struct-consuming function
    SELECT c.caller_func_addr AS func_addr,
           c.caller_name AS func_name,
           1 AS depth
    FROM callers c
    WHERE c.func_addr = 0x401000

    UNION ALL

    -- Recurse: callers of callers
    SELECT c.caller_func_addr,
           c.caller_name,
           cc.depth + 1
    FROM caller_chain cc
    JOIN callers c ON c.func_addr = cc.func_addr
    WHERE cc.depth < 5
)
SELECT DISTINCT func_name, printf('0x%X', func_addr) AS addr, MIN(depth) AS min_depth
FROM caller_chain
GROUP BY func_addr
ORDER BY min_depth;
```

### Aggregate offset accesses across all callers

Build a comprehensive struct field map by collecting offset patterns from every function that touches the struct:

```sql
-- Collect field offset accesses from all functions that call process_context
WITH callers_of AS (
    SELECT DISTINCT func_addr
    FROM disasm_calls
    WHERE callee_addr = 0x401000
),
offset_accesses AS (
    SELECT func_addr,
           func_at(func_addr) AS func_name,
           num_value AS field_offset,
           op_name
    FROM ctree
    WHERE func_addr IN (SELECT func_addr FROM callers_of)
      AND op_name IN ('cot_add', 'cot_idx')
      AND num_value IS NOT NULL
      AND num_value BETWEEN 0 AND 0x1000
)
SELECT field_offset,
       printf('0x%X', field_offset) AS hex_offset,
       COUNT(DISTINCT func_addr) AS seen_in_funcs,
       GROUP_CONCAT(DISTINCT func_name) AS functions
FROM offset_accesses
GROUP BY field_offset
ORDER BY field_offset;
```

### Find struct-heavy functions (candidates for structure recovery)

Functions with the most `cot_add` offset patterns are likely manipulating structs through raw pointer arithmetic:

```sql
-- Functions with most pointer arithmetic (struct field access candidates)
WITH offset_funcs AS (
    SELECT func_addr,
           COUNT(*) AS offset_accesses,
           COUNT(DISTINCT num_value) AS unique_offsets
    FROM ctree
    WHERE func_addr IN (SELECT address FROM funcs ORDER BY size DESC LIMIT 100)
      AND op_name = 'cot_add'
      AND num_value IS NOT NULL
      AND num_value BETWEEN 1 AND 0x1000
    GROUP BY func_addr
)
SELECT func_at(func_addr) AS name,
       printf('0x%X', func_addr) AS addr,
       offset_accesses,
       unique_offsets
FROM offset_funcs
ORDER BY unique_offsets DESC
LIMIT 15;
```

### Cross-reference struct field offsets with known type sizes

Match observed offsets against field sizes of existing types to guess field types:

```sql
-- Compare observed offsets with known struct sizes
WITH observed AS (
    SELECT DISTINCT num_value AS offset
    FROM ctree
    WHERE func_addr = 0x401000
      AND op_name = 'cot_add'
      AND num_value IS NOT NULL
      AND num_value BETWEEN 0 AND 0x200
),
candidate_types AS (
    SELECT t.name AS type_name, t.size AS type_size
    FROM types t
    WHERE t.is_struct = 1 AND t.size > 0
)
SELECT o.offset, printf('0x%X', o.offset) AS hex_offset,
       ct.type_name, ct.type_size
FROM observed o
LEFT JOIN candidate_types ct ON ct.type_size = o.offset
ORDER BY o.offset;
```

---

## Key Principles

1. **Bottom-up understanding**: Start with leaf callees, annotate them, then work up to callers. Each annotated callee makes the caller easier to understand.

2. **Cross-function struct correlation**: A single function rarely reveals the full struct layout. Look at multiple callers/callees of the same function to discover different fields.

3. **Iterative refinement**: Apply what you know, re-decompile, see if the output improves. Add more fields/types as you discover them.

4. **Verify every edit**: Follow the Mandatory Mutation Loop (read → edit → refresh → verify) from the `annotations` skill.

5. **Save periodically**: Use `SELECT save_database()` to persist your work.

---

## Related Skills

- **`annotations`** — The editing/annotation workflow: how to rename, retype, comment
- **`decompiler`** — Deep decompiler reference: ctree, types, parse_decls, union selection
- **`types`** — Type system mechanics: struct/union/enum creation and manipulation
- **`xrefs`** — Caller/callee traversal, `call_graph` / `shortest_path` tables, `string_refs` view
- **`disassembly`** — `cfg_edges` for control flow understanding during struct recovery
- **`storage`** — netnode_kv for tracking progress across sessions

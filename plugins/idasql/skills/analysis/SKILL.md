---
name: analysis
description: "Triage and audit IDA binaries. Use when asked to analyze a binary, find suspicious behavior, detect crypto/network activity, review decompiled code against source, or run multi-table queries."
metadata:
  argument-hint: "[binary-description or focus-area]"
allowed-tools:
  - Bash
  - Read
  - Glob
  - Grep
---

## Additional Resources

- For crypto/network detection patterns: [references/crypto-detection.md](references/crypto-detection.md), [references/network-detection.md](references/network-detection.md)
- For advanced SQL patterns (CTEs, window functions, batch analysis, pagination) and extended query cookbook: [references/analysis-cookbook.md](references/analysis-cookbook.md)

---

## Trigger Intents

Use this skill when user prompts sound like:
- "What does this binary do?"
- "Find suspicious/security-relevant behavior."
- "Which libraries/frameworks are present?"
- "Give me a prioritized triage plan."
- "Show higher-level insights, not just raw rows."
- "Compare this decompilation to source."
- "Help make this function review-ready."

Route to adjacent skills when needed:
- Need raw caller/callee detail: `xrefs`
- Need assembly-level investigation: `disassembly`
- Need pseudocode semantics: `decompiler`
- Need editing/annotation: `annotations`

---

## Do This First (Warm-Start Sequence)

Start broad, then narrow:

```sql
-- 1) Binary orientation
SELECT * FROM welcome;

-- 2) Capability hints from imports
SELECT module, name FROM imports ORDER BY module, name;

-- 3) Behavioral hints from strings
SELECT content, printf('0x%X', address) AS addr
FROM strings
WHERE length >= 8
ORDER BY length DESC
LIMIT 40;
```

Interpretation guidance:
- Crypto/network/process APIs + suspicious strings usually indicate highest-value functions to inspect first.
- Move from "signals" to "functions" via `xrefs`/`disasm_calls`, then decompile likely hotspots.

---

## Failure and Recovery

- Empty/high-noise results:
  - Tighten patterns and pivot to module-specific imports.
  - Add JOINs with `funcs` and limit by size/name or call density.
- Missing decompiler surfaces:
  - Continue with `disassembly` + `xrefs` patterns.
- Timeout on complex analytics:
  - Decompose into staged CTEs and smaller candidate sets.

---

## Handoff Patterns

1. `analysis` -> `xrefs`: map signal addresses to caller/callee graph.
2. `analysis` -> `decompiler`: inspect semantic logic in highest-risk functions.
3. `analysis` -> `annotations`: persist findings as comments/renames and make the decompilation review-ready.

---

## High-Fidelity Review Handoff

When the user wants side-by-side comparison with source, or asks to "clean up" a function so it reads better, stop treating the task as read-only triage and hand off to `annotations`.

Use this review probe first:

```sql
SELECT decompile(0x401000);
SELECT idx, name, type FROM ctree_lvars WHERE func_addr = 0x401000 ORDER BY idx;
SELECT callee_name FROM disasm_calls WHERE func_addr = 0x401000;
```

Then route to `annotations` for the edit pass. Success markers for a review-ready function are:
- typed signature and clearer field access
- named locals, globals, and labels
- one heading-style summary comment near function start
- less raw pointer math and fewer generic temp names

Treat that summary comment as part of the analysis product, not just presentation polish:
- it should support semantic search later
- it should help whole-program understanding when many functions have already been annotated

Non-goal:
- exact source syntax. Decompiler-stable forms such as `qmemcpy(...)` can still be acceptable if names, types, and comments are correct.

---

## Quick Start Examples

### "What does this binary do?"

```sql
-- Entry points
SELECT * FROM entries;

-- Imported APIs (hints at functionality)
SELECT module, name FROM imports ORDER BY module, name;

-- Interesting strings
SELECT content FROM strings WHERE length > 10 ORDER BY length DESC LIMIT 20;
```

### "Find security-relevant code"

```sql
-- Dangerous string functions
SELECT DISTINCT func_at(func_addr) FROM disasm_calls
WHERE callee_name IN ('strcpy', 'strcat', 'sprintf', 'gets');

-- Crypto-related
SELECT * FROM imports WHERE name LIKE '%Crypt%' OR name LIKE '%Hash%';

-- Network-related
SELECT * FROM imports WHERE name LIKE '%socket%' OR name LIKE '%connect%' OR name LIKE '%send%';
```

### "Understand a specific function"

```sql
-- Basic info
SELECT * FROM funcs WHERE address = 0x401000;

-- Full disassembly
SELECT disasm_func(0x401000);

-- Decompile (if Hex-Rays available)
SELECT decompile(0x401000);

-- Local variables
SELECT name, type, size FROM ctree_lvars WHERE func_addr = 0x401000;

-- What it calls
SELECT callee_name FROM disasm_calls WHERE func_addr = 0x401000;

-- What calls it
SELECT func_at(from_ea) FROM xrefs WHERE to_ea = 0x401000 AND is_code = 1;
```

### "Find all uses of a string"

```sql
SELECT s.content, func_at(x.from_ea) as function, printf('0x%X', x.from_ea) as location
FROM strings s
JOIN xrefs x ON s.address = x.to_ea
WHERE s.content LIKE '%config%';
```

---

## Natural Language Query Examples

### Function Signature Queries

**"Show me functions that return integers"**
```sql
SELECT name, return_type, arg_count FROM funcs
WHERE return_is_integral = 1 LIMIT 20;

-- Or via types_func_args (typedef-aware)
SELECT DISTINCT type_name FROM types_func_args
WHERE arg_index = -1 AND is_integral_resolved = 1;
```

**"Show me functions that take 4 string arguments"**
```sql
SELECT type_name, COUNT(*) as string_args
FROM types_func_args
WHERE arg_index >= 0
  AND is_ptr_resolved = 1
  AND base_type_resolved IN ('char', 'wchar_t', 'CHAR', 'WCHAR')
GROUP BY type_ordinal
HAVING string_args = 4;
```

**"Which functions return pointers?"**
```sql
SELECT name, return_type FROM funcs
WHERE return_is_ptr = 1 ORDER BY name LIMIT 20;
```

**"Find void functions with many arguments"**
```sql
SELECT name, arg_count FROM funcs
WHERE return_is_void = 1 AND arg_count >= 4
ORDER BY arg_count DESC;
```

**"What calling conventions are used?"**
```sql
SELECT calling_conv, COUNT(*) as count FROM funcs
WHERE calling_conv IS NOT NULL AND calling_conv != ''
GROUP BY calling_conv ORDER BY count DESC;
```

### Return Value Analysis

**"Which functions return 0?"**
```sql
SELECT DISTINCT f.name FROM funcs f
JOIN ctree_v_returns r ON r.func_addr = f.address
WHERE r.return_num = 0;
```

**"Find functions that return -1 (error pattern)"**
```sql
SELECT DISTINCT f.name FROM funcs f
JOIN ctree_v_returns r ON r.func_addr = f.address
WHERE r.return_num = -1;
```

**"Functions that return their input argument"**
```sql
SELECT DISTINCT f.name FROM funcs f
JOIN ctree_v_returns r ON r.func_addr = f.address
WHERE r.returns_arg = 1;
```

**"Functions that return the result of another call (wrappers)"**
```sql
SELECT DISTINCT f.name FROM funcs f
JOIN ctree_v_returns r ON r.func_addr = f.address
WHERE r.returns_call_result = 1;
```

**"Functions with multiple return statements"**
```sql
SELECT f.name, COUNT(*) as return_count
FROM funcs f
JOIN ctree_v_returns r ON r.func_addr = f.address
GROUP BY f.address
HAVING return_count > 1
ORDER BY return_count DESC LIMIT 20;
```

---

## Common Query Patterns

### Find Most Called Functions

```sql
SELECT f.name, COUNT(*) as callers
FROM funcs f
JOIN xrefs x ON f.address = x.to_ea
WHERE x.is_code = 1
GROUP BY f.address
ORDER BY callers DESC
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

### Function Complexity (by Block Count)

```sql
SELECT func_at(func_ea) as name, COUNT(*) as block_count
FROM blocks
GROUP BY func_ea
ORDER BY block_count DESC
LIMIT 10;
```

### Find Leaf Functions (No Outgoing Calls)

```sql
SELECT f.name, f.size
FROM funcs f
LEFT JOIN disasm_calls c ON c.func_addr = f.address
GROUP BY f.address
HAVING COUNT(c.ea) = 0
ORDER BY f.size DESC;
```

### Functions with Deep Call Chains

```sql
SELECT f.name, MAX(cc.depth) as max_depth
FROM disasm_v_call_chains cc
JOIN funcs f ON f.address = cc.root_func
GROUP BY cc.root_func
ORDER BY max_depth DESC
LIMIT 10;
```

For targeted traversal, prefer the `call_graph` table over `disasm_v_call_chains`:

```sql
-- Map all functions in a call subtree
SELECT func_name, depth FROM call_graph
WHERE start = 0x401000 AND direction = 'down' AND max_depth = 5;
```

### Trace Call Path to Target Function

```sql
-- Trace call path to an internal helper
SELECT step, func_name FROM shortest_path
WHERE from_addr = (SELECT address FROM funcs WHERE name = 'main')
  AND to_addr = (SELECT address FROM funcs WHERE name = 'copy_user_input')
  AND max_depth = 20;
```

Use `call_graph` + `disasm_calls` + `imports` when the destination is an imported
API. `shortest_path` endpoints must resolve to functions.

### Find All Strings Reachable from a Function

```sql
SELECT DISTINCT sr.string_value
FROM call_graph cg
JOIN string_refs sr ON sr.func_addr = cg.func_addr
WHERE cg.start = 0x401000 AND cg.direction = 'down' AND cg.max_depth = 3;
```

### Three-Way: Strings + Imports Reachable from a Function

```sql
-- Three-way: strings + imports reachable from a function
SELECT 'string' as kind, sr.string_value as detail, cg.func_name as via_func
FROM call_graph cg
JOIN string_refs sr ON sr.func_addr = cg.func_addr
WHERE cg.start = 0x401000 AND cg.direction = 'down' AND cg.max_depth = 5
  AND sr.string_value LIKE '%http%'
UNION ALL
SELECT 'import', i.name, cg.func_name
FROM call_graph cg
JOIN disasm_calls dc ON dc.func_addr = cg.func_addr
JOIN imports i ON dc.callee_addr = i.address
WHERE cg.start = 0x401000 AND cg.direction = 'down' AND cg.max_depth = 5
ORDER BY kind, detail;
```

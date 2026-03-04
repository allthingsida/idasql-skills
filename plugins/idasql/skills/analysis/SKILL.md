---
name: analysis
description: "Analyze IDA binaries: triage, security audit, crypto/network detection, multi-table queries."
---

For library/framework detection patterns, see reference files:
- `references/crypto-detection.md` — OpenSSL, CryptoAPI, AES/RSA patterns
- `references/network-detection.md` — curl, WinHTTP, socket, WSA patterns

---

## Trigger Intents

Use this skill when user prompts sound like:
- "What does this binary do?"
- "Find suspicious/security-relevant behavior."
- "Which libraries/frameworks are present?"
- "Give me a prioritized triage plan."
- "Show higher-level insights, not just raw rows."

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
3. `analysis` -> `annotations`: persist findings as comments/renames.

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

### Type Analysis

**"Find typedefs that hide pointers (like HANDLE)"**
```sql
SELECT DISTINCT type_name, arg_type, base_type_resolved
FROM types_func_args
WHERE is_ptr = 0 AND is_ptr_resolved = 1;
```

**"Functions with struct parameters"**
```sql
SELECT type_name, arg_name, arg_type FROM types_func_args
WHERE arg_index >= 0 AND is_struct = 1;
```

### Combined Queries

**"Integer-returning functions with 3+ args that return specific values"**
```sql
SELECT f.name, f.return_type, f.arg_count, r.return_num
FROM funcs f
JOIN ctree_v_returns r ON r.func_addr = f.address
WHERE f.return_is_integral = 1
  AND f.arg_count >= 3
  AND r.return_num IS NOT NULL
ORDER BY r.return_num;
```

**"Fastcall functions that return pointers"**
```sql
SELECT name, return_type, arg_count FROM funcs
WHERE calling_conv = 'fastcall' AND return_is_ptr = 1;
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

### Security: Dangerous Function Calls with Stack Buffers

```sql
SELECT f.name, c.callee_name, printf('0x%X', c.ea) as address
FROM funcs f
JOIN ctree_v_calls c ON c.func_addr = f.address
JOIN ctree_call_args a ON a.func_addr = c.func_addr AND a.call_item_id = c.item_id
WHERE c.callee_name IN ('strcpy', 'strcat', 'sprintf', 'gets', 'memcpy')
  AND a.arg_idx = 0 AND a.arg_var_is_stk = 1
ORDER BY f.name;
```

### Find Zero Comparisons (Potential Error Checks)

```sql
SELECT func_at(func_addr) as func, printf('0x%X', ea) as addr
FROM ctree_v_comparisons
WHERE op_name = 'cot_eq' AND rhs_op = 'cot_num' AND rhs_num = 0;
```

### Calls Inside Loops (Performance Hotspots)

```sql
SELECT f.name, l.callee_name, l.loop_op
FROM ctree_v_calls_in_loops l
JOIN funcs f ON f.address = l.func_addr
ORDER BY f.name;
```

### malloc with Constant Size

```sql
SELECT func_at(c.func_addr) as func, a.arg_num_value as size
FROM ctree_v_calls c
JOIN ctree_call_args a ON a.func_addr = c.func_addr AND a.call_item_id = c.item_id
WHERE c.callee_name LIKE '%malloc%'
  AND a.arg_idx = 0 AND a.arg_op = 'cot_num'
ORDER BY a.arg_num_value DESC;
```

### Largest Structures

```sql
SELECT name, size, alignment
FROM types
WHERE is_struct = 1 AND size > 0
ORDER BY size DESC
LIMIT 10;
```

### Instruction Profile for a Function

```sql
SELECT mnemonic, COUNT(*) as count
FROM instructions
WHERE func_addr = 0x401330
GROUP BY mnemonic
ORDER BY count DESC;
```

### Import Dependency Map

```sql
SELECT f.name as func_name, i.module, COUNT(*) as api_count
FROM funcs f
JOIN disasm_calls dc ON dc.func_addr = f.address
JOIN imports i ON dc.callee_addr = i.address
GROUP BY f.address, i.module
ORDER BY f.name, api_count DESC;
```

### Find Indirect Calls (Potential Virtual Functions/Callbacks)

```sql
SELECT f.name, COUNT(*) as indirect_calls
FROM funcs f
JOIN disasm_calls dc ON dc.func_addr = f.address
WHERE dc.callee_addr = 0
GROUP BY f.address
ORDER BY indirect_calls DESC
LIMIT 20;
```

### String Format Audit (printf-style Vulnerabilities)

```sql
SELECT f.name, c.callee_name, printf('0x%X', c.ea) as addr
FROM funcs f
JOIN ctree_v_calls c ON c.func_addr = f.address
JOIN ctree_call_args a ON a.func_addr = c.func_addr AND a.call_item_id = c.item_id
WHERE c.callee_name LIKE '%printf%'
  AND a.arg_idx = 0
  AND a.arg_op = 'cot_var';
```

### Memory Allocation Patterns

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

### Control Flow Anomalies

```sql
SELECT
    f.name,
    f.size,
    COUNT(DISTINCT b.start_ea) as blocks,
    f.size / COUNT(DISTINCT b.start_ea) as avg_block_size
FROM funcs f
JOIN blocks b ON b.func_ea = f.address
WHERE f.size > 100
GROUP BY f.address
HAVING COUNT(DISTINCT b.start_ea) > 10
   AND f.size / COUNT(DISTINCT b.start_ea) < 10
ORDER BY blocks DESC;
```

### Return Value Analysis

```sql
SELECT f.name, COUNT(*) as return_count
FROM funcs f
JOIN ctree ct ON ct.func_addr = f.address
WHERE ct.op_name = 'cit_return'
GROUP BY f.address
HAVING COUNT(*) > 3
ORDER BY return_count DESC;
```

### Function Signature Queries

```sql
-- Functions returning integers (includes BOOL, DWORD via resolved)
SELECT type_name FROM types_func_args
WHERE arg_index = -1 AND is_integral_resolved = 1;

-- Functions taking exactly 4 pointer arguments
SELECT type_name, COUNT(*) as ptr_args FROM types_func_args
WHERE arg_index >= 0 AND is_ptr = 1
GROUP BY type_ordinal HAVING ptr_args = 4;

-- Functions with string parameters (char*/wchar_t*)
SELECT DISTINCT type_name FROM types_func_args
WHERE arg_index >= 0 AND is_ptr = 1
  AND base_type_resolved IN ('char', 'wchar_t', 'CHAR', 'WCHAR');

-- Typedefs hiding pointers (HANDLE, HMODULE, etc.)
SELECT DISTINCT type_name, arg_type FROM types_func_args
WHERE is_ptr = 0 AND is_ptr_resolved = 1;

-- Functions returning void pointers
SELECT type_name FROM types_func_args
WHERE arg_index = -1 AND is_ptr_resolved = 1 AND is_void_resolved = 1;
```

### Loops with System Calls (Performance/Security Hotspots)

```sql
SELECT
    f.name as function,
    l.callee_name as api_called,
    l.loop_op as loop_type
FROM ctree_v_calls_in_loops l
JOIN funcs f ON f.address = l.func_addr
JOIN imports i ON l.callee_name = i.name
ORDER BY f.name;
```

### Type Usage Statistics

```sql
SELECT tm.type_name, COUNT(DISTINCT ct.func_addr) as func_count
FROM types_members tm
JOIN ctree ct ON ct.var_name = tm.member_name
GROUP BY tm.type_name
ORDER BY func_count DESC
LIMIT 20;
```

### Data Section Analysis

```sql
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

### Exception Handler Detection

```sql
SELECT
    f.name,
    COUNT(*) as chunk_count,
    SUM(fc.size) as total_size
FROM funcs f
JOIN fchunks fc ON fc.owner = f.address
GROUP BY f.address
HAVING COUNT(*) > 1
ORDER BY chunk_count DESC;
```

---

## Advanced SQL Patterns

### Common Table Expressions (CTEs)

CTEs make complex queries readable and allow recursive traversal.

#### Basic CTE for Filtering

```sql
-- Find functions that both call malloc AND check return value
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

#### CTE with Aggregation

```sql
-- Functions ranked by complexity (calls * blocks)
WITH call_counts AS (
    SELECT func_addr, COUNT(*) as call_cnt
    FROM disasm_calls
    GROUP BY func_addr
),
block_counts AS (
    SELECT func_ea as func_addr, COUNT(*) as block_cnt
    FROM blocks
    GROUP BY func_ea
)
SELECT f.name,
       COALESCE(c.call_cnt, 0) as calls,
       COALESCE(b.block_cnt, 0) as blocks,
       COALESCE(c.call_cnt, 0) * COALESCE(b.block_cnt, 0) as complexity
FROM funcs f
LEFT JOIN call_counts c ON f.address = c.func_addr
LEFT JOIN block_counts b ON f.address = b.func_addr
ORDER BY complexity DESC
LIMIT 10;
```

### Recursive CTEs (Call Graph Traversal)

```sql
-- Find all functions reachable from main (up to depth 5)
WITH RECURSIVE call_graph AS (
    SELECT address as func_addr, name, 0 as depth
    FROM funcs WHERE name = 'main'

    UNION ALL

    SELECT f.address, f.name, cg.depth + 1
    FROM call_graph cg
    JOIN disasm_calls dc ON dc.func_addr = cg.func_addr
    JOIN funcs f ON f.address = dc.callee_addr
    WHERE cg.depth < 5
      AND dc.callee_addr != 0
)
SELECT DISTINCT func_addr, name, MIN(depth) as min_depth
FROM call_graph
GROUP BY func_addr
ORDER BY min_depth, name;
```

```sql
-- Reverse call graph: who calls this function (transitive)
WITH RECURSIVE callers AS (
    SELECT DISTINCT dc.func_addr, 1 as depth
    FROM disasm_calls dc
    WHERE dc.callee_addr = 0x401000

    UNION ALL

    SELECT DISTINCT dc.func_addr, c.depth + 1
    FROM callers c
    JOIN disasm_calls dc ON dc.callee_addr = c.func_addr
    WHERE c.depth < 5
)
SELECT func_at(func_addr) as caller, MIN(depth) as distance
FROM callers
GROUP BY func_addr
ORDER BY distance, caller;
```

### Window Functions

```sql
-- Rank functions by size within each segment
SELECT
    segment_at(f.address) as seg,
    f.name,
    f.size,
    ROW_NUMBER() OVER (PARTITION BY segment_at(f.address) ORDER BY f.size DESC) as rank
FROM funcs f
WHERE f.size > 0;
```

```sql
-- Running total of function sizes
SELECT
    name,
    size,
    SUM(size) OVER (ORDER BY address) as cumulative_size
FROM funcs
ORDER BY address;
```

```sql
-- Find consecutive functions with similar sizes (possible duplicates)
SELECT
    name,
    size,
    LAG(name) OVER (ORDER BY size) as prev_name,
    LAG(size) OVER (ORDER BY size) as prev_size
FROM funcs
WHERE size > 100;
```

### Complex JOINs

#### Multi-Table Join (Functions with Context)

```sql
SELECT
    f.name,
    f.size,
    segment_at(f.address) as segment,
    (SELECT COUNT(*) FROM blocks WHERE func_ea = f.address) as block_count,
    (SELECT COUNT(*) FROM disasm_calls WHERE func_addr = f.address) as outgoing_calls,
    (SELECT COUNT(*) FROM xrefs WHERE to_ea = f.address AND is_code = 1) as incoming_calls,
    (SELECT COUNT(*) FROM ctree_lvars WHERE func_addr = f.address) as local_vars
FROM funcs f
ORDER BY f.size DESC
LIMIT 20;
```

#### Self-Join (Compare Functions)

```sql
SELECT
    f1.name as func1,
    f2.name as func2,
    f1.size
FROM funcs f1
JOIN funcs f2 ON f1.size = f2.size AND f1.address < f2.address
WHERE f1.size > 50
ORDER BY f1.size DESC;
```

### Subqueries

```sql
-- Functions that call more APIs than average
SELECT f.name, call_count
FROM (
    SELECT func_addr, COUNT(*) as call_count
    FROM disasm_calls dc
    JOIN imports i ON dc.callee_addr = i.address
    GROUP BY func_addr
) sub
JOIN funcs f ON f.address = sub.func_addr
WHERE call_count > (
    SELECT AVG(cnt) FROM (
        SELECT COUNT(*) as cnt
        FROM disasm_calls dc
        JOIN imports i ON dc.callee_addr = i.address
        GROUP BY func_addr
    )
)
ORDER BY call_count DESC;
```

### CASE Expressions

```sql
-- Categorize functions by complexity
SELECT
    name,
    size,
    CASE
        WHEN size < 50 THEN 'tiny'
        WHEN size < 200 THEN 'small'
        WHEN size < 1000 THEN 'medium'
        WHEN size < 5000 THEN 'large'
        ELSE 'huge'
    END as category
FROM funcs
ORDER BY size DESC;
```

```sql
-- Classify strings by content
SELECT
    content,
    CASE
        WHEN content LIKE '%error%' OR content LIKE '%fail%' THEN 'error'
        WHEN content LIKE '%password%' OR content LIKE '%key%' THEN 'sensitive'
        WHEN content LIKE '%http%' OR content LIKE '%://% ' THEN 'url'
        WHEN content LIKE '%.dll%' OR content LIKE '%.exe%' THEN 'file'
        ELSE 'other'
    END as category
FROM strings
WHERE length > 5;
```

### Batch Analysis with UNION ALL

```sql
-- Comprehensive security audit in one query
SELECT 'dangerous_func' as check_type, func_at(func_addr) as location, callee_name as detail
FROM disasm_calls
WHERE callee_name IN ('strcpy', 'strcat', 'sprintf', 'gets', 'scanf')

UNION ALL

SELECT 'crypto_usage', func_at(func_addr), callee_name
FROM disasm_calls
WHERE callee_name LIKE '%Crypt%' OR callee_name LIKE '%AES%' OR callee_name LIKE '%RSA%'

UNION ALL

SELECT 'network_call', func_at(func_addr), callee_name
FROM disasm_calls
WHERE callee_name IN ('socket', 'connect', 'send', 'recv', 'WSAStartup')

UNION ALL

SELECT 'registry_access', func_at(func_addr), callee_name
FROM disasm_calls
WHERE callee_name LIKE 'Reg%'

ORDER BY check_type, location;
```

### Efficient Pagination

```sql
SELECT * FROM (
    SELECT
        f.name,
        f.size,
        ROW_NUMBER() OVER (ORDER BY f.size DESC) as row_num
    FROM funcs f
)
WHERE row_num BETWEEN 101 AND 200;
```

### EXISTS for Efficient Filtering

```sql
-- Functions that have at least one string reference
SELECT f.name
FROM funcs f
WHERE EXISTS (
    SELECT 1 FROM xrefs x
    JOIN strings s ON x.to_ea = s.address
    WHERE x.from_ea BETWEEN f.address AND f.end_ea
);
```

```sql
-- Functions without any calls (leaf functions, EXISTS version)
SELECT f.name, f.size
FROM funcs f
WHERE NOT EXISTS (
    SELECT 1 FROM disasm_calls dc
    WHERE dc.func_addr = f.address
)
ORDER BY f.size DESC;
```

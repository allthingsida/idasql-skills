---
name: disassembly
description: "Query IDA disassembly: functions, segments, instructions, blocks, operands, graphs."
---

---

## Trigger Intents

Use this skill when user asks for:
- Function/segment/instruction inspection
- Call-site or control-flow analysis from disassembly
- Operand formatting and low-level code structure
- Raw byte/instruction-level evidence

Route to:
- `decompiler` for AST/pseudocode semantics
- `xrefs` for relationship-heavy caller/callee workflows
- `debugger` for patching/breakpoint actions

---

## Do This First (Warm-Start Sequence)

```sql
-- 1) Orientation
SELECT * FROM welcome;

-- 2) Segment map
SELECT name, printf('0x%X', start_ea) AS start_ea, printf('0x%X', end_ea) AS end_ea, perm
FROM segments
ORDER BY start_ea;

-- 3) Largest functions (triage anchors)
SELECT name, printf('0x%X', address) AS addr, size
FROM funcs
ORDER BY size DESC
LIMIT 20;
```

Interpretation guidance:
- Start from executable segments and largest/highly connected functions.
- Use `func_addr` constraints early when querying instruction-heavy surfaces.

---

## Failure and Recovery

- Slow queries on `instructions`/`heads`:
  - Add `WHERE func_addr = X` or tight EA ranges.
- Missing expected symbol names:
  - Pivot to address-based workflows and enrich via `names` updates later.
- Ambiguous control-flow behavior:
  - Cross-check with `disasm_calls` and then escalate to `decompiler`.

---

## Handoff Patterns

1. `disassembly` -> `xrefs` for relation expansion.
2. `disassembly` -> `decompiler` for semantic interpretation.
3. `disassembly` -> `debugger` for patch/breakpoint execution.

---

## Entity Tables

### funcs
All detected functions in the binary with prototype information.

| Column | Type | Description |
|--------|------|-------------|
| `address` | INT | Function start address |
| `name` | TEXT | Function name |
| `size` | INT | Function size in bytes |
| `end_ea` | INT | Function end address |
| `flags` | INT | Function flags |

**Prototype columns** (populated when type info available):

| Column | Type | Description |
|--------|------|-------------|
| `return_type` | TEXT | Return type string (e.g., "int", "void *") |
| `return_is_ptr` | INT | 1 if return type is pointer |
| `return_is_int` | INT | 1 if return type is exactly int |
| `return_is_integral` | INT | 1 if return type is int-like (int, long, DWORD, BOOL) |
| `return_is_void` | INT | 1 if return type is void |
| `arg_count` | INT | Number of function arguments |
| `calling_conv` | TEXT | Calling convention (cdecl, stdcall, fastcall, etc.) |

```sql
-- 10 largest functions
SELECT name, size FROM funcs ORDER BY size DESC LIMIT 10;

-- Functions starting with "sub_" (auto-named, not analyzed)
SELECT name, printf('0x%X', address) as addr FROM funcs WHERE name LIKE 'sub_%';

-- Functions returning integers with 3+ arguments
SELECT name, return_type, arg_count FROM funcs
WHERE return_is_integral = 1 AND arg_count >= 3;

-- Void functions (side effects, callbacks)
SELECT name, arg_count FROM funcs WHERE return_is_void = 1;

-- Pointer-returning functions (factories, allocators)
SELECT name, return_type FROM funcs WHERE return_is_ptr = 1;

-- Simple getter functions (no args, returns value)
SELECT name, return_type FROM funcs
WHERE arg_count = 0 AND return_is_void = 0;

-- Functions by calling convention
SELECT calling_conv, COUNT(*) as count FROM funcs
WHERE calling_conv IS NOT NULL AND calling_conv != ''
GROUP BY calling_conv ORDER BY count DESC;
```

**Write operations:**
```sql
-- Create a function
INSERT INTO funcs (address) VALUES (0x401000);

-- Rename a function
UPDATE funcs SET name = 'my_func' WHERE address = 0x401000;

-- Update function flags
UPDATE funcs SET flags = 0 WHERE address = 0x401000;

-- Delete a function
DELETE FROM funcs WHERE address = 0x401000;
```

### segments
Memory segments. Supports INSERT, UPDATE (`name`, `class`, `perm`), and DELETE.

| Column | Type | RW | Description |
|--------|------|----|-------------|
| `start_ea` | INT | R | Segment start |
| `end_ea` | INT | R | Segment end |
| `name` | TEXT | RW | Segment name (.text, .data, etc.) |
| `class` | TEXT | RW | Segment class (CODE, DATA) |
| `perm` | INT | RW | Permissions (R=4, W=2, X=1) |

```sql
-- Find executable segments
SELECT name, printf('0x%X', start_ea) as start FROM segments WHERE perm & 1 = 1;

-- Create a new data segment at the next aligned free range
WITH next_free AS (
    SELECT ((MAX(end_ea) + 0x2000 + 0xFFF) / 0x1000) * 0x1000 AS start_ea
    FROM segments
)
INSERT INTO segments (start_ea, end_ea, name, class, perm)
SELECT start_ea, start_ea + 0x300, 'tmp_seg_create_demo', 'DATA', 6
FROM next_free;

-- Rename a segment
UPDATE segments SET name = '.mytext' WHERE start_ea = 0x401000;

-- Change segment permissions to read+exec
UPDATE segments SET perm = 5 WHERE name = '.text';

-- Delete a segment
DELETE FROM segments WHERE name = '.rdata';

-- Delete demo segment created above
DELETE FROM segments WHERE name = 'tmp_seg_create_demo';
```

### names
All named locations (functions, labels, data). Supports INSERT, UPDATE, and DELETE.

| Column | Type | RW | Description |
|--------|------|----|-------------|
| `address` | INT | R | Address |
| `name` | TEXT | RW | Name |

```sql
-- Create/set a name
INSERT INTO names (address, name) VALUES (0x401000, 'my_symbol');

-- Rename
UPDATE names SET name = 'my_symbol_renamed' WHERE address = 0x401000;

-- Remove name at address
DELETE FROM names WHERE address = 0x401000;
```

### entries
Entry points (exports, program entry, tls callbacks, etc.).

| Column | Type | Description |
|--------|------|-------------|
| `ordinal` | INT | Export ordinal |
| `address` | INT | Entry address |
| `name` | TEXT | Entry name |

---

## Instruction Tables

### instructions

`instructions` is the disassembly table. For scalar disassembly text at a specific EA, use `disasm_at(ea[, context])`.
Use `disasm_func()` or `disasm_range()` when you explicitly need a function/range listing.
Decoded instructions support DELETE (converts instruction to unexplored bytes) and operand representation updates via `operand*_format_spec`.

`WHERE func_addr = X` is the fast path (function-item iterator). Without it, the table scans all code heads.
If `X` is not a valid function start/address in a function, the constrained iterator returns no rows.

| Column | Type | Description |
|--------|------|-------------|
| `address` | INT | Instruction address |
| `func_addr` | INT | Containing function |
| `itype` | INT | Instruction type (architecture-specific) |
| `mnemonic` | TEXT | Instruction mnemonic |
| `size` | INT | Instruction size |
| `operand0..operand7` | TEXT | Operand text (`0..7`) |
| `disasm` | TEXT | Full disassembly line |
| `operand0_class..operand7_class` | TEXT | Operand class: `reg`, `imm`, `displ`, `mem`, ... |
| `operand0_repr_kind..operand7_repr_kind` | TEXT | Current representation: `plain`, `enum`, `stroff` |
| `operand0_repr_type_name..operand7_repr_type_name` | TEXT | Enum name or stroff path (`Type/SubType`) |
| `operand0_repr_member_name..operand7_repr_member_name` | TEXT | Enum member expression when applicable |
| `operand0_repr_serial..operand7_repr_serial` | INT | Enum serial (duplicate-value enums) |
| `operand0_repr_delta..operand7_repr_delta` | INT | Stroff delta |
| `operand0_format_spec..operand7_format_spec` | TEXT (RW) | Apply/clear representation for a specific operand |

```sql
-- Instruction profile of a function (FAST)
SELECT mnemonic, COUNT(*) as count
FROM instructions WHERE func_addr = 0x401330
GROUP BY mnemonic ORDER BY count DESC;

-- Find all call instructions in a function
SELECT address, disasm FROM instructions
WHERE func_addr = 0x401000 AND mnemonic = 'call';

-- Delete an instruction (convert to unexplored bytes)
DELETE FROM instructions WHERE address = 0x401000;

-- Delete a range of instructions
DELETE FROM instructions
WHERE address >= 0x401000 AND address < 0x401100;

-- Delete all decoded instructions in one function
DELETE FROM instructions WHERE func_addr = 0x401000;

-- Recreate one instruction
SELECT make_code(0x401000);

-- Recreate instructions in a range [start, end)
SELECT make_code_range(0x401000, 0x401100);

-- Recreate instructions in one function range (via funcs bounds)
SELECT make_code_range(address, end_ea) FROM funcs WHERE address = 0x401000;

-- Apply enum representation to operand 1
UPDATE instructions
SET operand1_format_spec = 'enum:MY_ENUM'
WHERE address = 0x401020;

-- Apply struct-offset representation with optional delta
UPDATE instructions
SET operand0_format_spec = 'stroff:MY_STRUCT,delta=0'
WHERE address = 0x401030;

-- Clear representation back to plain
UPDATE instructions
SET operand1_format_spec = 'clear'
WHERE address = 0x401020;
```

**Performance:** `WHERE func_addr = X` uses O(function_size) iteration. Without this constraint, it scans the entire database - SLOW.

### disasm_calls
All call instructions with resolved targets.

| Column | Type | Description |
|--------|------|-------------|
| `func_addr` | INT | Function containing the call |
| `ea` | INT | Call instruction address |
| `callee_addr` | INT | Target address (0 if unknown) |
| `callee_name` | TEXT | Target name |

```sql
-- Functions that call malloc
SELECT DISTINCT func_at(func_addr) as caller
FROM disasm_calls WHERE callee_name LIKE '%malloc%';
```

---

## blocks
Basic blocks within functions. **Use `func_ea` constraint for performance.**

| Column | Type | Description |
|--------|------|-------------|
| `func_ea` | INT | Containing function |
| `start_ea` | INT | Block start |
| `end_ea` | INT | Block end |
| `size` | INT | Block size |

```sql
-- Blocks in a specific function (FAST - uses constraint pushdown)
SELECT * FROM blocks WHERE func_ea = 0x401000;

-- Functions with most basic blocks
SELECT func_at(func_ea) as name, COUNT(*) as blocks
FROM blocks GROUP BY func_ea ORDER BY blocks DESC LIMIT 10;
```
`WHERE func_ea = X` is the optimized path. Without it, `blocks` may scan all functions.

---

## Additional Tables

### fchunks
Function chunks (for functions with non-contiguous code, like exception handlers).

| Column | Type | Description |
|--------|------|-------------|
| `owner` | INT | Parent function address |
| `start_ea` | INT | Chunk start |
| `end_ea` | INT | Chunk end |
| `size` | INT | Chunk size |
| `flags` | INT | Chunk flags |
| `is_tail` | INT | 1=tail chunk (owned by another function) |

```sql
-- Functions with multiple chunks (complex control flow)
SELECT func_at(owner) as name, COUNT(*) as chunks
FROM fchunks GROUP BY owner HAVING chunks > 1;
```

### heads
All defined items (code/data heads) in the database.

| Column | Type | Description |
|--------|------|-------------|
| `address` | INT | Head address |
| `size` | INT | Item size |
| `flags` | INT | IDA flags |

**Performance:** This table can be very large. Always use address range filters.

### bytes
Byte-level read/write table for patching and physical-offset mapping.

| Column | Type | Description |
|--------|------|-------------|
| `ea` | INT | Address |
| `value` | INT | Current byte value (RW) |
| `original_value` | INT | Original byte before patch |
| `is_patched` | INT | 1 if byte differs from original |
| `fpos` | INT | Physical/input file offset (NULL when unmapped) |

```sql
-- Inspect EA + physical offset mapping
SELECT printf('0x%X', ea) AS ea, fpos, value
FROM bytes
WHERE ea BETWEEN 0x401000 AND 0x401020;

-- Join current bytes with patch inventory offsets
SELECT b.ea, b.fpos, p.original_value, p.patched_value
FROM bytes b
JOIN patched_bytes p ON p.ea = b.ea
WHERE b.fpos IS NOT NULL;
```

### disasm_loops
Detected loops in disassembly.

| Column | Type | Description |
|--------|------|-------------|
| `func_addr` | INT | Function address |
| `loop_start` | INT | Loop header address |
| `loop_end` | INT | Loop end address |

### Disassembly Views

Views for disassembly-level analysis (no Hex-Rays required):

| View | Description |
|------|-------------|
| `disasm_v_leaf_funcs` | Functions with no outgoing calls |
| `disasm_v_call_chains` | Call chain paths (recursive CTE) |
| `disasm_v_calls_in_loops` | Calls inside loop bodies |
| `disasm_v_funcs_with_loops` | Functions containing loops |

```sql
-- Find functions that don't call anything
SELECT * FROM disasm_v_leaf_funcs LIMIT 10;

-- Find hotspot calls (inside loops)
SELECT func_at(func_addr) as func, callee_name
FROM disasm_v_calls_in_loops;
```

### signatures
FLIRT signature matches.

| Column | Type | Description |
|--------|------|-------------|
| `address` | INT | Matched address |
| `name` | TEXT | Signature name |
| `library` | TEXT | Library name |

### hidden_ranges
Collapsed/hidden code regions in IDA.

| Column | Type | Description |
|--------|------|-------------|
| `start_ea` | INT | Range start |
| `end_ea` | INT | Range end |
| `description` | TEXT | Description |
| `visible` | INT | Visibility state |

### problems
IDA analysis problems and warnings.

| Column | Type | Description |
|--------|------|-------------|
| `address` | INT | Problem address |
| `type` | INT | Problem type code |
| `description` | TEXT | Problem description |

```sql
-- Find all analysis problems
SELECT printf('0x%X', address) as addr, description FROM problems;
```

### fixups
Relocation and fixup information.

| Column | Type | Description |
|--------|------|-------------|
| `address` | INT | Fixup address |
| `type` | INT | Fixup type |
| `target` | INT | Target address |

### mappings
Memory mappings for debugging.

| Column | Type | Description |
|--------|------|-------------|
| `from_ea` | INT | Mapped from |
| `to_ea` | INT | Mapped to |
| `size` | INT | Mapping size |

---

## Metadata Tables

### db_info
Database-level metadata.

| Column | Type | Description |
|--------|------|-------------|
| `key` | TEXT | Metadata key |
| `value` | TEXT | Metadata value |

```sql
-- Get database info
SELECT * FROM db_info;
```

### ida_info
IDA processor and analysis info.

| Column | Type | Description |
|--------|------|-------------|
| `key` | TEXT | Info key |
| `value` | TEXT | Info value |

```sql
-- Get processor type
SELECT value FROM ida_info WHERE key = 'procname';
```

---

## SQL Functions — Disassembly

| Function | Description |
|----------|-------------|
| `disasm_at(addr)` | Canonical listing line for containing head (works for code/data) |
| `disasm_at(addr, n)` | Canonical listing line with +/- `n` neighboring heads |
| `disasm(addr)` | Single disassembly line at address |
| `disasm(addr, n)` | Next N instructions from address (count-based, not boundary-aware) |
| `disasm_range(start, end)` | All disassembly lines in address range [start, end) |
| `disasm_func(addr)` | Full disassembly of function containing address |
| `make_code(addr)` | Create instruction at address (returns 1/0) |
| `make_code_range(start, end)` | Create instructions in range, returns created count |
| `mnemonic(addr)` | Instruction mnemonic only |
| `operand(addr, n)` | Operand text (n=0-5) |

### Disassembly Examples

```sql
-- Canonical single-EA disassembly (safe for code or data)
SELECT disasm_at(0x401000);

-- Canonical context window (+/- 2 heads)
SELECT disasm_at(0x401000, 2);

-- Fallback for older runtimes without disasm_at():
SELECT printf('%llx', address) || ': ' || disasm
FROM heads
WHERE address <= 0x401000 AND address + size > 0x401000
LIMIT 1;
-- Note: this fallback may decode some data heads as code; prefer disasm_at when available.

-- Full function disassembly (resolves boundaries via get_func)
SELECT disasm_func(address) FROM funcs WHERE name = '_main';

-- Disassemble a specific address range
SELECT disasm_range(address, end_ea) FROM funcs WHERE name = '_main';
SELECT disasm_range(0x401000, 0x401100);

-- Disassemble all functions in a segment
SELECT name, disasm_func(address) FROM funcs
WHERE address >= (SELECT start_ea FROM segments WHERE name = '.text')
  AND address <  (SELECT end_ea FROM segments WHERE name = '.text');

-- Force instruction decode from EA (useful for code-only workflows)
SELECT disasm(0x401000);

-- Sliding window: next 5 instructions from an address
SELECT disasm(0x401000, 5);

-- Structured analysis: filter instructions by mnemonic
SELECT address, disasm FROM instructions
WHERE func_addr = 0x401000 AND mnemonic = 'call';
```

---

## SQL Functions — Names & Functions

Address argument note: `addr`/`ea`/`func_addr` parameters accept integer EAs, numeric strings, and symbol names.

| Function | Description |
|----------|-------------|
| `name_at(addr)` | Name at address |
| `func_at(addr)` | Function name containing address |
| `func_start(addr)` | Start of containing function |
| `func_end(addr)` | End of containing function |
| `func_qty()` | Total function count |
| `func_at_index(n)` | Function address at index (O(1)) |

---

## SQL Functions — Navigation

| Function | Description |
|----------|-------------|
| `next_head(addr)` | Next defined item |
| `prev_head(addr)` | Previous defined item |
| `segment_at(addr)` | Segment name at address |
| `hex(val)` | Format as hex string |

---

## SQL Functions — Item Analysis

| Function | Description |
|----------|-------------|
| `item_type(addr)` | Item type flags at address |
| `item_size(addr)` | Item size at address |
| `is_code(addr)` | Returns 1 if address is code |
| `is_data(addr)` | Returns 1 if address is data |
| `flags_at(addr)` | Raw IDA flags at address |

---

## SQL Functions — Instruction Details

| Function | Description |
|----------|-------------|
| `itype(addr)` | Instruction type code (processor-specific) |
| `decode_insn(addr)` | Full instruction info as JSON |
| `operand_type(addr, n)` | Operand type code (o_void, o_reg, etc.) |
| `operand_value(addr, n)` | Operand value (register num, immediate, etc.) |

```sql
-- Get instruction type for filtering
SELECT address, itype(address) as itype, mnemonic(address)
FROM heads WHERE is_code(address) = 1 LIMIT 10;

-- Decode full instruction
SELECT decode_insn(0x401000);
```

---

## SQL Functions — File Generation

| Function | Description |
|----------|-------------|
| `gen_listing(path)` | Generate full-database listing output (LST) |

```sql
-- Whole database listing export
SELECT gen_listing('C:/tmp/full.lst');
```

---

## SQL Functions — Graph Generation

| Function | Description |
|----------|-------------|
| `gen_cfg_dot(addr)` | Generate CFG as DOT graph string |
| `gen_cfg_dot_file(addr, path)` | Write CFG DOT to file |
| `gen_schema_dot()` | Generate database schema as DOT |

```sql
-- Get CFG for a function as DOT format
SELECT gen_cfg_dot(0x401000);

-- Export schema visualization
SELECT gen_schema_dot();
```

---

## Common x86 Instruction Types

When filtering by `itype` (faster than string comparison):

| itype | Mnemonic | Description |
|-------|----------|-------------|
| 16 | call (near) | Direct call |
| 18 | call (indirect) | Indirect call |
| 122 | mov | Move data |
| 143 | push | Push to stack |
| 134 | pop | Pop from stack |
| 159 | retn | Return |
| 85 | jz | Jump if zero |
| 79 | jnz | Jump if not zero |
| 27 | cmp | Compare |
| 103 | nop | No operation |

---

## Performance Rules

Understanding table architecture helps you choose the right query strategy:

| Table | Architecture | Key Constraint | Notes |
|-------|-------------|----------------|-------|
| `funcs` | Index-Based | none needed | O(1) per row via `getn_func(i)` — always fast |
| `instructions` | Iterator | `func_addr` | Function-item iterator (fast) vs full code-head scan (slow) |
| `blocks` | Iterator | `func_ea` | Constraint pushdown: iterates blocks of one function |
| `disasm_calls` | Generator | `func_addr` | Lazy streaming, respects LIMIT |
| `heads` | Iterator | address range | Can be very large — always use address range filters |
| `segments` | Index-Based | none needed | Small table, always fast |
| `names` | Iterator | none needed | Iterates IDA's name list |

**Key rules:**
- `funcs` is always fast — no constraint needed. Use it freely for aggregation, sorting, filtering.
- `instructions` without `func_addr` scans every code head in the database — use `func_addr` for per-function queries.
- `blocks` without `func_ea` iterates all functions' flowcharts — always constrain.
- `disasm_calls` is a Generator table (streams lazily, never materializes everything) — safe with LIMIT, but `func_addr` constraint avoids scanning all functions.
- `heads` is the largest table in most databases. Always filter by address range or use a more specific table (`instructions`, `blocks`).

**Cost model:**
```
funcs (full scan)            → O(func_qty()), typically ~1000s, fast
instructions WHERE func_addr → O(function_size / avg_insn_size)
instructions (no constraint) → O(total_code_heads), potentially 100K+
blocks WHERE func_ea         → O(block_count_in_func), fast
disasm_calls WHERE func_addr → O(instructions_in_func), streaming
```

---

## Advanced Disassembly Patterns (CTEs)

CTE notes for predictable performance:
- Seed CTEs with constrained function sets (for example: `funcs ORDER BY size DESC LIMIT N`).
- Keep `func_addr`/`func_ea` constraints inside inner CTEs when touching `instructions`/`blocks`.
- For mutation workflows, run candidate CTEs first, then execute bounded `DELETE`/`make_code*` using those results.
- Avoid recursive/unbounded CTEs over unconstrained `instructions` on large IDBs.

### Instruction mnemonic frequency across functions (complexity fingerprinting)

Fingerprint functions by their instruction mix — useful for finding similar functions or detecting obfuscation:

```sql
-- Top 10 most "complex" functions by unique mnemonic count
WITH mnemonic_profile AS (
    SELECT func_addr,
           func_at(func_addr) AS func_name,
           COUNT(DISTINCT mnemonic) AS unique_mnemonics,
           COUNT(*) AS total_insns
    FROM instructions
    WHERE func_addr IN (SELECT address FROM funcs ORDER BY size DESC LIMIT 50)
    GROUP BY func_addr
)
SELECT func_name,
       printf('0x%X', func_addr) AS addr,
       unique_mnemonics,
       total_insns,
       ROUND(unique_mnemonics * 1.0 / total_insns, 3) AS diversity_ratio
FROM mnemonic_profile
ORDER BY unique_mnemonics DESC
LIMIT 10;
```

### Functions with the most unique callee APIs (dispatch/hub detection)

Hub functions that call many different APIs are often dispatchers, init routines, or main loops:

```sql
-- Functions calling the most distinct callees
WITH callee_counts AS (
    SELECT func_addr,
           func_at(func_addr) AS func_name,
           COUNT(DISTINCT callee_name) AS unique_callees
    FROM disasm_calls
    WHERE callee_name IS NOT NULL AND callee_name != ''
    GROUP BY func_addr
)
SELECT func_name,
       printf('0x%X', func_addr) AS addr,
       unique_callees
FROM callee_counts
ORDER BY unique_callees DESC
LIMIT 15;
```

### Function complexity score (blocks × instructions × calls)

A composite complexity metric combining structural and call complexity:

```sql
-- Composite complexity score
WITH block_counts AS (
    SELECT func_ea AS addr, COUNT(*) AS n_blocks
    FROM blocks GROUP BY func_ea
),
insn_counts AS (
    SELECT func_addr AS addr, COUNT(*) AS n_insns
    FROM instructions
    WHERE func_addr IN (SELECT address FROM funcs ORDER BY size DESC LIMIT 100)
    GROUP BY func_addr
),
call_counts AS (
    SELECT func_addr AS addr, COUNT(*) AS n_calls
    FROM disasm_calls GROUP BY func_addr
)
SELECT func_at(i.addr) AS name,
       printf('0x%X', i.addr) AS addr,
       COALESCE(b.n_blocks, 0) AS blocks,
       i.n_insns AS insns,
       COALESCE(c.n_calls, 0) AS calls,
       COALESCE(b.n_blocks, 1) * i.n_insns * (1 + COALESCE(c.n_calls, 0)) AS complexity
FROM insn_counts i
LEFT JOIN block_counts b ON b.addr = i.addr
LEFT JOIN call_counts c ON c.addr = i.addr
ORDER BY complexity DESC
LIMIT 15;
```

### Rank functions by instruction count per segment

Find the largest functions in each segment — useful for triage:

```sql
-- Top 3 largest functions per segment (by instruction count)
WITH ranked AS (
    SELECT segment_at(f.address) AS seg,
           f.name,
           f.size,
           ROW_NUMBER() OVER (PARTITION BY segment_at(f.address) ORDER BY f.size DESC) AS rank
    FROM funcs f
)
SELECT seg, name, size
FROM ranked
WHERE rank <= 3
ORDER BY seg, rank;
```

---

## In-Context Learning Playbooks

Use these prompt-to-SQL templates in agent sessions:

```sql
-- 1) Safe instruction lifecycle at one EA
SELECT address, disasm FROM instructions WHERE address = 0x401000;
DELETE FROM instructions WHERE address = 0x401000;
SELECT make_code(0x401000);
SELECT address, disasm FROM instructions WHERE address = 0x401000;

-- 2) Range lifecycle with verification
SELECT COUNT(*) FROM instructions WHERE address >= 0x401000 AND address < 0x401100;
DELETE FROM instructions WHERE address >= 0x401000 AND address < 0x401100;
SELECT make_code_range(0x401000, 0x401100);
SELECT COUNT(*) FROM instructions WHERE address >= 0x401000 AND address < 0x401100;

-- 3) Function-scoped lifecycle
SELECT COUNT(*) FROM instructions WHERE func_addr = 0x401000;
DELETE FROM instructions WHERE func_addr = 0x401000;
SELECT make_code_range(address, end_ea) FROM funcs WHERE address = 0x401000;
SELECT COUNT(*) FROM instructions WHERE func_addr = 0x401000;
```

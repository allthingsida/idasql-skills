---
name: disassembly
description: "Query IDA disassembly. Use when asked about functions, segments, instructions, blocks, operands, control flow, or raw code structure."
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
```

**Write operations:**
```sql
-- Create a function
INSERT INTO funcs (address) VALUES (0x401000);

-- Rename a function
UPDATE funcs SET name = 'my_func' WHERE address = 0x401000;

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

-- Rename a segment
UPDATE segments SET name = '.mytext' WHERE start_ea = 0x401000;
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
| `operand0_repr_type_name..operand7_repr_type_name` | TEXT | Enum name or stroff path |
| `operand0_format_spec..operand7_format_spec` | TEXT (RW) | Apply/clear representation for a specific operand |

```sql
-- Instruction profile of a function (FAST)
SELECT mnemonic, COUNT(*) as count
FROM instructions WHERE func_addr = 0x401330
GROUP BY mnemonic ORDER BY count DESC;

-- Find all call instructions in a function
SELECT address, disasm FROM instructions
WHERE func_addr = 0x401000 AND mnemonic = 'call';

-- Apply enum representation to operand 1
UPDATE instructions
SET operand1_format_spec = 'enum:MY_ENUM'
WHERE address = 0x401020;

-- Clear representation back to plain
UPDATE instructions
SET operand1_format_spec = 'clear'
WHERE address = 0x401020;
```

**Performance:** `WHERE func_addr = X` uses O(function_size) iteration. Without this constraint, it scans the entire database.

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

### cfg_edges

Control flow graph edges between basic blocks. **Always use `WHERE func_ea = X`** (filter_eq pushdown, O(blocks in function)).

| Column | Type | Description |
|--------|------|-------------|
| `func_ea` | INT | Containing function |
| `from_block` | INT | Source block address |
| `to_block` | INT | Target block address |
| `edge_type` | TEXT | `normal` (single-successor or fallback label), `true`/`false` (generic first/second arms for a two-way branch; labels follow successor order, not taken/fallthrough semantics) |

```sql
-- Get CFG structure
SELECT * FROM cfg_edges WHERE func_ea = 0x401000;

-- Find branch points (conditional blocks)
SELECT from_block, COUNT(*) as succ_count
FROM cfg_edges WHERE func_ea = 0x401000
GROUP BY from_block HAVING succ_count > 1;

-- Find merge points (blocks with multiple predecessors)
SELECT to_block, COUNT(*) as pred_count
FROM cfg_edges WHERE func_ea = 0x401000
GROUP BY to_block HAVING pred_count > 1;

-- Function complexity ranking: combine CFG, loops, and call metrics
SELECT f.name, f.size,
       (SELECT COUNT(*)
        FROM (
            SELECT ce.from_block
            FROM cfg_edges ce
            WHERE ce.func_ea = f.address
            GROUP BY ce.from_block
            HAVING COUNT(*) > 1
        ) branch_blocks) as branch_sites,
       (SELECT COUNT(*) FROM disasm_loops dl WHERE dl.func_addr = f.address) as loops,
       (SELECT COUNT(*) FROM disasm_calls dc WHERE dc.func_addr = f.address) as calls_made
FROM funcs f
WHERE f.size > 32
ORDER BY branch_sites DESC
LIMIT 20;
```

### function_chunks

Cached table with one row per function chunk. Aggregate by `func_addr` when you
need function-level span or density metrics.

| Column | Type | Description |
|--------|------|-------------|
| `func_addr` | INT | Function address |
| `chunk_start` | INT | Chunk start address |
| `chunk_end` | INT | Chunk end address |
| `block_count` | INT | Number of blocks in chunk |
| `total_size` | INT | Total size of chunk |

```sql
SELECT * FROM function_chunks WHERE func_addr = 0x401000;
```

---

## SQL Functions -- Disassembly

| Function | Description |
|----------|-------------|
| `disasm_at(addr)` | Canonical listing line for containing head (works for code/data) |
| `disasm_at(addr, n)` | Canonical listing line with +/- `n` neighboring heads |
| `disasm(addr)` | Single disassembly line at address |
| `disasm(addr, n)` | Next N instructions from address (count-based) |
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

-- Full function disassembly (resolves boundaries via get_func)
SELECT disasm_func(address) FROM funcs WHERE name = '_main';

-- Disassemble a specific address range
SELECT disasm_range(0x401000, 0x401100);

-- Sliding window: next 5 instructions from an address
SELECT disasm(0x401000, 5);
```

---

## SQL Functions -- Names & Functions

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

## SQL Functions -- Navigation

| Function | Description |
|----------|-------------|
| `next_head(addr)` | Next defined item |
| `prev_head(addr)` | Previous defined item |
| `segment_at(addr)` | Segment name at address |
| `hex(val)` | Format as hex string |

---

## SQL Functions -- Item Analysis

| Function | Description |
|----------|-------------|
| `item_type(addr)` | Item type flags at address |
| `item_size(addr)` | Item size at address |
| `is_code(addr)` | Returns 1 if address is code |
| `is_data(addr)` | Returns 1 if address is data |
| `flags_at(addr)` | Raw IDA flags at address |

---

## SQL Functions -- Instruction Details

| Function | Description |
|----------|-------------|
| `itype(addr)` | Instruction type code (processor-specific) |
| `decode_insn(addr)` | Full instruction info as JSON |
| `operand_type(addr, n)` | Operand type code (o_void, o_reg, etc.) |
| `operand_value(addr, n)` | Operand value (register num, immediate, etc.) |

---

## SQL Functions -- File Generation

| Function | Description |
|----------|-------------|
| `gen_listing(path)` | Generate full-database listing output (LST) |

---

## SQL Functions -- Graph Generation

| Function | Description |
|----------|-------------|
| `gen_cfg_dot(addr)` | Generate CFG as DOT graph string |
| `gen_cfg_dot_file(addr, path)` | Write CFG DOT to file |
| `gen_schema_dot()` | Generate database schema as DOT |

```sql
-- Get CFG for a function as DOT format
SELECT gen_cfg_dot(0x401000);
```

---

## Performance Rules

| Table | Architecture | Key Constraint | Notes |
|-------|-------------|----------------|-------|
| `funcs` | Index-Based | none needed | O(1) per row via `getn_func(i)` -- always fast |
| `instructions` | Iterator | `func_addr` | Function-item iterator (fast) vs full code-head scan (slow) |
| `blocks` | Iterator | `func_ea` | Constraint pushdown: iterates blocks of one function |
| `cfg_edges` | Iterator | `func_ea` | filter_eq pushdown: O(blocks in function) |
| `disasm_calls` | Generator | `func_addr` | Lazy streaming, respects LIMIT |
| `heads` | Iterator | address range | Can be very large -- always use address range filters |
| `segments` | Index-Based | none needed | Small table, always fast |
| `names` | Iterator | none needed | Iterates IDA's name list |

**Key rules:**
- `funcs` is always fast -- no constraint needed.
- `instructions` without `func_addr` scans every code head -- use `func_addr` for per-function queries.
- `blocks` without `func_ea` iterates all functions' flowcharts -- always constrain.
- `heads` is the largest table in most databases. Always filter by address range.

**Cost model:**
```
funcs (full scan)            -> O(func_qty()), typically ~1000s, fast
instructions WHERE func_addr -> O(function_size / avg_insn_size)
instructions (no constraint) -> O(total_code_heads), potentially 100K+
blocks WHERE func_ea         -> O(block_count_in_func), fast
cfg_edges WHERE func_ea      -> O(block_count_in_func), fast
disasm_calls WHERE func_addr -> O(instructions_in_func), streaming
```

---

## Additional Resources

- For advanced CTE patterns and instruction lifecycle playbooks: [references/disassembly-examples.md](references/disassembly-examples.md)
- For additional table schemas (fchunks, heads, bytes, signatures, problems, fixups, etc.): [references/disassembly-tables.md](references/disassembly-tables.md)

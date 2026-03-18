# Disassembly Tables Reference

## fchunks

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

## heads

All defined items (code/data heads) in the database.

| Column | Type | Description |
|--------|------|-------------|
| `address` | INT | Head address |
| `size` | INT | Item size |
| `flags` | INT | IDA flags |

**Performance:** This table can be very large. Always use address range filters.

## bytes

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

## disasm_loops

Detected loops in disassembly.

| Column | Type | Description |
|--------|------|-------------|
| `func_addr` | INT | Function address |
| `loop_start` | INT | Loop header address |
| `loop_end` | INT | Loop end address |

## Disassembly Views

Views for disassembly-level analysis (no Hex-Rays required):

| View | Description |
|------|-------------|
| `disasm_v_leaf_funcs` | Functions with no outgoing calls |
| `disasm_v_call_chains` | Call chain paths (recursive CTE). For targeted traversal, prefer `call_graph` table: `SELECT * FROM call_graph WHERE start=X AND direction='down' AND max_depth=10` |
| `disasm_v_calls_in_loops` | Calls inside loop bodies |
| `disasm_v_funcs_with_loops` | Functions containing loops |

```sql
-- Find functions that don't call anything
SELECT * FROM disasm_v_leaf_funcs LIMIT 10;

-- Find hotspot calls (inside loops)
SELECT func_at(func_addr) as func, callee_name
FROM disasm_v_calls_in_loops;
```

## signatures

FLIRT signature matches.

| Column | Type | Description |
|--------|------|-------------|
| `address` | INT | Matched address |
| `name` | TEXT | Signature name |
| `library` | TEXT | Library name |

## hidden_ranges

Collapsed/hidden code regions in IDA.

| Column | Type | Description |
|--------|------|-------------|
| `start_ea` | INT | Range start |
| `end_ea` | INT | Range end |
| `description` | TEXT | Description |
| `visible` | INT | Visibility state |

## problems

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

## fixups

Relocation and fixup information.

| Column | Type | Description |
|--------|------|-------------|
| `address` | INT | Fixup address |
| `type` | INT | Fixup type |
| `target` | INT | Target address |

## mappings

Memory mappings for debugging.

| Column | Type | Description |
|--------|------|-------------|
| `from_ea` | INT | Mapped from |
| `to_ea` | INT | Mapped to |
| `size` | INT | Mapping size |

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

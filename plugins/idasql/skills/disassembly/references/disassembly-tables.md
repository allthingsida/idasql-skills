# Disassembly Tables Reference

## fchunks

Function chunks (for functions with non-contiguous code, like exception handlers).

| Column | Type | Description |
|--------|------|-------------|
| `owner` | INT | Parent function address |
| `start_addr` | INT | Chunk start |
| `end_addr` | INT | Chunk end |
| `size` | INT | Chunk size |
| `flags` | INT | Chunk flags |
| `is_tail` | INT | 1=tail chunk (owned by another function) |

```sql
-- Functions with multiple chunks (complex control flow)
SELECT (SELECT name FROM funcs WHERE owner >= addr AND owner < end_addr LIMIT 1) as name, COUNT(*) as chunks
FROM fchunks GROUP BY owner HAVING chunks > 1;
```

## heads

All defined items (code/data heads) in the database.

| Column | Type | Description |
|--------|------|-------------|
| `addr` | INT | Head address |
| `size` | INT | Item size |
| `type` | TEXT | Item type (`code`, `data`, `string`, etc.) |
| `flags` | INT | IDA flags |

**Performance:** `WHERE addr = X` and address range filters are optimized. Next/previous navigation should use `ORDER BY addr [DESC] LIMIT 1`; broad scans can still be large.

## bytes

Pure mapped-byte read/write table for patching and physical-offset mapping.
Use `heads` for IDA item size/type metadata; `bytes` includes item-tail bytes.

| Column | Type | Description |
|--------|------|-------------|
| `addr` | INT | Address |
| `value` | INT | Current byte value (RW; UPDATE patches 1 byte) |
| `word` | INT | 2-byte little-endian value (RW; UPDATE patches 2 bytes) |
| `dword` | INT | 4-byte little-endian value (RW; UPDATE patches 4 bytes) |
| `qword` | INT | 8-byte little-endian value (RW; UPDATE patches 8 bytes) |
| `original_value` | INT | Original byte before patch |
| `is_patched` | INT | 1 if byte differs from original (`WHERE is_patched = 1` enumerates patches fast) |
| `fpos` | INT | Physical/input file offset (NULL when unmapped) |

Revert a patch with `DELETE FROM bytes WHERE addr = ...` (or `WHERE is_patched = 1`).

```sql
-- Inspect EA + physical offset mapping over a tight byte range
SELECT printf('0x%X', addr) AS addr, fpos, value
FROM bytes
WHERE addr >= 0x401000 AND addr < 0x401020
ORDER BY addr;

-- Add item metadata when the byte is also an item head
SELECT b.addr, b.value, h.size, h.type
FROM bytes b
LEFT JOIN heads h ON h.addr = b.addr
WHERE b.addr >= 0x401000 AND b.addr < 0x401020
ORDER BY b.addr;

-- Patch inventory with file offsets (is_patched enumerates patches fast)
SELECT addr, fpos, original_value, value AS patched_value
FROM bytes
WHERE is_patched = 1 AND fpos IS NOT NULL;
```

## disasm_loops

Detected loops in disassembly.

| Column | Type | Description |
|--------|------|-------------|
| `func_addr` | INT | Function address |
| `loop_id` | INT | Loop index within the function |
| `header_addr` | INT | Loop header block start address |
| `header_end_addr` | INT | Loop header block end address |
| `back_edge_block_addr` | INT | Back-edge source block start address |
| `back_edge_block_end` | INT | Back-edge source block end address |

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
SELECT (SELECT name FROM funcs WHERE func_addr >= addr AND func_addr < end_addr LIMIT 1) as func, callee_name
FROM disasm_v_calls_in_loops;
```

## signatures

FLIRT signature matches.

| Column | Type | Description |
|--------|------|-------------|
| `index` | INT | Signature slot index |
| `name` | TEXT | Signature name |
| `optlibs` | TEXT | Optional libraries string |
| `state` | INT | Signature state (application status) |

## hidden_ranges

Collapsed/hidden code regions in IDA.

| Column | Type | Description |
|--------|------|-------------|
| `start_addr` | INT | Range start |
| `end_addr` | INT | Range end |
| `description` | TEXT | Description |
| `visible` | INT | Visibility state |

## problems

IDA analysis problems and warnings.

| Column | Type | Description |
|--------|------|-------------|
| `addr` | INT | Problem address |
| `type_id` | INT | Problem type code (numeric) |
| `type` | TEXT | Problem type name |
| `description` | TEXT | Problem description |

```sql
-- Find all analysis problems
SELECT printf('0x%X', addr) as addr, description FROM problems;
```

## fixups

Relocation and fixup information.

| Column | Type | Description |
|--------|------|-------------|
| `addr` | INT | Fixup address |
| `type` | INT | Fixup type |
| `target` | INT | Target address |

## mappings

Memory mappings for debugging.

| Column | Type | Description |
|--------|------|-------------|
| `from_addr` | INT | Mapped from |
| `to_addr` | INT | Mapped to |
| `size` | INT | Mapping size |

## Metadata Tables

### db_info

Database-level metadata as `key`/`value`/`type` rows (e.g. `processor`, `filetype`, `min_addr`, `max_addr`, `sdk_version`).

| Column | Type | Description |
|--------|------|-------------|
| `key` | TEXT | Metadata key |
| `value` | TEXT | Metadata value |
| `type` | TEXT | Value type hint (`string`, `int`, `hex`, `bool`) |

```sql
-- Get database info
SELECT * FROM db_info;

-- Get the processor name
SELECT value FROM db_info WHERE key = 'processor';
```

### ida_info

IDA analysis-flag info as `key`/`value`/`type` rows (e.g. `show_auto`, `show_void`, `is_dll`, `wide_hbf`, `demnames`). For the processor name use `db_info` key `processor`.

| Column | Type | Description |
|--------|------|-------------|
| `key` | TEXT | Info key |
| `value` | TEXT | Info value |
| `type` | TEXT | Value type hint (`bool`, `int`) |

```sql
-- Get all analysis-flag info
SELECT * FROM ida_info;
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

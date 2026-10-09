# Disassembly Tables Reference

## fchunks

IDA's raw chunk list (for functions with non-contiguous code, like exception
handlers): **one row per chunk**. A tail chunk shared by several functions appears
once, under its **primary** owner only, so grouping by `owner` undercounts the other
owners' chunks. For complete per-function ownership use `function_chunks` (one row per
owner, fast `WHERE func_addr = X`), `funcs.chunk_count`, or `func_at(addr)`; see the
`disassembly` skill.

| Column | Type | Description |
|--------|------|-------------|
| `owner` | INT | Primary owning function address |
| `start_addr` | INT | Chunk start |
| `end_addr` | INT | Chunk end |
| `size` | INT | Chunk size |
| `flags` | INT | Chunk flags (64-bit IDA function flags) |
| `is_tail` | INT | 1 = tail chunk, 0 = a function's entry chunk |

```sql
-- Functions with multiple chunks (complex control flow), every owner counted
SELECT name, chunk_count AS chunks
FROM funcs
WHERE chunk_count > 1
ORDER BY chunk_count DESC;

-- Raw tail chunks with their primary owner
SELECT printf('0x%X', start_addr) AS tail, size, (SELECT name FROM funcs WHERE addr = owner) AS primary_owner
FROM fchunks
WHERE is_tail = 1;
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
| `value` | INT | Current byte value, **NULL for a mapped-but-uninitialized byte** (e.g. BSS) (RW; UPDATE patches 1 byte) |
| `word` | INT | 2-byte little-endian value (RW; UPDATE patches 2 bytes) |
| `dword` | INT | 4-byte little-endian value (RW; UPDATE patches 4 bytes) |
| `qword` | INT | 8-byte little-endian value (RW; UPDATE patches 8 bytes) |
| `original_value` | INT | Original byte before patch |
| `is_patched` | INT | 1 if byte differs from original (`WHERE is_patched = 1` enumerates patches fast) |
| `is_initialized` | INT | 1 if the byte is loaded from the image, 0 for mapped-but-uninitialized (e.g. BSS) |
| `fpos` | INT | Physical/input file offset (NULL when unmapped) |

`value` preserves the "unknown" vs "real 0" distinction: it is SQL NULL wherever
`is_initialized = 0`. Writing such a byte initializes it, and `DELETE` returns it
to the uninitialized (NULL) state. Add `AND is_initialized = 1` when a read must
yield concrete bytes only — `blob_concat(value)` **skips** NULL rows, so a bulk
read spanning BSS silently returns fewer bytes than requested.

Revert a patch with `DELETE FROM bytes WHERE addr = ...` (or `WHERE is_patched = 1`).

```sql
-- Inspect EA + physical offset mapping over a tight byte range
SELECT printf('0x%X', addr) AS addr, fpos, value
FROM bytes
WHERE addr >= 0x401000 AND addr < 0x401020
ORDER BY bytes.addr;

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

Natural loops in disassembly: one row per back edge whose header dominates its latch
(the same loops as the `loops` table; address order plays no part). Filter by a function's
exact entry `func_addr`.

| Column | Type | Description |
|--------|------|-------------|
| `func_addr` | INT | Function address |
| `loop_id` | INT | The header's block index within the function |
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
| `disasm_v_calls_in_loops` | Calls between a loop's header and its latch (an address range: for a loop spanning chunks it is approximate) |
| `disasm_v_funcs_with_loops` | Functions containing loops |
| `func_summary` | One row per function: size, chunks, blocks, CFG edges, cyclomatic complexity, call sites out / callees, call sites in / callers, loops, switches, data reads / writes, frame size, `uses_chkstk` (owned by the `analysis` skill) |

```sql
-- Find functions that don't call anything
SELECT * FROM disasm_v_leaf_funcs LIMIT 10;

-- Find hotspot calls (inside loops)
SELECT (SELECT name FROM funcs WHERE addr = func_addr) as func, callee_name
FROM disasm_v_calls_in_loops;
```

## signatures

The database's FLIRT signature list (writable: INSERT applies, DELETE removes a planned
entry). Semantics, refusals and examples: `SKILL.md`, "signatures (FLIRT)".

| Column | Type | Description |
|--------|------|-------------|
| `idx` | INT | Position in IDA's list (shifts after a DELETE) |
| `name` | TEXT | Short name or absolute `.sig` path, as IDA stores it |
| `title` | TEXT | The library's name; NULL when the file is gone |
| `state` | TEXT | `applied`, `current` or `planned` |
| `matches` | INT | Library functions the signature recognized |
| `optlibs` | TEXT | Optional libraries string |

## available_signatures

The `.sig` files IDA would find for this processor (IDAUSR, `$IDASGN`, IDA's own folder;
the first of a name wins).

| Column | Type | Description |
|--------|------|-------------|
| `name` | TEXT | File name without `.sig` (what INSERT takes) |
| `title` | TEXT | The library's name |
| `path` | TEXT | Full path |
| `source` | TEXT | `idausr`, `idasgn` or `idadir` |
| `is_startup` | INT | 1 for a startup signature |
| `modules` | INT | Library modules in the file |
| `in_list` | INT | 1 when already in `signatures` |

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

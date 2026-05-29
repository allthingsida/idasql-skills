---
name: debugger
description: "IDA debugger operations. Use when asked to set breakpoints, patch bytes, add conditions, or manage a patch inventory."
allowed-tools:
  - Bash
  - Read
  - Glob
  - Grep
---

---

## Trigger Intents

Use this skill when user asks to:
- add/remove/modify breakpoints
- patch bytes or revert patches
- create patch inventories and debugging action plans
- instrument analysis-driven break/watch workflows

Route to:
- `analysis`/`xrefs` for selecting meaningful targets first
- `disassembly` for opcode-level patch context
- `annotations` for documenting patch rationale and outcomes

---

## Do This First (Warm-Start Sequence)

```sql
-- 1) Current breakpoint inventory
SELECT printf('0x%X', address) AS addr, type_name, enabled
FROM breakpoints
ORDER BY address;

-- 2) Current patch inventory (fast: backed by IDA's patch list)
SELECT printf('0x%X', ea) AS ea, original_value, value AS patched_value
FROM bytes WHERE is_patched = 1
ORDER BY ea
LIMIT 50;

-- 3) Validate target bytes before patch
SELECT ea, value, original_value, is_patched
FROM bytes
WHERE ea = 0x401000;
```

Interpretation guidance:
- Confirm existing instrumentation before adding more.
- Always snapshot current/original byte state before mutating.

---

## Failure and Recovery

- Breakpoint insert/update failed:
  - Validate address existence and hardware size/type compatibility.
- Patch verification mismatch:
  - Re-read `bytes` (and `WHERE is_patched = 1`), then retry with precise address.
- Unintended patch side effects:
  - Revert with `DELETE FROM bytes WHERE ea = ...` and reassess target instruction context.

---

## Handoff Patterns

1. `debugger` -> `disassembly` to validate instruction semantics around patch site.
2. `debugger` -> `xrefs` to assess blast radius of patched/broken call paths.
3. `debugger` -> `annotations` to leave durable analyst breadcrumbs.

---

## breakpoints

Debugger breakpoints. Supports full CRUD (SELECT, INSERT, UPDATE, DELETE). Breakpoints persist in the IDB even without an active debugger session.

| Column | Type | RW | Description |
|--------|------|----|-------------|
| `address` | INT | R | Breakpoint address |
| `enabled` | INT | RW | 1=enabled, 0=disabled |
| `type` | INT | RW | Breakpoint type (0=software, 1=hw_write, 2=hw_read, 3=hw_rdwr, 4=hw_exec) |
| `type_name` | TEXT | R | Type name (software, hardware_write, etc.) |
| `size` | INT | RW | Breakpoint size (for hardware breakpoints) |
| `flags` | INT | RW | Breakpoint flags |
| `pass_count` | INT | RW | Pass count before trigger |
| `condition` | TEXT | RW | Condition expression |
| `loc_type` | INT | R | Location type code |
| `loc_type_name` | TEXT | R | Location type (absolute, relative, symbolic, source) |
| `module` | TEXT | R | Module path (relative breakpoints) |
| `symbol` | TEXT | R | Symbol name (symbolic breakpoints) |
| `offset` | INT | R | Offset (relative/symbolic) |
| `source_file` | TEXT | R | Source file (source breakpoints) |
| `source_line` | INT | R | Source line number |
| `is_hardware` | INT | R | 1=hardware breakpoint |
| `is_active` | INT | R | 1=currently active |
| `group` | TEXT | RW | Breakpoint group name |
| `bptid` | INT | R | Breakpoint ID |

```sql
-- List all breakpoints
SELECT printf('0x%08X', address) as addr, type_name, enabled, condition
FROM breakpoints;

-- Add software breakpoint
INSERT INTO breakpoints (address) VALUES (0x401000);

-- Add hardware write watchpoint
INSERT INTO breakpoints (address, type, size) VALUES (0x402000, 1, 4);

-- Add conditional breakpoint
INSERT INTO breakpoints (address, condition) VALUES (0x401000, 'eax == 0');

-- Disable a breakpoint
UPDATE breakpoints SET enabled = 0 WHERE address = 0x401000;

-- Delete a breakpoint
DELETE FROM breakpoints WHERE address = 0x401000;

-- Find which functions have breakpoints
SELECT b.address, f.name, b.type_name, b.enabled
FROM breakpoints b
JOIN funcs f ON b.address >= f.address AND b.address < f.end_ea;
```

---

## bytes (Byte Patching)

Pure mapped-byte program view with patch support. This table is one row per
mapped byte address; IDA item metadata such as size/type belongs to `heads`.

| Column | Type | RW | Description |
|--------|------|----|-------------|
| `ea` | INT | R | Byte address |
| `value` | INT | RW | Current byte value (UPDATE patches 1 byte) |
| `word` | INT | RW | 2-byte little-endian value (UPDATE patches 2 bytes) |
| `dword` | INT | RW | 4-byte little-endian value (UPDATE patches 4 bytes) |
| `qword` | INT | RW | 8-byte little-endian value (UPDATE patches 8 bytes) |
| `original_value` | INT | R | Original byte value before patch |
| `is_patched` | INT | R | 1 if byte differs from original (`WHERE is_patched = 1` enumerates patches fast) |
| `fpos` | INT | R | Physical/input file offset (NULL when unavailable) |

Revert a patch with `DELETE FROM bytes WHERE ea = ...` (or `WHERE is_patched = 1`).

```sql
-- Read one address
SELECT ea, value, original_value, is_patched
FROM bytes WHERE ea = 0x401000;

-- Read a byte range, including item-tail bytes
SELECT ea, value
FROM bytes
WHERE ea >= 0x401000 AND ea < 0x401010
ORDER BY ea;

-- Get item metadata separately
SELECT address, size, type, flags, disasm
FROM heads
WHERE address = 0x401000;

-- Patch via table update (single byte, or width columns word/dword/qword)
UPDATE bytes SET value = 0x90 WHERE ea = 0x401000;
UPDATE bytes SET dword = 0x90909090 WHERE ea = 0x401000;  -- little-endian

-- Inspect patch inventory (fast: backed by IDA's patch list)
SELECT printf('0x%X', ea) AS ea, original_value, value AS patched_value
FROM bytes WHERE is_patched = 1 ORDER BY ea LIMIT 20;

-- Persist once done
SELECT save_database();
```

---

## bytes — Patching (write surface)

All byte patching is done through the writable `bytes` table. There are no
`patch_*` / `revert_byte` / `get_original_byte` scalar functions.

| Column | RW | Meaning |
|--------|----|---------|
| `value` | RW | Current byte; UPDATE patches 1 byte |
| `word` / `dword` / `qword` | RW | UPDATE patches 2/4/8 bytes little-endian |
| `original_value` | R | Original (pre-patch) byte |
| `is_patched` | R | 1 if patched; `WHERE is_patched = 1` enumerates patches fast |

```sql
SELECT printf('0x%X', ea) AS ea,
       printf('0x%02X', original_value) AS old,
       printf('0x%02X', value) AS new
FROM bytes WHERE is_patched = 1
ORDER BY ea;
```

---

## SQL Functions — Byte Access

| Function | Description |
|----------|-------------|
| `bytes(addr, n)` | Read `n` raw bytes as hex string |
| `bytes_raw(addr, n)` | Read `n` bytes as BLOB |
| `load_file_bytes(path, file_offset, address, size[, patchable])` | Load patch bytes from a host file into memory/file image |

```sql
-- Read bytes
SELECT bytes(0x401000, 16);

-- Patch one byte (example: NOP) and a 4-byte little-endian value
UPDATE bytes SET value = 0x90 WHERE ea = 0x401000;
UPDATE bytes SET dword = 0x90909090 WHERE ea = 0x401000;

-- Verify current vs original
SELECT value AS current, original_value AS original
FROM bytes WHERE ea = 0x401000;

-- Revert patch (one byte, or every patch)
DELETE FROM bytes WHERE ea = 0x401000;
DELETE FROM bytes WHERE is_patched = 1;

-- Persist patches explicitly
SELECT save_database();
```

`load_file_bytes(...)` is the bulk alternative to per-row `UPDATE bytes` patching when the patch content already exists in a file. (The old `patch_byte`/`patch_word`/`patch_dword`/`patch_qword` scalars no longer exist — patch through the `bytes` table instead.)

---

## Analysis-Driven Breakpoint Workflows

### Set breakpoints on all callers of a security-sensitive API

Use disasm_calls to find every call site and batch-insert breakpoints:

```sql
-- Breakpoint on every call to VirtualAlloc (or similar)
INSERT INTO breakpoints (address)
SELECT ea FROM disasm_calls WHERE callee_name LIKE '%VirtualAlloc%';

-- Verify
SELECT printf('0x%08X', address) AS addr, type_name, enabled
FROM breakpoints;
```

### Watchpoints on struct fields discovered via type analysis

After recovering a struct, set hardware watchpoints on specific field offsets:

```sql
-- Hardware write watchpoint on a 4-byte field (e.g., config.flags at base+0x10)
-- First, find where the struct base is stored (requires manual analysis)
INSERT INTO breakpoints (address, type, size) VALUES (0x402010, 1, 4);
-- type=1 is hardware_write, size=4 for DWORD field
```

### Conditional breakpoints from decompiler analysis

Set breakpoints that only trigger when specific conditions are met:

```sql
-- Break when first argument (rcx on x64 fastcall) equals a specific enum value
INSERT INTO breakpoints (address, condition)
VALUES (0x401000, 'rcx == 3');

-- Break on error return
INSERT INTO breakpoints (address, condition)
VALUES (0x401050, 'rax == 0xFFFFFFFF');
```

---

## Patching Workflows

### NOP out anti-debug checks

Find and neutralize `IsDebuggerPresent` checks:

```sql
-- Find calls to IsDebuggerPresent
SELECT dc.ea, (SELECT name FROM funcs WHERE dc.func_addr >= address AND dc.func_addr < end_ea LIMIT 1) AS func_name,
       disasm_at(dc.ea, 2) AS context
FROM disasm_calls dc
WHERE dc.callee_name LIKE '%IsDebuggerPresent%';

-- Patch the conditional jump after the check (example: jnz → nop nop)
-- First inspect the instruction after the call
SELECT disasm_at(0x401030, 3);
-- Then patch (adjust addresses based on actual binary)
UPDATE bytes SET value = 0x90 WHERE ea = 0x401035;
UPDATE bytes SET value = 0x90 WHERE ea = 0x401036;
```

### Inventory all patches and generate report

```sql
-- Full patch report: what was changed and where
SELECT printf('0x%X', ea) AS address,
       (SELECT name FROM funcs WHERE ea >= address AND ea < end_ea LIMIT 1) AS func_name,
       printf('0x%02X', original_value) AS original,
       printf('0x%02X', value) AS patched,
       disasm_at(ea) AS context
FROM bytes WHERE is_patched = 1
ORDER BY ea;
```

---

## Performance Notes

| Table | Size | Constraint | Notes |
|-------|------|-----------|-------|
| `breakpoints` | Small (<100 typical) | none needed | Always fast |
| `bytes` | All mapped bytes | `ea` | **Critical** — constrain to one address or a tight range |
| `bytes WHERE is_patched = 1` | Small (patch count) | `is_patched = 1` | Fast — iterates only patched locations via IDA's patch list |

- `breakpoints` table is small — full scans are fine.
- `bytes` table emits one row per mapped byte. Use `WHERE ea = X` or a tight `ea` range.
- `bytes WHERE is_patched = 1` iterates only patched locations — always fast.

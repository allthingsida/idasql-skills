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

-- 2) Current patch inventory
SELECT printf('0x%X', ea) AS ea, original_value, patched_value
FROM patched_bytes
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
  - Re-read `bytes` and `patched_bytes`, then retry with precise address.
- Unintended patch side effects:
  - Revert with `revert_byte(...)` and reassess target instruction context.

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

Byte-wise program view with patch support.

| Column | Type | RW | Description |
|--------|------|----|-------------|
| `ea` | INT | R | Address |
| `value` | INT | RW | Current byte value (UPDATE patches byte) |
| `original_value` | INT | R | Original byte value before patch |
| `size` | INT | R | Item size at address |
| `type` | TEXT | R | Item type (`code`, `data`, etc.) |
| `is_patched` | INT | R | 1 if byte differs from original |

```sql
-- Read one address
SELECT ea, value, original_value, is_patched
FROM bytes WHERE ea = 0x401000;

-- Patch via table update
UPDATE bytes SET value = 0x90 WHERE ea = 0x401000;

-- Inspect patch inventory
SELECT * FROM patched_bytes LIMIT 20;

-- Persist once done
SELECT save_database();
```

---

## patched_bytes

All patched locations tracked by IDA.

| Column | Type | Description |
|--------|------|-------------|
| `ea` | INT | Patched address |
| `original_value` | INT | Original byte value |
| `patched_value` | INT | Current patched value |
| `fpos` | INT | File offset when available |

```sql
SELECT printf('0x%X', ea) AS ea,
       printf('0x%02X', original_value) AS old,
       printf('0x%02X', patched_value) AS new
FROM patched_bytes
ORDER BY ea;
```

---

## SQL Functions — Byte Patching

| Function | Description |
|----------|-------------|
| `bytes(addr, n)` | Read `n` bytes as hex string |
| `bytes_raw(addr, n)` | Read `n` bytes as BLOB |
| `load_file_bytes(path, file_offset, address, size[, patchable])` | Load patch bytes from a host file into memory/file image |
| `patch_byte(addr, val)` | Patch one byte at `addr` (returns 1/0) |
| `patch_word(addr, val)` | Patch 2 bytes at `addr` (returns 1/0) |
| `patch_dword(addr, val)` | Patch 4 bytes at `addr` (returns 1/0) |
| `patch_qword(addr, val)` | Patch 8 bytes at `addr` (returns 1/0) |
| `revert_byte(addr)` | Revert one patched byte to original |
| `get_original_byte(addr)` | Read original (pre-patch) byte |

```sql
-- Read bytes
SELECT bytes(0x401000, 16);

-- Patch one byte (example: NOP)
SELECT patch_byte(0x401000, 0x90) AS ok;

-- Verify current vs original
SELECT bytes(0x401000, 1) AS current, get_original_byte(0x401000) AS original;

-- Revert patch
SELECT revert_byte(0x401000) AS reverted;

-- Persist patches explicitly
SELECT save_database();
```

`load_file_bytes(...)` is the bulk alternative to `patch_*` helpers when patch content already exists in a file.

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
SELECT dc.ea, func_at(dc.func_addr) AS func_name,
       disasm_at(dc.ea, 2) AS context
FROM disasm_calls dc
WHERE dc.callee_name LIKE '%IsDebuggerPresent%';

-- Patch the conditional jump after the check (example: jnz → nop nop)
-- First inspect the instruction after the call
SELECT disasm_at(0x401030, 3);
-- Then patch (adjust addresses based on actual binary)
SELECT patch_byte(0x401035, 0x90);
SELECT patch_byte(0x401036, 0x90);
```

### Inventory all patches and generate report

```sql
-- Full patch report: what was changed and where
SELECT printf('0x%X', ea) AS address,
       func_at(ea) AS func_name,
       printf('0x%02X', original_value) AS original,
       printf('0x%02X', patched_value) AS patched,
       disasm_at(ea) AS context
FROM patched_bytes
ORDER BY ea;
```

---

## Performance Notes

| Table | Size | Constraint | Notes |
|-------|------|-----------|-------|
| `breakpoints` | Small (<100 typical) | none needed | Always fast |
| `bytes` | Entire address space | `ea` | **Critical** — without `ea` constraint, iterates entire address space |
| `patched_bytes` | Small (patch count) | none needed | Scans all patches, usually tiny |

- `breakpoints` table is small — full scans are fine.
- `bytes` table maps the entire virtual address space. **Never query without `WHERE ea = X`** or a tight address range.
- `patched_bytes` iterates only patched locations — always fast.

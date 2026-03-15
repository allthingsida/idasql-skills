# Structure Recovery Patterns

Common patterns for reconstructing struct definitions from decompiled offset casts.

## Pattern 1: Direct Offset Access

Decompiled code: `*(DWORD *)(a1 + 0x10)`

This means: `a1` is a pointer to a struct with a `DWORD` field at offset `0x10`.

```sql
-- Find all offset accesses on a parameter
SELECT ea, num_value as offset, op_name
FROM ctree WHERE func_addr = 0x401000
  AND op_name = 'cot_add'
  AND num_value IS NOT NULL
ORDER BY num_value;
```

## Pattern 2: Array-like Access

Decompiled code: `*((BYTE *)a1 + i + 0x20)`

This means: `a1` has a byte array starting at offset `0x20`.

## Pattern 3: Nested Struct Access

Decompiled code: `*(DWORD *)(*((_QWORD *)a1 + 2) + 0x18)`

This means:
- `a1` has a pointer field at offset `+0x10` (offset 2 * 8 for QWORD)
- That pointer points to another struct with a DWORD field at `+0x18`

## Pattern 4: Function Pointer Tables (vtable)

Decompiled code: `(*(void (__fastcall **)(a1, int))(*((_QWORD *)a1) + 0x18))(a1, 42)`

This means:
- `a1[0]` is a vtable pointer
- vtable offset `+0x18` is a virtual function taking `(this, int)`

```sql
-- Find vtable-like patterns: calls through double-deref
SELECT ea, op_name FROM ctree
WHERE func_addr = 0x401000
  AND op_name = 'cot_call'
  AND depth > 3;
```

## Pattern 5: Cross-Function Discovery

```sql
-- Step 1: Find all functions that take the same struct pointer (first arg)
-- Look for functions called with the same variable
SELECT DISTINCT dc.callee_name, dc.callee_addr
FROM disasm_calls dc
WHERE dc.func_addr = 0x401000;

-- Step 2: For each callee, examine what offsets it accesses
-- This reveals fields the current function doesn't use
SELECT func_at(func_addr) as func, num_value as offset
FROM ctree
WHERE func_addr IN (0x401050, 0x401080, 0x4010B0)
  AND op_name = 'cot_add'
  AND num_value IS NOT NULL
GROUP BY func_addr, num_value
ORDER BY num_value;

-- Step 3: Build comprehensive field map
-- Combine discovered offsets from all functions
```

## Pattern 6: Enum Detection from Switch/Case

When a function switches on a field value, the cases often map to enum values:

```sql
-- Find switch-like comparisons in the function
SELECT ea, op_name, num_value
FROM ctree WHERE func_addr = 0x401000
  AND op_name IN ('cot_eq', 'cot_ne')
  AND num_value IS NOT NULL
ORDER BY num_value;

-- Create the enum from discovered values
INSERT INTO types (name, kind) VALUES ('MY_CMD_TYPE', 'enum');
-- Get ordinal, then add values:
INSERT INTO types_enum_values (type_ordinal, value_name, value) VALUES (50, 'CMD_INIT', 0);
INSERT INTO types_enum_values (type_ordinal, value_name, value) VALUES (50, 'CMD_READ', 1);
INSERT INTO types_enum_values (type_ordinal, value_name, value) VALUES (50, 'CMD_WRITE', 2);
```

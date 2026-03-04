---
name: types
description: "IDA type system: create/modify/apply structs, unions, enums, typedefs, parse_decls."
---

This skill is the **authoritative reference** for IDA's type system as exposed through idasql. For annotation workflows that use types, see `annotations`. For decompiler-specific type interactions (ctree, lvars, union selection, numform), see `decompiler`.

---

## Trigger Intents

Use this skill when user asks to:
- create/edit structs, unions, enums, typedefs
- inspect function prototype argument types
- resolve hidden pointer/typedef behavior
- apply or refine recovered data models

Route to:
- `decompiler` for expression-level type context
- `annotations` for applying and documenting type decisions
- `resource` for recursive structure-recovery workflows

---

## Do This First (Warm-Start Sequence)

```sql
-- 1) Inventory local types
SELECT ordinal, name, kind, size
FROM types
ORDER BY ordinal
LIMIT 30;

-- 2) Large/high-signal structs
SELECT name, size
FROM types
WHERE is_struct = 1
ORDER BY size DESC
LIMIT 20;

-- 3) Prototype introspection sample
SELECT type_name, arg_index, arg_name, arg_type
FROM types_func_args
WHERE arg_index >= 0
LIMIT 40;
```

Interpretation guidance:
- Start with inventory and prioritize large/high-fanout types.
- Use `types_func_args` resolved fields for typedef-aware reasoning.

---

## Failure and Recovery

- Type insert/update failed:
  - Validate declaration syntax and target ordinal/name existence.
- Conflicting/incomplete type picture:
  - Correlate with `decompiler` (`ctree_lvars`, call args) before committing changes.
- Unexpected disassembly rendering:
  - Re-check operand format settings and applied declarations.

---

## Handoff Patterns

1. `types` -> `decompiler` to validate semantic effect in pseudocode.
2. `types` -> `annotations` for naming/comments on newly typed fields.
3. `types` -> `resource` for multi-function struct refinement.

---

## Type Tables

### local_types

Local type declarations as stored in the database.
Use this for quick inventory/filtering of local types; use `types*` tables for deeper editing workflows.

| Column | Type | Description |
|--------|------|-------------|
| `ordinal` | INT | Type ordinal (local type ID) |
| `name` | TEXT | Type name |
| `type` | TEXT | Declared type text |
| `is_struct` | INT | 1=struct |
| `is_enum` | INT | 1=enum |
| `is_typedef` | INT | 1=typedef |

```sql
-- Quick local type inventory
SELECT ordinal, name, type FROM local_types ORDER BY ordinal LIMIT 50;
```

For canonical schema and owner mapping, see `../connect/references/schema-catalog.md` (`local_types`).

### types

All local type definitions. Supports INSERT (create struct/union/enum), UPDATE, and DELETE.

| Column | Type | Description |
|--------|------|-------------|
| `ordinal` | INT | Type ordinal (unique identifier) |
| `name` | TEXT | Type name |
| `size` | INT | Size in bytes |
| `kind` | TEXT | struct/union/enum/typedef/func |
| `is_struct` | INT | 1=struct |
| `is_union` | INT | 1=union |
| `is_enum` | INT | 1=enum |

```sql
-- List all structs
SELECT ordinal, name, size FROM types WHERE is_struct = 1 ORDER BY size DESC;

-- List all enums
SELECT ordinal, name FROM types WHERE is_enum = 1;

-- Find types by name pattern
SELECT * FROM types WHERE name LIKE '%CONTEXT%';
```

### Creating Types

```sql
-- Create a struct
INSERT INTO types (name, kind) VALUES ('MY_HEADER', 'struct');

-- Create a union
INSERT INTO types (name, kind) VALUES ('PARAM_UNION', 'union');

-- Create an enum
INSERT INTO types (name, kind) VALUES ('CMD_TYPE', 'enum');

-- Verify creation (get the assigned ordinal)
SELECT ordinal, name, kind FROM types WHERE name = 'MY_HEADER';
```

### Deleting Types

```sql
-- Delete a type by name
DELETE FROM types WHERE name = 'MY_HEADER';

-- Delete by ordinal
DELETE FROM types WHERE ordinal = 42;
```

---

### types_members

Structure and union members. Supports INSERT, UPDATE, and DELETE.

| Column | Type | Description |
|--------|------|-------------|
| `type_ordinal` | INT | Parent type ordinal |
| `type_name` | TEXT | Parent type name |
| `member_name` | TEXT | Member name |
| `offset` | INT | Byte offset |
| `size` | INT | Member size |
| `member_type` | TEXT | Type string (e.g., `int`, `void *`, `char[256]`) |
| `mt_is_ptr` | INT | 1=pointer |
| `mt_is_array` | INT | 1=array |
| `mt_is_struct` | INT | 1=embedded struct |

```sql
-- View members of a struct
SELECT member_name, member_type, offset, size
FROM types_members WHERE type_name = 'MY_HEADER'
ORDER BY offset;

-- Add a member with explicit type
INSERT INTO types_members (type_ordinal, member_name, member_type)
VALUES (42, 'magic', 'unsigned int');

-- Add a pointer member
INSERT INTO types_members (type_ordinal, member_name, member_type)
VALUES (42, 'data_ptr', 'void *');

-- Add a fixed-size array member
INSERT INTO types_members (type_ordinal, member_name, member_type)
VALUES (42, 'name', 'char[64]');

-- Add a member with default type
INSERT INTO types_members (type_ordinal, member_name)
VALUES (42, 'reserved');

-- Rename a member
UPDATE types_members SET member_name = 'signature'
WHERE type_ordinal = 42 AND member_name = 'magic';

-- Change member type
UPDATE types_members SET member_type = 'DWORD'
WHERE type_ordinal = 42 AND member_name = 'signature';

-- Delete a member
DELETE FROM types_members
WHERE type_ordinal = 42 AND member_name = 'reserved';
```

---

### types_enum_values

Enum constant values. Supports INSERT, UPDATE, and DELETE.

| Column | Type | Description |
|--------|------|-------------|
| `type_ordinal` | INT | Enum type ordinal |
| `type_name` | TEXT | Enum name |
| `value_name` | TEXT | Constant name |
| `value` | INT | Constant value |

```sql
-- View enum values
SELECT value_name, value FROM types_enum_values
WHERE type_name = 'CMD_TYPE'
ORDER BY value;

-- Add enum values
INSERT INTO types_enum_values (type_ordinal, value_name, value)
VALUES (50, 'CMD_INIT', 0);
INSERT INTO types_enum_values (type_ordinal, value_name, value)
VALUES (50, 'CMD_READ', 1);
INSERT INTO types_enum_values (type_ordinal, value_name, value)
VALUES (50, 'CMD_WRITE', 2);
INSERT INTO types_enum_values (type_ordinal, value_name, value)
VALUES (50, 'CMD_CLOSE', 3);

-- Add enum value with comment
INSERT INTO types_enum_values (type_ordinal, value_name, value, comment)
VALUES (50, 'CMD_SHUTDOWN', 0xFF, 'only used during cleanup');

-- Rename an enum value
UPDATE types_enum_values SET value_name = 'CMD_OPEN'
WHERE type_ordinal = 50 AND value_name = 'CMD_INIT';

-- Delete an enum value
DELETE FROM types_enum_values
WHERE type_ordinal = 50 AND value_name = 'CMD_SHUTDOWN';
```

---

### types_func_args

Function prototype arguments with deep type classification.

| Column | Type | Description |
|--------|------|-------------|
| `type_ordinal` | INT | Function type ordinal |
| `type_name` | TEXT | Function type name |
| `arg_index` | INT | Argument index (-1 = return type, 0+ = args) |
| `arg_name` | TEXT | Argument name |
| `arg_type` | TEXT | Argument type string |
| `calling_conv` | TEXT | Calling convention (on return row only) |

#### Surface-Level Type Classification

Literal type as written — what you see in the declaration:

| Column | Description |
|--------|-------------|
| `is_ptr` | 1 if pointer type |
| `is_int` | 1 if exactly `int` |
| `is_integral` | 1 if int-like (int, long, short, char, bool) |
| `is_float` | 1 if float/double |
| `is_void` | 1 if void |
| `is_struct` | 1 if struct/union |
| `is_array` | 1 if array |
| `ptr_depth` | Pointer depth (int** = 2) |
| `base_type` | Type with pointers stripped |

#### Resolved Type Classification

After typedef resolution — what the type actually is:

| Column | Description |
|--------|-------------|
| `is_ptr_resolved` | 1 if resolved type is pointer |
| `is_int_resolved` | 1 if resolved type is exactly int |
| `is_integral_resolved` | 1 if resolved type is int-like |
| `is_float_resolved` | 1 if resolved type is float/double |
| `is_void_resolved` | 1 if resolved type is void |
| `ptr_depth_resolved` | Pointer depth after resolution |
| `base_type_resolved` | Resolved type with pointers stripped |

This dual classification is critical for typedef-aware queries. For example, `HANDLE` appears as non-pointer at surface level but resolves to `void *`.

```sql
-- Typedefs that hide pointers (HANDLE, HMODULE, etc.)
SELECT DISTINCT type_name, arg_type, base_type_resolved
FROM types_func_args
WHERE is_ptr = 0 AND is_ptr_resolved = 1;

-- Functions returning integers (strict: exactly int)
SELECT type_name FROM types_func_args
WHERE arg_index = -1 AND is_int = 1;

-- Functions returning integers (loose: includes BOOL, DWORD, LONG)
SELECT type_name FROM types_func_args
WHERE arg_index = -1 AND is_integral_resolved = 1;

-- Functions taking 4 pointer arguments
SELECT type_name, COUNT(*) as ptr_args FROM types_func_args
WHERE arg_index >= 0 AND is_ptr = 1
GROUP BY type_ordinal HAVING ptr_args = 4;

-- Functions with string parameters
SELECT DISTINCT type_name FROM types_func_args
WHERE arg_index >= 0 AND is_ptr = 1
  AND base_type_resolved IN ('char', 'wchar_t', 'CHAR', 'WCHAR');

-- Functions returning void pointers
SELECT type_name FROM types_func_args
WHERE arg_index = -1 AND is_ptr_resolved = 1 AND is_void_resolved = 1;

-- Functions with struct parameters
SELECT type_name, arg_name, arg_type FROM types_func_args
WHERE arg_index >= 0 AND is_struct = 1;
```

---

## Type Views

Convenience views for filtering types:

| View | Description |
|------|-------------|
| `types_v_structs` | `SELECT * FROM types WHERE is_struct = 1` |
| `types_v_unions` | `SELECT * FROM types WHERE is_union = 1` |
| `types_v_enums` | `SELECT * FROM types WHERE is_enum = 1` |
| `types_v_typedefs` | `SELECT * FROM types WHERE is_typedef = 1` |
| `types_v_funcs` | `SELECT * FROM types WHERE is_func = 1` |

---

## Importing C Declarations (parse_decls)

`parse_decls(text)` imports C declarations into the local type library. This is the most powerful way to seed types.

```sql
-- Import a simple struct
SELECT parse_decls('
struct MY_HEADER {
    unsigned int magic;
    unsigned int version;
    unsigned int size;
    void *data;
};
');

-- Import with pragmas for packing
SELECT parse_decls('
#pragma pack(push, 1)
typedef struct _iobuf FILE;
typedef enum operations_e {
    op_empty = 0,
    op_open = 11,
    op_read = 22,
    op_close = 1,
    op_seek = 2,
    op_read4 = 3
} operations_e;
typedef struct open_t { const char* filename; const char* mode; FILE** fp; } open_t;
typedef struct close_t { FILE* fp; } close_t;
typedef struct read_t { FILE* fp; void* buf; unsigned __int64 size; } read_t;
typedef struct seek_t { FILE* fp; __int64 offset; int whence; } seek_t;
typedef struct read4_t { FILE* fp; __int64 seek; int val; } read4_t;
typedef struct command_t {
    operations_e cmd_id;
    union {
        open_t open;
        read_t read;
        read4_t read4;
        seek_t seek;
        close_t close;
    } ops;
    unsigned __int64 ret;
} command_t;
#pragma pack(pop)
');

-- Verify imported types
SELECT name, kind, size FROM types WHERE name IN ('command_t', 'operations_e', 'open_t');
```

---

## Applying Types to Functions and Variables

### Function Prototypes

```sql
-- Apply type to function via prototype column
UPDATE funcs SET prototype = 'void __fastcall exec_command(command_t *cmd);'
WHERE address = 0x140001BD0;

-- Apply via set_type function
SELECT set_type(0x140001BD0, 'void __fastcall exec_command(command_t *cmd);');

-- Read current type at address
SELECT type_at(0x140001BD0);

-- Clear type (reset to auto-detected)
SELECT set_type(0x140001BD0, '');

-- Re-decompile to see effect
SELECT decompile(0x140001BD0, 1);
```

### Local Variables

```sql
-- Change local variable type
UPDATE ctree_lvars SET type = 'MY_HEADER *'
WHERE func_addr = 0x401000 AND idx = 0;

-- Change and verify
SELECT decompile(0x401000, 1);
SELECT idx, name, type FROM ctree_lvars
WHERE func_addr = 0x401000 AND idx = 0;
```

### Names

```sql
-- Set a name at address
SELECT set_name(0x402000, 'g_config');
```

---

## Struct Offset Representation in Disassembly

The `instructions` table `operand*_format_spec` column applies struct offset display to disassembly operands:

```sql
-- Apply struct-offset representation to a disassembly operand
-- This makes `[rax+10h]` display as `[rax+MY_STRUCT.field_name]`
UPDATE instructions
SET operand0_format_spec = 'stroff:MY_STRUCT,delta=0'
WHERE address = 0x401030;

-- Apply enum representation to an immediate operand
UPDATE instructions
SET operand1_format_spec = 'enum:CMD_TYPE'
WHERE address = 0x401020;

-- Clear back to plain numeric display
UPDATE instructions
SET operand0_format_spec = 'clear'
WHERE address = 0x401030;
```

---

## Enum/Union Rendering in Decompiled Code

For numform helpers (`set_numform*`) and union selection helpers (`set_union_selection*`), see `decompiler` skill.

---

## Complete Type Workflow Example

```sql
-- 1. Import declarations
SELECT parse_decls('
struct NETWORK_CONFIG {
    unsigned int flags;
    char server[256];
    unsigned short port;
    void *context;
};
enum NET_FLAGS {
    NET_FLAG_NONE = 0,
    NET_FLAG_SSL = 1,
    NET_FLAG_KEEPALIVE = 2,
    NET_FLAG_COMPRESS = 4
};
');

-- 2. Apply struct to a function parameter
UPDATE funcs SET prototype = 'int __cdecl init_network(NETWORK_CONFIG *cfg);'
WHERE address = 0x401000;

-- 3. Apply enum rendering in disassembly
UPDATE instructions SET operand1_format_spec = 'enum:NET_FLAGS'
WHERE address = 0x401020;

-- 4. Apply enum rendering in decompiled code
SELECT set_numform_ea_expr(0x401000, 0x401025, 0, 'enum:NET_FLAGS', 'cot_band', 0);

-- 5. Verify
SELECT decompile(0x401000, 1);

-- 6. Save
SELECT save_database();
```

---

## Performance Rules

| Table | Architecture | Key Constraint | Notes |
|-------|-------------|----------------|-------|
| `types` | Cached | `ordinal` (optional) | Full cache rebuilt on demand; usually fast (<1000 types) |
| `types_members` | Cached | `type_ordinal` | O(1) lookup with constraint; without it iterates all types |
| `types_enum_values` | Cached | `type_ordinal` | O(1) lookup with constraint |
| `types_func_args` | Cached | `type_ordinal` | O(1) lookup with constraint |

**Key rules:**
- `type_ordinal` constraint pushdown gives O(1) access to a single type's members, enum values, or func args.
- Without constraint, these tables iterate all local types. This is usually fast (most binaries have <1000 local types), but prefer filtered queries when you know the target.
- Type views (`types_v_structs`, etc.) are pre-filtered — use them for categorical queries.
- `parse_decls()` is the fastest way to seed multiple types at once (single call vs multiple INSERTs).

---

## Advanced Type Patterns (CTEs)

### Find structs used as function parameters across the codebase

Discover which structs are most widely used — high-value targets for annotation:

```sql
-- Structs passed as parameters to the most functions
WITH struct_params AS (
    SELECT DISTINCT tfa.type_ordinal,
           tfa.base_type_resolved AS struct_name,
           tfa.type_name AS func_type
    FROM types_func_args tfa
    WHERE tfa.arg_index >= 0
      AND tfa.is_struct = 1
)
SELECT struct_name,
       COUNT(*) AS used_by_funcs
FROM struct_params
GROUP BY struct_name
ORDER BY used_by_funcs DESC
LIMIT 15;
```

### Discover potential enum values from magic number comparisons

Find functions that compare the same variable against multiple constants — these constants are likely enum values:

```sql
-- Functions with many numeric comparisons (enum candidate detection)
WITH comparisons AS (
    SELECT func_addr,
           func_at(func_addr) AS func_name,
           num_value
    FROM ctree
    WHERE func_addr IN (SELECT address FROM funcs LIMIT 200)
      AND op_name IN ('cot_eq', 'cot_ne')
      AND num_value IS NOT NULL
      AND num_value BETWEEN 0 AND 255
)
SELECT func_name,
       COUNT(DISTINCT num_value) AS distinct_constants,
       GROUP_CONCAT(DISTINCT num_value) AS values_seen
FROM comparisons
GROUP BY func_addr
HAVING distinct_constants >= 4
ORDER BY distinct_constants DESC;
```

### Type coverage analysis — functions with vs without typed parameters

Gauge how much type recovery work remains:

```sql
-- Count functions by typing status
WITH func_typing AS (
    SELECT f.address,
           f.name,
           CASE WHEN f.return_type IS NOT NULL AND f.return_type != '' THEN 1 ELSE 0 END AS has_return_type,
           CASE WHEN f.arg_count > 0 THEN 1 ELSE 0 END AS has_args
    FROM funcs f
    WHERE f.name NOT LIKE 'sub_%'
)
SELECT
    COUNT(*) AS total_named_funcs,
    SUM(has_return_type) AS with_return_type,
    SUM(has_args) AS with_args,
    COUNT(*) - SUM(has_return_type) AS missing_return_type
FROM func_typing;
```

### Find large structs with many pointer members (likely vtables or dispatch tables)

```sql
SELECT t.name, t.size,
       COUNT(*) AS ptr_members,
       COUNT(*) * 100.0 / MAX(1, (SELECT COUNT(*) FROM types_members WHERE type_ordinal = t.ordinal)) AS ptr_pct
FROM types t
JOIN types_members tm ON tm.type_ordinal = t.ordinal
WHERE tm.mt_is_ptr = 1 AND t.is_struct = 1
GROUP BY t.ordinal
HAVING ptr_members >= 3
ORDER BY ptr_members DESC;
```

---

## Related Skills

- **`annotations`** — Workflow expert: how to combine type application with renaming and commenting
- **`decompiler`** — Deep ctree mechanics, union selection, numform, mutation loop
- **`resource`** — Structure recovery methodology from offset casts

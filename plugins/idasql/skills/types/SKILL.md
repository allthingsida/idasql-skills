---
name: types
description: "IDA type system. Use when asked to create, modify, or apply structs, unions, enums, typedefs, or parse C declarations."
allowed-tools:
  - Bash
  - Read
  - Glob
  - Grep
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
- `re-source` for recursive structure-recovery workflows

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
3. `types` -> `re-source` for multi-function struct refinement.

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

-- Add members (member_type supports: int, void *, char[64], etc.)
INSERT INTO types_members (type_ordinal, member_name, member_type)
VALUES (42, 'magic', 'unsigned int');
INSERT INTO types_members (type_ordinal, member_name, member_type)
VALUES (42, 'data_ptr', 'void *');

-- Rename/retype a member
UPDATE types_members SET member_name = 'signature'
WHERE type_ordinal = 42 AND member_name = 'magic';
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

-- Add enum values (optional comment column supported)
INSERT INTO types_enum_values (type_ordinal, value_name, value)
VALUES (50, 'CMD_INIT', 0);
INSERT INTO types_enum_values (type_ordinal, value_name, value)
VALUES (50, 'CMD_READ', 1);

-- Rename / delete enum values
UPDATE types_enum_values SET value_name = 'CMD_OPEN'
WHERE type_ordinal = 50 AND value_name = 'CMD_INIT';
DELETE FROM types_enum_values
WHERE type_ordinal = 50 AND value_name = 'CMD_READ';
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

-- Functions with struct parameters
SELECT type_name, arg_name, arg_type FROM types_func_args
WHERE arg_index >= 0 AND is_struct = 1;
```

For more `types_func_args` query patterns (string parameters, pointer counts, return type filters), see [references/type-patterns.md](references/type-patterns.md).

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
| `types_v_inheritance` | Struct/class inheritance relationships (baseclasses from `types_members`) |

### `types_v_inheritance` view

Shows struct/class inheritance relationships extracted from baseclass members.

| Column | Type | Description |
|--------|------|-------------|
| `derived_ordinal` | INT | Ordinal of the derived type |
| `derived_name` | TEXT | Name of the derived type |
| `base_type_name` | TEXT | Name of the base type |
| `base_ordinal` | INT | Ordinal of the base type |
| `base_offset` | INT | Byte offset of the base within the derived type |

```sql
-- Find base classes of a type
SELECT * FROM types_v_inheritance WHERE derived_name = 'MyClass';

-- Recursive ancestors
WITH RECURSIVE ancestors(name, depth) AS (
    SELECT base_type_name, 1 FROM types_v_inheritance WHERE derived_name = 'MyClass'
    UNION ALL
    SELECT i.base_type_name, a.depth + 1
    FROM types_v_inheritance i JOIN ancestors a ON i.derived_name = a.name
    WHERE a.depth < 10
)
SELECT * FROM ancestors;
```

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

-- Import with pragmas for packing (enums, typedefs, nested unions)
SELECT parse_decls('
#pragma pack(push, 1)
typedef enum operations_e { op_empty=0, op_open=11, op_read=22 } operations_e;
typedef struct command_t { operations_e cmd_id; unsigned __int64 ret; } command_t;
#pragma pack(pop)
');

-- Verify imported types
SELECT name, kind, size FROM types WHERE name IN ('command_t', 'operations_e');
```

For a full multi-struct `parse_decls` example with nested unions, see [references/type-patterns.md](references/type-patterns.md).

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

### Call Sites

Use call-site typing for indirect calls when function prototypes and local-variable types still leave a specific call under-typed.

```sql
-- Discover indirect call sites first
SELECT call_ea, target_op, target_var_name, arg_count
FROM ctree_v_indirect_calls
WHERE func_addr = 0x140001BD0
ORDER BY call_ea;

-- Apply a prototype to one call site
SELECT apply_callee_type(
  0x140001C3E,
  'int __fastcall emit_message(const char *name, const char *target, int flag, const char *tag);'
);

-- Verify the persisted call-site typing
SELECT callee_type_at(0x140001C3E);
SELECT call_arg_addrs(0x140001C3E);
SELECT decompile(0x140001BD0, 1);
```

### Typing Surfaces Matrix

| Surface | Scope | Semantic vs render-only | Typical use |
|---------|-------|-------------------------|-------------|
| `UPDATE funcs SET prototype = ...` / `set_type()` | Function/global address | Semantic | Give a function or global the right declared type |
| `UPDATE ctree_lvars SET type = ...` | One decompiled local/arg | Semantic | Clean up local pointer/struct inference |
| `apply_callee_type(call_ea, decl)` | One call site | Semantic | Fix an indirect call when the callee prototype must be explicit |
| `instructions.operand*_format_spec` | One disassembly operand | Render-only | Show enums/struct offsets in listing output |
| `set_union_selection*` | One decompiler expression | Render-only | Choose a union arm for nicer pseudocode |
| `set_numform*` | One decompiler expression operand | Render-only | Change numeric rendering without changing base type |

### Names

```sql
-- Set a name at address
SELECT set_name(0x402000, 'g_config');
```

---

## Struct Offset Representation in Disassembly

The `instructions` table `operand*_format_spec` column applies struct offset display to disassembly operands:

```sql
-- Apply struct-offset: makes `[rax+10h]` display as `[rax+MY_STRUCT.field_name]`
UPDATE instructions SET operand0_format_spec = 'stroff:MY_STRUCT,delta=0'
WHERE address = 0x401030;

-- Apply enum: `enum:CMD_TYPE`; clear back to plain: `clear`
UPDATE instructions SET operand1_format_spec = 'enum:CMD_TYPE'
WHERE address = 0x401020;
```

---

## Enum/Union Rendering in Decompiled Code

For numform helpers (`set_numform*`) and union selection helpers (`set_union_selection*`), see `decompiler` skill.

`apply_callee_type` belongs on the semantic side of the fence: it affects call analysis, unlike render-only enum/union formatting helpers.

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

## Related Skills

- **`annotations`** — Workflow expert: how to combine type application with renaming and commenting
- **`decompiler`** — Deep ctree mechanics, union selection, numform, mutation loop
- **`re-source`** — Structure recovery methodology from offset casts

---

## Additional Resources

- For complete type workflow examples and advanced CTE patterns: [references/type-patterns.md](references/type-patterns.md)

# Type Patterns Reference

## types_func_args Query Patterns

```sql
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
```

---

## Complex parse_decls Example

Import multiple related types with pragmas, enums, nested unions:

```sql
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

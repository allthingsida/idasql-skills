# Ctree Manipulation Reference

## Ctree Node Types (Complete List)

### Expressions (cot_*)

| Node | Description | Key Fields |
|------|-------------|------------|
| `cot_call` | Function call | `obj_ea`, `obj_name` |
| `cot_var` | Local variable | `var_idx`, `var_name` |
| `cot_obj` | Global object/function | `obj_ea`, `obj_name` |
| `cot_num` | Numeric constant | `num_value` |
| `cot_str` | String literal | `str_value` |
| `cot_ptr` | Pointer dereference `*p` | `x_id` = operand |
| `cot_ref` | Address-of `&x` | `x_id` = operand |
| `cot_asg` | Assignment `x = y` | `x_id` = lhs, `y_id` = rhs |
| `cot_add` | Addition `x + y` | `x_id`, `y_id` |
| `cot_sub` | Subtraction `x - y` | `x_id`, `y_id` |
| `cot_mul` | Multiplication `x * y` | `x_id`, `y_id` |
| `cot_sdiv` | Signed division | `x_id`, `y_id` |
| `cot_udiv` | Unsigned division | `x_id`, `y_id` |
| `cot_eq` | Equal `x == y` | `x_id`, `y_id` |
| `cot_ne` | Not equal `x != y` | `x_id`, `y_id` |
| `cot_lt` | Less than (signed) | `x_id`, `y_id` |
| `cot_gt` | Greater than (signed) | `x_id`, `y_id` |
| `cot_land` | Logical AND `x && y` | `x_id`, `y_id` |
| `cot_lor` | Logical OR `x \|\| y` | `x_id`, `y_id` |
| `cot_lnot` | Logical NOT `!x` | `x_id` |
| `cot_band` | Bitwise AND `x & y` | `x_id`, `y_id` |
| `cot_bor` | Bitwise OR `x \| y` | `x_id`, `y_id` |
| `cot_xor` | Bitwise XOR `x ^ y` | `x_id`, `y_id` |
| `cot_idx` | Array index `a[i]` | `x_id` = base, `y_id` = index |
| `cot_memptr` | Member pointer `p->f` | `x_id`, `num_value` = offset |
| `cot_memref` | Member reference `s.f` | `x_id`, `num_value` = offset |
| `cot_cast` | Type cast `(type)x` | `x_id` |
| `cot_ternary` | Ternary `c ? a : b` | `x_id`, `y_id`, `z_id` |
| `cot_comma` | Comma operator `a, b` | `x_id`, `y_id` |
| `cot_helper` | Helper function call | use `call_helper_name` |

### Statements (cit_*)

| Node | Description | Key Fields |
|------|-------------|------------|
| `cit_if` | If statement | `x_id` = condition |
| `cit_for` | For loop | |
| `cit_while` | While loop | `x_id` = condition |
| `cit_do` | Do-while loop | `x_id` = condition |
| `cit_return` | Return statement | `x_id` = return value |
| `cit_block` | Code block `{ ... }` | |
| `cit_switch` | Switch statement | `x_id` = expression |
| `cit_break` | Break | |
| `cit_continue` | Continue | |
| `cit_goto` | Goto | `goto_label_num` = target label |
| `cit_expr` | Expression statement | `x_id` = expression |

## Querying Ctree Patterns

`ctree` also exposes control-flow label metadata:
- `label_num` on label-bearing nodes
- `goto_label_num` on `cit_goto` nodes

### Find All Calls to a Specific Function

```sql
SELECT item_id, ea, obj_name
FROM ctree
WHERE func_addr = 0x401000
  AND op_name = 'cot_call'
  AND obj_name LIKE '%malloc%';
```

### Find All Comparisons Against Zero

```sql
SELECT item_id, ea, parent_id
FROM ctree
WHERE func_addr = 0x401000
  AND op_name IN ('cot_eq', 'cot_ne')
  AND num_value = 0;
```

### Find All Variable Accesses

```sql
SELECT item_id, ea, var_name, var_idx
FROM ctree
WHERE func_addr = 0x401000
  AND op_name = 'cot_var'
ORDER BY ea;
```

### Find Struct Member Accesses (Pointer)

```sql
SELECT item_id, ea, num_value as field_offset
FROM ctree
WHERE func_addr = 0x401000
  AND op_name = 'cot_memptr'
ORDER BY num_value;
```

### Find All String Literals in a Function

```sql
SELECT item_id, ea, str_value
FROM ctree
WHERE func_addr = 0x401000
  AND op_name = 'cot_str';
```

### Find Label Definitions and Goto Targets

```sql
SELECT item_id, op_name, label_num, goto_label_num
FROM ctree
WHERE func_addr = 0x401000
  AND (label_num >= 0 OR goto_label_num >= 0)
ORDER BY item_id;

SELECT label_num, name, item_id, printf('0x%X', item_ea) AS item_ea
FROM ctree_labels
WHERE func_addr = 0x401000
ORDER BY label_num;
```

## Coordinate Resolution Helpers

When you need to target a specific expression for union selection or numform changes:

```sql
-- Resolve by EA + expression type + occurrence index
SELECT ctree_item_at(0x401000, 0x401030, 'cot_asg', 0);  -- first assignment at EA
SELECT ctree_item_at(0x401000, 0x401030, 'cot_eq', 0);   -- first comparison at EA
SELECT ctree_item_at(0x401000, 0x401030, 'cot_call', 1);  -- second call at EA

-- Resolve call argument to item ID
SELECT call_arg_item(0x401000, 0x401030, 0);       -- arg 0 of call at EA
SELECT call_arg_item(0x401000, 0x401030, 0, '__imp_fread');  -- disambiguate by callee
```

## Using ctree_call_args for Argument Analysis

```sql
-- Find all arguments passed to a specific callee
SELECT arg_idx, arg_op, arg_var_name, arg_num_value
FROM ctree_call_args
WHERE func_addr = 0x401000
  AND call_obj_name LIKE '%memcpy%';

-- Find calls where first arg is a stack variable (buffer overflow candidates)
SELECT call_obj_name, arg_var_name, arg_var_is_stk
FROM ctree_call_args
WHERE func_addr = 0x401000
  AND arg_idx = 0
  AND arg_var_is_stk = 1;
```

## Advanced Decompiler Patterns (CTEs)

### Functions with deeply nested control flow

Find functions with the most ctree depth -- indicators of complex logic, state machines, or obfuscation:

```sql
-- Top 10 functions by maximum AST depth
SELECT func_at(func_addr) AS name,
       printf('0x%X', func_addr) AS addr,
       MAX(depth) AS max_depth,
       COUNT(*) AS node_count
FROM ctree
WHERE func_addr IN (
    SELECT address FROM funcs ORDER BY size DESC LIMIT 50
)
GROUP BY func_addr
ORDER BY max_depth DESC
LIMIT 10;
```

### Cross-function variable type consistency

Find functions where the same-named local variable has different types -- sign of inconsistent annotation:

```sql
-- Variables named the same but typed differently across functions
WITH typed_vars AS (
    SELECT func_addr, name, type
    FROM ctree_lvars
    WHERE func_addr IN (
        SELECT address FROM funcs WHERE name NOT LIKE 'sub_%' LIMIT 100
    )
    AND name != '' AND type != ''
)
SELECT name, COUNT(DISTINCT type) AS type_variants,
       GROUP_CONCAT(DISTINCT type) AS types_seen
FROM typed_vars
GROUP BY name
HAVING type_variants > 1
ORDER BY type_variants DESC
LIMIT 20;
```

### Functions calling the same API with different argument patterns

Useful for understanding API usage conventions and finding anomalies:

```sql
-- How different functions call 'CreateFileW' -- what patterns emerge?
WITH call_sites AS (
    SELECT func_addr,
           func_at(func_addr) AS caller,
           arg_idx,
           arg_op,
           arg_num_value,
           arg_str_value,
           arg_var_name
    FROM ctree_call_args
    WHERE func_addr IN (
        SELECT DISTINCT func_addr FROM disasm_calls
        WHERE callee_name LIKE '%CreateFile%'
    )
    AND call_obj_name LIKE '%CreateFile%'
)
SELECT caller, arg_idx,
       arg_op, arg_num_value, arg_str_value, arg_var_name
FROM call_sites
ORDER BY arg_idx, caller;
```

### Decompiler-based string extraction (when strings table misses inline constants)

```sql
-- String literals visible in decompiled code (catches stack strings, computed strings)
SELECT func_at(func_addr) AS func,
       printf('0x%X', ea) AS addr,
       str_value
FROM ctree
WHERE func_addr = 0x401000
  AND op_name = 'cot_str'
  AND str_value IS NOT NULL;
```

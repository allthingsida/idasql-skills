# Decompiler Views Reference

## ctree_v_indirect_calls

Use this view to find call sites whose callee is not a direct `cot_obj` or `cot_helper`. It is the preferred discovery surface before `apply_callee_type(...)`.

| Column | Type | Description |
|--------|------|-------------|
| `func_addr` | INT | Function address |
| `call_item_id` | INT | Call expression item ID |
| `call_ea` | INT | Call instruction EA |
| `target_item_id` | INT | Callee expression item ID |
| `target_op` | TEXT | Callee expression opcode (`cot_var`, `cot_cast`, etc.) |
| `target_var_idx` | INT | Local-variable index when target is a variable |
| `target_var_name` | TEXT | Local-variable name when available |
| `call_obj_name` | TEXT | Object name when target expression still resolves to an object |
| `call_helper_name` | TEXT | Helper name when present |
| `arg_count` | INT | Flattened argument count from `ctree_call_args` |

```sql
SELECT call_ea, target_op, target_var_name, arg_count
FROM ctree_v_indirect_calls
WHERE func_addr = 0x140001BD0
ORDER BY call_ea;
```

## ctree_v_returns

Return statements with details about what's being returned.

| Column | Type | Description |
|--------|------|-------------|
| `func_addr` | INT | Function address |
| `item_id` | INT | Return statement item_id |
| `ea` | INT | Address of return |
| `return_op` | TEXT | Return value opcode (`cot_num`, `cot_var`, `cot_call`, etc.) |
| `return_num` | INT | Numeric value (if `cot_num`) |
| `return_str` | TEXT | String value (if `cot_str`) |
| `return_var` | TEXT | Variable name (if `cot_var`) |
| `returns_arg` | INT | 1 if returning a function argument |
| `returns_call_result` | INT | 1 if returning result of another call |

```sql
-- Functions that return 0
SELECT DISTINCT func_at(func_addr) as name FROM ctree_v_returns
WHERE return_op = 'cot_num' AND return_num = 0;

-- Functions that return -1 (error sentinel)
SELECT DISTINCT func_at(func_addr) as name FROM ctree_v_returns
WHERE return_op = 'cot_num' AND return_num = -1;

-- Functions that return their argument (pass-through)
SELECT DISTINCT func_at(func_addr) as name FROM ctree_v_returns
WHERE returns_arg = 1;
```

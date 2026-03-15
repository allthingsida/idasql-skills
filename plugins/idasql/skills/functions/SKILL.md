---
name: functions
description: "Complete idasql SQL function reference catalog. Use when looking up function signatures, parameters, or usage examples."
user-invocable: false
allowed-tools:
  - Bash
  - Read
  - Glob
  - Grep
---

This skill is a **comprehensive catalog** of every idasql SQL function. Use it to look up any function signature, parameters, and usage.

---

## Disassembly

| Function | Description |
|----------|-------------|
| `disasm_at(addr)` | Canonical listing line for containing head (works for code/data) |
| `disasm_at(addr, n)` | Canonical listing line with +/- `n` neighboring heads |
| `disasm(addr)` | Single disassembly line at address |
| `disasm(addr, n)` | Next N instructions from address (count-based, not boundary-aware) |
| `disasm_range(start, end)` | All disassembly lines in address range [start, end) |
| `disasm_func(addr)` | Full disassembly of function containing address |
| `make_code(addr)` | Create instruction at address (returns 1 if already code or created) |
| `make_code_range(start, end)` | Create instructions in [start, end), returns number created |
| `mnemonic(addr)` | Instruction mnemonic only |
| `operand(addr, n)` | Operand text (n=0-5) |

```sql
SELECT disasm_at(0x401000);
SELECT disasm_at(0x401000, 2);
SELECT disasm_func(address) FROM funcs WHERE name = '_main';
SELECT disasm_range(0x401000, 0x401100);
SELECT disasm(0x401000);
SELECT disasm(0x401000, 5);
SELECT make_code(0x401000);
SELECT make_code_range(0x401000, 0x401100);
```

Function creation is table-driven (not a SQL function):
```sql
INSERT INTO funcs (address) VALUES (0x401000);
```

---

## Byte Access and Patching

| Function | Description |
|----------|-------------|
| `bytes(addr, n)` | Read `n` bytes as hex string |
| `bytes_raw(addr, n)` | Read `n` bytes as BLOB |
| `load_file_bytes(path, file_offset, address, size[, patchable])` | Load bytes from a host file into IDB memory/file image |
| `patch_byte(addr, val)` | Patch one byte at `addr` (returns 1/0) |
| `patch_word(addr, val)` | Patch 2 bytes at `addr` (returns 1/0) |
| `patch_dword(addr, val)` | Patch 4 bytes at `addr` (returns 1/0) |
| `patch_qword(addr, val)` | Patch 8 bytes at `addr` (returns 1/0) |
| `revert_byte(addr)` | Revert one patched byte to original |
| `get_original_byte(addr)` | Read original (pre-patch) byte |

```sql
SELECT bytes(0x401000, 16);
SELECT patch_byte(0x401000, 0x90) AS ok;
SELECT bytes(0x401000, 1) AS current, get_original_byte(0x401000) AS original;
SELECT revert_byte(0x401000) AS reverted;
```

`load_file_bytes(...)` is intended for file-driven bulk patching workflows. It returns `1` on success, `0` on failure.

---

## Binary Search

| Function | Description |
|----------|-------------|
| `search_bytes(pattern)` | Find all matches, returns JSON array |
| `search_bytes(pattern, start, end)` | Search within address range |
| `search_first(pattern)` | First match address (or NULL) |
| `search_first(pattern, start, end)` | First match in range |

**Pattern syntax (IDA native):**
- `"48 8B 05"` - Exact bytes (hex, space-separated)
- `"48 ? 05"` or `"48 ?? 05"` - `?` = any byte wildcard (whole byte only)
- `"(01 02 03)"` - Alternatives (match any of these bytes)

```sql
SELECT search_bytes('48 8B ? 00');
SELECT json_extract(value, '$.address') as addr
FROM json_each(search_bytes('48 89 ?')) LIMIT 10;
SELECT printf('0x%llX', search_first('CC CC CC'));
```

**Optimization Pattern:**
```sql
-- Count unique functions containing RDTSC (opcode: 0F 31)
SELECT COUNT(DISTINCT func_start(json_extract(value, '$.address'))) as count
FROM json_each(search_bytes('0F 31'))
WHERE func_start(json_extract(value, '$.address')) IS NOT NULL;
```

---

## Names & Functions

Address argument note: `addr`/`ea`/`func_addr` parameters accept integer EAs, numeric strings, and symbol names.

| Function | Description |
|----------|-------------|
| `name_at(addr)` | Name at address |
| `func_at(addr)` | Function name containing address |
| `func_start(addr)` | Start of containing function |
| `func_end(addr)` | End of containing function |
| `func_qty()` | Total function count |
| `func_at_index(n)` | Function address at index (O(1)) |

---

## Cross-References

| Function | Description |
|----------|-------------|
| `xrefs_to(addr)` | JSON array of xrefs TO address |
| `xrefs_from(addr)` | JSON array of xrefs FROM address |

---

## Navigation

| Function | Description |
|----------|-------------|
| `next_head(addr)` | Next defined item |
| `prev_head(addr)` | Previous defined item |
| `segment_at(addr)` | Segment name at address |
| `hex(val)` | Format as hex string |

---

## Comments

| Function | Description |
|----------|-------------|
| `comment_at(addr)` | Get comment at address |
| `set_comment(addr, text)` | Set regular comment |
| `set_comment(addr, text, 1)` | Set repeatable comment |

---

## Modification

| Function | Description |
|----------|-------------|
| `set_name(addr, name)` | Set name at address |
| `type_at(addr)` | Read type declaration applied at address |
| `set_type(addr, decl)` | Apply C declaration/type at address (empty decl clears type; `addr` may be EA, numeric string, or symbol name) |
| `parse_decls(text)` | Import C declarations (struct/union/enum/typedef) into local types |

Preferred SQL write surface for function metadata:
- `UPDATE funcs SET name = '...', prototype = '...' WHERE address = ...`
- `prototype` maps to `type_at/set_type` behavior and invalidates decompiler cache.
- For per-call indirect-call typing, use `apply_callee_type(call_ea, decl)` from the decompiler surface.

---

## Python Execution

| Function | Description |
|----------|-------------|
| `idapython_snippet(code[, sandbox])` | Execute Python snippet and return captured output text |
| `idapython_file(path[, sandbox])` | Execute Python file and return captured output text |

Runtime guard:
```sql
PRAGMA idasql.enable_idapython = 1;
```

```sql
SELECT idapython_snippet('print("hello from idapython")');
SELECT idapython_file('C:/temp/script.py');
SELECT idapython_snippet('counter = globals().get("counter", 0) + 1; print(counter)', 'alpha');
```

---

## Context Awareness (Plugin UI)

| Function | Description |
|----------|-------------|
| `get_ui_context_json()` | Return current UI/widget/context JSON for context-aware prompts (plugin-only) |

```sql
SELECT get_ui_context_json();
```

---

## Item Analysis

| Function | Description |
|----------|-------------|
| `item_type(addr)` | Item type flags at address |
| `item_size(addr)` | Item size at address |
| `is_code(addr)` | Returns 1 if address is code |
| `is_data(addr)` | Returns 1 if address is data |
| `flags_at(addr)` | Raw IDA flags at address |

---

## Instruction Details

| Function | Description |
|----------|-------------|
| `itype(addr)` | Instruction type code (processor-specific) |
| `decode_insn(addr)` | Full instruction info as JSON |
| `operand_type(addr, n)` | Operand type code (o_void, o_reg, etc.) |
| `operand_value(addr, n)` | Operand value (register num, immediate, etc.) |

```sql
SELECT address, itype(address) as itype, mnemonic(address)
FROM heads WHERE is_code(address) = 1 LIMIT 10;
SELECT decode_insn(0x401000);
```

---

## Decompilation

| Function | Description |
|----------|-------------|
| `decompile(addr)` | **PREFERRED** — Full pseudocode with line prefixes |
| `decompile(addr, 1)` | Force re-decompilation (use after writes/renames) |
| `apply_callee_type(call_ea, decl)` | Apply a prototype to one indirect/dynamic call site |
| `callee_type_at(call_ea)` | Read explicit call-site prototype when present |
| `call_arg_addrs(call_ea)` | JSON array of persisted argument-loader instruction EAs |
| `list_lvars(addr)` | List local variables as JSON |
| `rename_lvar(func_addr, lvar_idx, new_name)` | Rename a local variable by index |
| `rename_lvar_by_name(func_addr, old_name, new_name)` | Rename a local variable by existing name |
| `rename_label(func_addr, label_num, new_name)` | Rename a decompiler control-flow label by label number |
| `set_lvar_comment(func_addr, lvar_idx, text)` | Set local-variable comment by index |
| `set_union_selection(func_addr, ea, path)` | Set/clear union selection path at EA |
| `set_union_selection_item(func_addr, item_id, path)` | Set/clear union selection path by `ctree.item_id` |
| `set_union_selection_ea_arg(func_addr, ea, arg_idx, path[, callee])` | **PREFERRED** call-arg targeting helper |
| `call_arg_item(func_addr, ea, arg_idx[, callee])` | Resolve call-arg coordinate to explicit `arg_item_id` |
| `ctree_item_at(func_addr, ea[, op_name[, nth]])` | Resolve generic expression coordinate to `ctree.item_id` |
| `set_union_selection_ea_expr(func_addr, ea, path[, op_name[, nth]])` | Set/clear union selection via expression coordinate |
| `get_union_selection(func_addr, ea)` | Read union selection path JSON at EA |
| `get_union_selection_item(func_addr, item_id)` | Read union selection path JSON by `ctree.item_id` |
| `get_union_selection_ea_arg(func_addr, ea, arg_idx[, callee])` | Read union selection JSON via call-arg coordinate |
| `get_union_selection_ea_expr(func_addr, ea[, op_name[, nth]])` | Read union selection JSON via expression coordinate |
| `set_numform(func_addr, ea, opnum, spec)` | Set/clear numform by EA + operand index |
| `get_numform(func_addr, ea, opnum)` | Read numform JSON by EA + operand index |
| `set_numform_item(func_addr, item_id, opnum, spec)` | Set/clear numform by ctree item id |
| `get_numform_item(func_addr, item_id, opnum)` | Read numform JSON by ctree item id |
| `set_numform_ea_arg(func_addr, ea, arg_idx, opnum, spec[, callee])` | Set/clear numform via call-arg coordinate |
| `get_numform_ea_arg(func_addr, ea, arg_idx, opnum[, callee])` | Read numform JSON via call-arg coordinate |
| `set_numform_ea_expr(func_addr, ea, opnum, spec[, op_name[, nth]])` | Set/clear numform via expression coordinate |
| `get_numform_ea_expr(func_addr, ea, opnum[, op_name[, nth]])` | Read numform JSON via expression coordinate |

`rename_lvar*` functions return JSON with explicit fields:
- `success` (execution success)
- `applied` (observable rename applied)
- `reason` (for non-applied cases: `not_found`, `ambiguous_name`, `unchanged`, `not_nameable`, ...)

---

## File Generation

| Function | Description |
|----------|-------------|
| `gen_listing(path)` | Generate a full-database listing file (LST) |

```sql
SELECT gen_listing('C:/tmp/full.lst');
```

---

## Graph Generation

| Function | Description |
|----------|-------------|
| `gen_cfg_dot(addr)` | Generate CFG as DOT graph string |
| `gen_cfg_dot_file(addr, path)` | Write CFG DOT to file |
| `gen_schema_dot()` | Generate database schema as DOT |

```sql
SELECT gen_cfg_dot(0x401000);
SELECT gen_schema_dot();
```

---

## Entity Search (grep)

Canonical workflow guidance lives in `../grep/SKILL.md`.

| Surface | Description |
|---------|-------------|
| `grep` table | Structured rows for composable SQL search |
| `grep(pattern, limit, offset)` | JSON array for quick agent/tool output |

```sql
SELECT name, kind, address FROM grep WHERE pattern = 'sub%' LIMIT 10;
SELECT grep('sub%', 10, 0);
SELECT grep('init');  -- defaults: limit 50, offset 0
```

---

## String List Functions

| Function | Description |
|----------|-------------|
| `rebuild_strings()` | Rebuild with ASCII + UTF-16, minlen 5 (default) |
| `rebuild_strings(minlen)` | Rebuild with custom minimum length |
| `rebuild_strings(minlen, types)` | Rebuild with custom length and type mask |
| `string_count()` | Get current string count (no rebuild) |

Type mask: `1`=ASCII, `2`=UTF-16, `4`=UTF-32, `3`=ASCII+UTF-16 (default), `7`=all.

```sql
SELECT string_count();
SELECT rebuild_strings();
SELECT rebuild_strings(4);
SELECT rebuild_strings(5, 7);
```

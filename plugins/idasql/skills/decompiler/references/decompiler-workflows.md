# Decompiler Workflows Reference

## Runtime Capability Profile (Do This First)

Do **not** start with broad `pragma_*` discovery unless debugging the tool itself.
Start with documented surfaces and probe availability directly:

1. Baseline decompiler surface:
```sql
SELECT decompile(0x401000);
```

2. Baseline mutation surfaces (must exist in all supported plugin runtimes):
```sql
SELECT set_name(0x401000, 'my_func');
SELECT rename_lvar(0x401000, 0, 'arg0');
SELECT set_lvar_comment(0x401000, 0, 'seed comment');
```

3. Advanced expression/representation helpers (optional in older/minimal runtimes):
```sql
SELECT call_arg_item(0x401000, 0x401020, 0);
SELECT ctree_item_at(0x401000, 0x401030, 'cot_asg', 0);
SELECT set_union_selection_ea_expr(0x401000, 0x401030, '', 'cot_asg', 0);
SELECT set_numform_ea_expr(0x401000, 0x401030, 0, 'clear', 'cot_asg', 0);
```

If any call returns `no such function`, treat that primitive as unavailable in this runtime and switch to fallback workflows below.

## Mandatory Mutation Loop

> Follow the read -> edit -> refresh -> verify cycle defined in `connect` Global Agent Contracts.

For multi-step decompiler cleanup, use this phase order:
1. Apply structural typing first: `parse_decls`, prototypes, `ctree_lvars.type`, global types.
2. Inspect `ctree_v_indirect_calls` for unresolved indirect call sites.
3. Apply `apply_callee_type(call_ea, decl)` only where function/local typing is still insufficient.
4. Refresh once with `decompile(func_addr, 1)` so the typed ctree/lvars are current.
5. Apply rename/label/union-selection/numform/comment cleanup against the refreshed rows.
6. Refresh and verify again.

## Call-Site Typing Workflow

Use call-site typing when a specific indirect call still decompiles poorly after function/global typing and `ctree_lvars.type` updates.

```sql
-- 1. Find candidate indirect calls
SELECT call_ea, target_op, target_var_name, arg_count
FROM ctree_v_indirect_calls
WHERE func_addr = 0x140001BD0
ORDER BY call_ea;

-- 2. Apply an explicit prototype at one call site
SELECT apply_callee_type(
  0x140001C3E,
  'int __fastcall emit_message(const char *name, const char *target, int flag, const char *tag);'
);

-- 3. Verify persisted call metadata
SELECT callee_type_at(0x140001C3E);
SELECT call_arg_addrs(0x140001C3E);

-- 4. Refresh once after semantic typing
SELECT decompile(0x140001BD0, 1);
```

`apply_callee_type` is a semantic typing surface. It is different from render-only helpers like `set_union_selection*` and `set_numform*`.

## Local Type Seeding (Works Even In Minimal Runtimes)

When advanced numform/union helpers are unavailable, aggressively improve pseudocode via local type seeding:

```sql
-- Change local/arg type and optional comment
UPDATE ctree_lvars
SET type = 'unsigned __int64',
    comment = 'my comment here'
WHERE func_addr = 0x401000 AND idx = 18;

-- Refresh and verify effect in pseudocode
SELECT decompile(0x401000, 1);
SELECT idx, name, type, comment
FROM ctree_lvars
WHERE func_addr = 0x401000 AND idx = 18;
```

Use this to reduce noisy casts and surface meaningful field access when paired with function prototype/type improvements.

## Fallback Path (When Advanced Helpers Are Missing)

If `set_union_selection*` / `set_numform*` / `ctree_item_at` are unavailable:

- Use `UPDATE funcs SET prototype = ...` for function-level typing.
- Use `UPDATE ctree_lvars SET type/comment = ...` for local shaping.
- Prefer `rename_lvar*` for local names, even in fallback flows.
- Use `UPDATE pseudocode SET comment = ...` for stable semantic breadcrumbs.
- Keep constants readable via comments when enum rendering primitives are unavailable.
- Explicitly note unavailable primitives in your response so follow-up runs don't waste queries.

## Full Decompiler Examples

```sql
-- Decompile a function (PREFERRED way to view pseudocode)
SELECT decompile(0x401000);

-- After modifying comments or variables, re-decompile to see changes
SELECT decompile(0x401000, 1);

-- Get all local variables in a function
SELECT list_lvars(0x401000);

-- Rename by index (canonical, deterministic)
SELECT rename_lvar(0x401000, 2, 'buffer_size');

-- Rename by current name (convenience; fails if ambiguous)
SELECT rename_lvar_by_name(0x401000, 'v2', 'buffer_size');

-- If you discovered the target via stack slot or another query, resolve idx first
SELECT rename_lvar(
  0x401000,
  (SELECT idx
   FROM ctree_lvars
   WHERE func_addr = 0x401000 AND stkoff = 32
   ORDER BY idx
   LIMIT 1),
  'ctx');

-- Set local-variable comment by index
SELECT set_lvar_comment(0x401000, 2, 'points to decrypted buffer');

-- Simple current-row UPDATE path for rename
-- Prefer rename_lvar* for split/array locals or scripted cleanup
UPDATE ctree_lvars SET name = 'buffer_size'
WHERE func_addr = 0x401000 AND idx = 2;

-- Equivalent UPDATE path for comments
UPDATE ctree_lvars SET comment = 'points to decrypted buffer'
WHERE func_addr = 0x401000 AND idx = 2;

-- Fallback when direct UPDATE comment write fails on a specific lvar
-- (some runtimes can return "SQL logic error" for particular slots):
SELECT set_lvar_comment(0x401000, 2, 'points to decrypted buffer');

-- Mandatory verification loop after rename
SELECT list_lvars(0x401000);
SELECT decompile(0x401000, 1);

-- Import declarations + apply prototype to improve decompilation quality
SELECT parse_decls('
#pragma pack(push, 1)
typedef struct _iobuf FILE;
typedef enum operations_e { op_empty=0, op_open=11, op_read=22, op_close=1, op_seek=2, op_read4=3 } operations_e;
typedef struct open_t { const char* filename; const char* mode; FILE** fp; } open_t;
typedef struct close_t { FILE* fp; } close_t;
typedef struct read_t { FILE* fp; void* buf; unsigned __int64 size; } read_t;
typedef struct seek_t { FILE* fp; __int64 offset; int whence; } seek_t;
typedef struct read4_t { FILE* fp; __int64 seek; int val; } read4_t;
typedef struct command_t { operations_e cmd_id; union { open_t open; read_t read; read4_t read4; seek_t seek; close_t close; } ops; unsigned __int64 ret; } command_t;
#pragma pack(pop)
');
UPDATE funcs
SET name = 'exec_command',
    prototype = 'void __fastcall exec_command(command_t *cmd);'
WHERE address = 0x140001BD0;
SELECT decompile(0x140001BD0, 1);

-- Hybrid call-arg targeting (recommended): line 0x140001C3E has multiple casted args.
-- Callee is optional. If used, pass exact name from ctree_call_args
-- (for imports this is commonly "__imp_fread", not "fread").
SELECT set_union_selection_ea_arg(0x140001BD0, 0x140001C3E, 0, '[1]');
SELECT get_union_selection_ea_arg(0x140001BD0, 0x140001C3E, 0);

-- If helper returns ambiguity/no-match, resolve explicitly:
SELECT call_item_id, arg_idx, arg_item_id, call_ea AS ea,
       COALESCE(NULLIF(call_obj_name,''), call_helper_name, '') AS callee
FROM ctree_call_args
WHERE func_addr = 0x140001BD0 AND call_ea = 0x140001C3E AND arg_idx = 0
ORDER BY call_item_id, arg_idx;

-- Fallback with explicit item id:
SELECT set_union_selection_item(0x140001BD0, 42, '[1]');

-- Inspect persisted path
SELECT get_union_selection_item(0x140001BD0, 42);

-- Clear selection
SELECT set_union_selection_item(0x140001BD0, 42, '');

-- Optional bridge when you want hybrid lookup + explicit item workflow:
SELECT call_arg_item(0x140001BD0, 0x140001C3E, 0);

-- Assignment-side stores often need generic expression targeting.
-- This is the right fix when a wrong union arm creates casts or temp locals.
SELECT ctree_item_at(0x140001BD0, 0x140001C49, 'cot_asg', 0);
SELECT set_union_selection_ea_expr(0x140001BD0, 0x140001C49, '[0]', 'cot_asg', 0);
SELECT set_numform_ea_expr(0x140001BD0, 0x140001C49, 0, 'clear', 'cot_asg', 0);

-- Non-call expression workflow (e.g., comparisons/ifs):
-- 1) resolve expression item deterministically by ea + op_name + nth
SELECT ctree_item_at(0x140001BD0, 0x140001CBB, 'cot_eq', 0);
-- 2) apply/read via generic expression helpers
SELECT set_numform_ea_expr(0x140001BD0, 0x140001CBB, 0, 'enum:operations_e', 'cot_eq', 0);
SELECT get_numform_ea_expr(0x140001BD0, 0x140001CBB, 0, 'cot_eq', 0);
SELECT set_numform_ea_expr(0x140001BD0, 0x140001CBB, 0, 'clear', 'cot_eq', 0);

-- Assignment-style expression (not a call): target with cot_asg
SELECT ctree_item_at(0x140001BD0, 0x140001C49, 'cot_asg', 0);
SELECT set_union_selection_ea_expr(0x140001BD0, 0x140001C49, '', 'cot_asg', 0);
```

`rename_lvar*` functions return JSON with explicit fields:
- `success` (execution success)
- `applied` (observable rename applied)
- `reason` (for non-applied cases: `not_found`, `ambiguous_name`, `unchanged`, `not_nameable`, ...)

`rename_label` returns the same `success`/`applied`/`reason` contract with label-specific fields (`label_num`, `before_name`, `after_name`).

## Persistence and Lifecycle Semantics

Writes are visible immediately within the current process, but they are not flushed to the IDB file until an explicit save path is used.

**CLI mode (`idasql.exe`):**
- Session opens one database, serves queries, then closes on exit.
- HTTP `POST /shutdown` cleanly stops the server and closes the session.
- Temporary unpacked IDA side files (`.id0/.id1/.id2/.nam/.til`) may appear while the DB is open and are expected to be removed on clean close.
- Changes are not persisted by default unless you call `save_database()` or run with `-w/--write`.

**Plugin mode (`idasql_plugin`):**
- Plugin stays alive for the IDA database/plugin lifetime.
- HTTP/MCP servers are stopped on plugin teardown/unload.
- Plugin unload is the lifecycle boundary for final cleanup.

**To persist changes explicitly:**
```sql
SELECT save_database();
```

`save_database()` can be costly. Prefer batching writes and saving once at an intentional boundary.

**CLI flag for save-on-exit:**
```bash
idasql -s db.i64 -q "UPDATE funcs SET name='main' WHERE address=0x401000" -w
```

**Best practice for batch operations:**
```sql
UPDATE funcs SET name = 'init_config' WHERE address = 0x401000;
UPDATE names SET name = 'g_settings' WHERE address = 0x402000;
SELECT save_database();
```

> Agent rule: never assume writes are persisted unless `save_database()` or `-w` is explicitly used.

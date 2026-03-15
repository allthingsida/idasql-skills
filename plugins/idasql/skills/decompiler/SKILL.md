---
name: decompiler
description: "Decompile IDA functions: pseudocode, ctree AST, local variables, labels."
---

> For detailed ctree node types and manipulation patterns, see: `references/ctree-manipulation.md`

---

## Trigger Intents

Use this skill when user asks for:
- "decompile this function"
- pseudocode understanding or AST-level analysis
- local variable semantics in decompiled form
- decompiler-centric pattern mining (returns/calls/conditions)

Route to:
- `annotations` for persistent comments/renames after interpretation
- `types` for struct/enum/type construction and application
- `disassembly` when decompiler is unavailable or insufficient

---

## Do This First (Warm-Start Sequence)

```sql
-- 1) Capability/profile probe
SELECT * FROM pragma_table_list WHERE name IN ('pseudocode', 'ctree', 'ctree_lvars');

-- 2) Pick one concrete function target
SELECT name, printf('0x%X', address) AS addr, size
FROM funcs
ORDER BY size DESC
LIMIT 10;

-- 3) View decompiled text via primary read surface
SELECT decompile(0x401000);
```

Interpretation guidance:
- `decompile(addr)` is primary display surface.
- `pseudocode`/`ctree*` are structured query/edit surfaces.

---

## Global Constraint Reminder (Critical)

Always constrain decompiler tables by function:

```sql
WHERE func_addr = 0x...
```

Without this, decompiler tables may decompile every function and become extremely slow.

---

## Failure and Recovery

- No Hex-Rays/decompiler tables unavailable:
  - Fall back to `disassembly` + `xrefs` workflows.
- Empty/partial rows:
  - Confirm target `func_addr` exists and refresh decompile cache (`decompile(addr, 1)` where supported).
- Mutation did not appear:
  - Run mandatory mutation loop (read -> edit -> refresh -> verify).

---

## Handoff Patterns

1. `decompiler` -> `types` for local type seeding and richer declarations.
2. `decompiler` -> `annotations` for persistent narrative and naming.
3. `decompiler` -> `disassembly` for opcode-level validation.

---

## Decompiler Tables (Hex-Rays Required)

**CRITICAL:** Always filter by `func_addr`. Without constraint, these tables will decompile EVERY function - extremely slow!

### pseudocode
The `pseudocode` table is a structured line-by-line pseudocode with writable comments. **Use `decompile(addr)` to view pseudocode; use this table only for surgical edits (comments) or structured queries.**

| Column | Type | Writable | Description |
|--------|------|----------|-------------|
| `func_addr` | INT | No | Function address |
| `line_num` | INT | No | Line number |
| `line` | TEXT | No | Pseudocode text |
| `ea` | INT | No | Corresponding assembly address (from COLOR_ADDR anchor) |
| `comment` | TEXT | **Yes** | Decompiler comment at this ea |
| `comment_placement` | TEXT | **Yes** | Comment placement: `semi` (inline, default), `block1` (above line) |

Filter behavior:
- `WHERE func_addr = X`: best performance; iterates pseudocode for one function only.
- `WHERE ea = X`: decompiles only the containing function and returns matching lines for that EA.
- `WHERE line_num = N`: scans functions and returns rows at that line index; use only when you need cross-function line alignment.

**Comment placements:** `semi` (after `;`), `block1` (own line above), `block2`, `curly1`, `curly2`, `colon`, `case`, `else`, `do`

```sql
-- VIEWING: Use decompile() function, NOT the pseudocode table
SELECT decompile(0x401000);

-- COMMENTING: Use pseudocode table to add/edit/delete comments
-- The example UPDATEs below assume 0x401020 is an already resolved writable
-- non-brace anchor. Do not substitute func_addr or the first displayed row.
-- Add inline comment (appears after semicolon)
UPDATE pseudocode SET comment_placement = 'semi',
                      comment = 'buffer overflow here'
WHERE func_addr = 0x401000 AND ea = 0x401020;

-- Add block comment (appears on own line above the statement)
UPDATE pseudocode SET comment_placement = 'block1', comment = 'vulnerable call'
WHERE func_addr = 0x401000 AND ea = 0x401020;

-- Delete comments at a resolved unique anchor
-- Warning: comment = NULL currently clears all placements at that ea.
UPDATE pseudocode SET comment = NULL
WHERE func_addr = 0x401000 AND ea = 0x401020;

-- STRUCTURED QUERY: Get specific lines with ea and comment info
SELECT ea, line, comment FROM pseudocode WHERE func_addr = 0x401000;
```

### pseudocode_orphan_comments
The `pseudocode_orphan_comments` table exposes persisted Hex-Rays comments that no longer attach to the current decompiled output. Use it to inspect or delete stale comments without guessing at UI state.

| Column | Type | Writable | Description |
|--------|------|----------|-------------|
| `func_addr` | INT | No | Function address |
| `func_name` | TEXT | No | Current function name for triage |
| `ea` | INT | No | Stored orphan comment EA |
| `comment_placement` | TEXT | No | Stored `treeloc_t.itp` placement |
| `orphan_comment` | TEXT | **Delete-only** | Stored orphan comment text |

Rules:
- One row = one orphaned stored comment.
- `UPDATE ... SET orphan_comment = NULL` or `''` deletes that orphan comment.
- Any non-empty write is rejected.
- Always filter by `func_addr` when investigating one function.

```sql
-- Inspect precise orphan comment rows for one function
SELECT ea, comment_placement, orphan_comment
FROM pseudocode_orphan_comments
WHERE func_addr = 0x401000
ORDER BY ea, comment_placement;

-- Delete one orphan comment exactly
UPDATE pseudocode_orphan_comments
SET orphan_comment = NULL
WHERE func_addr = 0x401000
  AND ea = 0x401020
  AND comment_placement = 'semi';
```

### pseudocode_v_orphan_comment_groups
`pseudocode_v_orphan_comment_groups` is the grouped, read-only orphan triage surface. It returns one row per function with orphan comments and supports a native `func_addr` fast path.

Columns:
- `func_addr`
- `func_name`
- `orphan_count`
- `orphan_comments_json`

Rules:
- Start with `LIMIT` for cross-database triage.
- Prefer `WHERE func_addr = ...` once you have picked a function.
- Use this surface for review; use `pseudocode_orphan_comments` for exact deletion.

```sql
SELECT func_addr, func_name, orphan_count
FROM pseudocode_v_orphan_comment_groups
ORDER BY orphan_count DESC
LIMIT 20;

SELECT orphan_count, orphan_comments_json
FROM pseudocode_v_orphan_comment_groups
WHERE func_addr = 0x401000;
```

### Comment Anchor Resolution (Critical)

Use this recipe before writing heading-style or function-summary comments.

Rules:
- Do not assume `ea == func_addr`.
- The first displayed pseudocode row often has `ea = 0` and is not the right write target.
- One `ea` can map to multiple rows (`{`, statement, `}`); prefer a unique non-brace anchor.
- Use `line_num` only to inspect candidate rows. Persisted writes are keyed by `treeloc_t { ea, comment_placement }`; shared-`ea` rows need extra care, so do not assume every displayed shared-`ea` row is independently writable.
- `annotations` owns the broader cleanup workflow; this section owns the anchor-selection rule.
- This anchor is the canonical target for top-of-function semantic summaries used in later search and whole-program understanding.

```sql
-- Inspect candidate rows first
SELECT line_num, ea, line, comment
FROM pseudocode
WHERE func_addr = 0x401000
ORDER BY line_num;

-- Resolve the first attachable non-brace row near function start
SELECT line_num, ea, line
FROM pseudocode
WHERE func_addr = 0x401000
  AND ea != 0
  AND TRIM(line) NOT IN ('{', '}')
  AND ea IN (
    SELECT ea
    FROM pseudocode
    WHERE func_addr = 0x401000 AND ea != 0
    GROUP BY ea
    HAVING COUNT(*) = 1
  )
ORDER BY line_num
LIMIT 1;

-- Write a heading-style summary using the resolved ea
UPDATE pseudocode
SET comment_placement = 'block1',
    comment = 'One-paragraph summary of the function.'
WHERE func_addr = 0x401000
  AND ea = (
    SELECT ea
    FROM pseudocode
    WHERE func_addr = 0x401000
      AND ea != 0
      AND TRIM(line) NOT IN ('{', '}')
      AND ea IN (
        SELECT ea
        FROM pseudocode
        WHERE func_addr = 0x401000 AND ea != 0
        GROUP BY ea
        HAVING COUNT(*) = 1
      )
    ORDER BY line_num
    LIMIT 1
  );
```

### ctree
Full Abstract Syntax Tree of decompiled code.

| Column | Type | Description |
|--------|------|-------------|
| `func_addr` | INT | Function address |
| `item_id` | INT | Unique node ID |
| `is_expr` | INT | 1=expression, 0=statement |
| `op_name` | TEXT | Node type (`cot_call`, `cit_if`, etc.) |
| `ea` | INT | Address in binary |
| `parent_id` | INT | Parent node ID |
| `depth` | INT | Tree depth |
| `x_id`, `y_id`, `z_id` | INT | Child node IDs |
| `var_idx` | INT | Local variable index |
| `var_name` | TEXT | Variable name |
| `obj_ea` | INT | Target address |
| `obj_name` | TEXT | Symbol name |
| `num_value` | INT | Numeric literal |
| `label_num` | INT | Label number when node defines a label |
| `goto_label_num` | INT | Target label number for `cit_goto` nodes |
| `str_value` | TEXT | String literal |

### ctree_lvars
Local variables from decompilation.

| Column | Type | Description |
|--------|------|-------------|
| `func_addr` | INT | Function address |
| `idx` | INT | Variable index |
| `name` | TEXT | Variable name |
| `type` | TEXT | Type string |
| `comment` | TEXT | Local-variable comment shown next to declaration |
| `size` | INT | Size in bytes |
| `is_arg` | INT | 1=function argument |
| `is_stk_var` | INT | 1=stack variable |
| `stkoff` | INT | Stack offset |

Mutation guidance:
- Prefer `idx`-based updates for deterministic writes.
- `name` can be empty for internal/non-display temps; treat those as potentially non-nameable.
- `comment` updates map to Hex-Rays local-variable comments (`lv.cmt`) and appear in `decompile(...)` output.

### ctree_labels
Decompiler control-flow labels. Supports UPDATE (`name`) and mirrors label facilities on `cfunc_t`.

| Column | Type | RW | Description |
|--------|------|----|-------------|
| `func_addr` | INT | R | Function address |
| `label_num` | INT | R | Label number (`LABEL_<n>`) |
| `name` | TEXT | RW | Current label name |
| `item_id` | INT | R | Backing ctree item id for this label |
| `item_ea` | INT | R | Address of label-bearing ctree item |
| `is_user_defined` | INT | R | 1 if name differs from default `LABEL_<n>` |

Mutation guidance:
- Treat label identity as `(func_addr, label_num)`, not by name.
- Prefer `rename_label(...)` when you need explicit JSON result fields (`success`, `applied`, `reason`).
- Use `UPDATE ctree_labels SET name=...` for SQL-native batch workflows.

```sql
-- Inspect labels in one function
SELECT label_num, name, item_id, printf('0x%X', item_ea) AS item_ea
FROM ctree_labels
WHERE func_addr = 0x401000
ORDER BY label_num;

-- Inspect label metadata directly on ctree nodes
SELECT item_id, op_name, label_num, goto_label_num
FROM ctree
WHERE func_addr = 0x401000
  AND (label_num >= 0 OR goto_label_num >= 0)
ORDER BY item_id;
```

```sql
-- No-op label rename probe (safe: preserves current name)
WITH first_label AS (
    SELECT func_addr, label_num, name
    FROM ctree_labels
    ORDER BY func_addr, label_num
    LIMIT 1
)
SELECT rename_label(func_addr, label_num, name) AS result_json
FROM first_label;

-- Equivalent no-op UPDATE path via writable table
UPDATE ctree_labels
SET name = name
WHERE rowid IN (
    SELECT rowid
    FROM ctree_labels
    ORDER BY func_addr, label_num
    LIMIT 1
);
```

### ctree_call_args
Flattened call arguments for easy querying.

| Column | Type | Description |
|--------|------|-------------|
| `func_addr` | INT | Function address |
| `call_item_id` | INT | Call node ID |
| `call_ea` | INT | Call-site EA used by hybrid ea+arg helpers |
| `call_obj_name` | TEXT | Callee object name when call target is `cot_obj` |
| `call_helper_name` | TEXT | Callee helper name when call target is `cot_helper` |
| `arg_idx` | INT | Argument index (0-based) |
| `arg_item_id` | INT | Argument expression item ID (`ctree.item_id`) |
| `arg_op` | TEXT | Argument type |
| `arg_var_name` | TEXT | Variable name if applicable |
| `arg_var_is_stk` | INT | 1=stack variable |
| `arg_num_value` | INT | Numeric value |
| `arg_str_value` | TEXT | String value |

---

## Decompiler Views

Pre-built views for common patterns:

| View | Purpose |
|------|---------|
| `ctree_v_calls` | Function calls with callee info |
| `ctree_v_indirect_calls` | Indirect/dynamic call sites that benefit from call-site typing |
| `pseudocode_v_orphan_comment_groups` | One row per function with grouped orphan comment JSON; filter by `func_addr` after triage |
| `ctree_v_loops` | for/while/do loops |
| `ctree_v_ifs` | if statements |
| `ctree_v_comparisons` | Comparisons with operands |
| `ctree_v_assignments` | Assignments with operands |
| `ctree_v_derefs` | Pointer dereferences |
| `ctree_v_returns` | Return statements with value details |
| `ctree_v_calls_in_loops` | Calls inside loops (recursive) |
| `ctree_v_calls_in_ifs` | Calls inside if branches (recursive) |
| `ctree_v_leaf_funcs` | Functions with no outgoing calls |
| `ctree_v_call_chains` | Call chain paths up to depth 10 |

### ctree_v_indirect_calls

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

### ctree_v_returns

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

---

## Type Tables and Views

For `types`, `types_members`, `types_enum_values`, `types_func_args` schemas, type views, and type CRUD examples, see `types` skill.

---

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

---

## SQL Functions — Decompilation

**When to use `decompile()` vs `pseudocode` table:**
- **Read/show pseudocode** → always start with `SELECT decompile(addr)`. It returns the full function as one text block with per-line prefixes (`/* <ea> */` when available, `/*          */` when no line anchor exists).
- **Local declaration hints** → declaration lines include compact local-variable index hints (`[lv:N]`) so rename operations can target `rename_lvar(func_addr, N, new_name)` safely.
- **Need fresh output after edits** → use `SELECT decompile(addr, 1)` to force re-decompilation.
- **Need structured line access or comment CRUD** → query/update the `pseudocode` table.

| Function | Description |
|----------|-------------|
| `decompile(addr)` | **PREFERRED** — Full pseudocode with line prefixes (`addr` may be EA, numeric string, or symbol name; available when decompiler surfaces are enabled) |
| `decompile(addr, 1)` | Same output but forces re-decompilation (use after writes/renames) |
| `apply_callee_type(call_ea, decl)` | Apply a prototype to one call site |
| `callee_type_at(call_ea)` | Read explicit call-site prototype when present |
| `call_arg_addrs(call_ea)` | Read persisted argument-loader addresses as JSON |
| `list_lvars(addr)` | List local variables as JSON |
| `rename_lvar(func_addr, lvar_idx, new_name)` | Rename a local variable by index |
| `rename_lvar_by_name(func_addr, old_name, new_name)` | Rename a local variable by existing name |
| `rename_label(func_addr, label_num, new_name)` | Rename a decompiler label by label number |
| `set_lvar_comment(func_addr, lvar_idx, text)` | Set local-variable comment by index |
| `set_union_selection(func_addr, ea, path)` | Set/clear union selection path at EA (`[0,1]` or `0,1`) |
| `set_union_selection_item(func_addr, item_id, path)` | Set/clear union selection path by `ctree.item_id` |
| `set_union_selection_ea_arg(func_addr, ea, arg_idx, path[, callee])` | **PREFERRED** call-arg targeting helper; resolves to item id or errors with hint |
| `call_arg_item(func_addr, ea, arg_idx[, callee])` | Resolve call-arg coordinate to explicit `arg_item_id` |
| `ctree_item_at(func_addr, ea[, op_name[, nth]])` | Resolve generic expression coordinate to explicit `ctree.item_id` |
| `set_union_selection_ea_expr(func_addr, ea, path[, op_name[, nth]])` | Set/clear union selection via generic expression coordinate |
| `get_union_selection(func_addr, ea)` | Read union selection path JSON at EA |
| `get_union_selection_item(func_addr, item_id)` | Read union selection path JSON by `ctree.item_id` |
| `get_union_selection_ea_arg(func_addr, ea, arg_idx[, callee])` | Read union selection JSON via call-arg coordinate |
| `get_union_selection_ea_expr(func_addr, ea[, op_name[, nth]])` | Read union selection JSON via generic expression coordinate |
| `set_numform(func_addr, ea, opnum, spec)` | Set/clear numform directly by EA + operand index |
| `get_numform(func_addr, ea, opnum)` | Read numform JSON directly by EA + operand index |
| `set_numform_item(func_addr, item_id, opnum, spec)` | Set/clear numform by explicit ctree item id |
| `get_numform_item(func_addr, item_id, opnum)` | Read numform JSON by explicit ctree item id |
| `set_numform_ea_arg(func_addr, ea, arg_idx, opnum, spec[, callee])` | Set/clear numform via call-arg coordinate |
| `get_numform_ea_arg(func_addr, ea, arg_idx, opnum[, callee])` | Read numform JSON via call-arg coordinate |
| `set_numform_ea_expr(func_addr, ea, opnum, spec[, op_name[, nth]])` | Set/clear numform via generic expression coordinate |
| `get_numform_ea_expr(func_addr, ea, opnum[, op_name[, nth]])` | Read numform JSON via generic expression coordinate |

Targeting guidance:
- Use `*_ea_arg` helpers for repeated callees and call-site arguments.
- Use `ctree_item_at(..., op_name, nth)` plus `*_ea_expr` helpers for non-call expressions and assignment-side struct/union population stores.
- When cleanup succeeds, expect recovered member paths and fewer bad casts/temp locals. Constants may still render as named objects instead of quoted literals.

### Runtime Capability Profile (Do This First)

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

### Mandatory Mutation Loop

> Follow the read → edit → refresh → verify cycle defined in `connect` Global Agent Contracts.

For multi-step decompiler cleanup, use this phase order:
1. Apply structural typing first: `parse_decls`, prototypes, `ctree_lvars.type`, global types.
2. Inspect `ctree_v_indirect_calls` for unresolved indirect call sites.
3. Apply `apply_callee_type(call_ea, decl)` only where function/local typing is still insufficient.
4. Refresh once with `decompile(func_addr, 1)` so the typed ctree/lvars are current.
5. Apply rename/label/union-selection/numform/comment cleanup against the refreshed rows.
6. Refresh and verify again.

### Call-Site Typing Workflow

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

### Local Type Seeding (Works Even In Minimal Runtimes)

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

### Fallback Path (When Advanced Helpers Are Missing)

If `set_union_selection*` / `set_numform*` / `ctree_item_at` are unavailable:

- Use `UPDATE funcs SET prototype = ...` for function-level typing.
- Use `UPDATE ctree_lvars SET type/comment = ...` for local shaping.
- Prefer `rename_lvar*` for local names, even in fallback flows.
- Use `UPDATE pseudocode SET comment = ...` for stable semantic breadcrumbs.
- Keep constants readable via comments when enum rendering primitives are unavailable.
- Explicitly note unavailable primitives in your response so follow-up runs don't waste queries.

### Full Decompiler Examples

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

---

## SQL Functions — Modification

For `set_name()`, `type_at()`, `set_type()`, `parse_decls()` reference, see `types` skill.

Preferred SQL write surface for function metadata:
- `UPDATE funcs SET name = '...', prototype = '...' WHERE address = ...`
- `prototype` maps to `type_at/set_type` behavior and invalidates decompiler cache.

---

## Performance Rules

Understanding table architecture helps you write fast queries:

| Table | Architecture | Key Constraint | Notes |
|-------|-------------|----------------|-------|
| `pseudocode` | Cached | `func_addr` | Lazy per-function cache, freed after query |
| `pseudocode_orphan_comments` | Cached | `func_addr` | Query-scoped orphan rows; writable delete-only |
| `pseudocode_v_orphan_comment_groups` | Cached | `func_addr` | Query-scoped grouped orphan triage; start broad with `LIMIT` |
| `ctree` | Generator | `func_addr` | Lazy streaming, never materializes full result, respects LIMIT |
| `ctree_lvars` | Cached | `func_addr` | Lazy per-function cache, freed after query |
| `ctree_call_args` | Generator | `func_addr` | Lazy streaming, respects LIMIT |

**Critical rules:**
- **ALL decompiler tables require `func_addr` constraint.** Without it, every function is decompiled — this can take minutes on large binaries.
- Generator tables (`ctree`, `ctree_call_args`) stream rows lazily and stop at LIMIT — use `LIMIT` to cap cost.
- Cached tables (`pseudocode`, orphan surfaces, `ctree_lvars`) are query-scoped only here: they build per-query state and do not keep static cross-query row caches.
- Decompiler views (`ctree_v_calls`, `ctree_v_indirect_calls`, `ctree_v_loops`, etc.) inherit the `func_addr` constraint — always filter.
- **Hex-Rays cfunc cache:** `decompile(addr)` is internally cached. `decompile(addr, 1)` forces a full re-decompilation by calling `mark_cfunc_dirty()` first — only use when you need to see effects of a mutation.

**Cost model:**
```
decompile(addr)          → ~50-200ms first call, ~0ms cached
decompile(addr, 1)       → ~50-200ms always (forces re-decompile)
ctree WHERE func_addr=X  → one decompilation + streaming rows
ctree (no constraint)    → N decompilations where N = func_qty()
```

---

## Advanced Decompiler Patterns (CTEs)

### Functions with deeply nested control flow

Find functions with the most ctree depth — indicators of complex logic, state machines, or obfuscation:

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

Find functions where the same-named local variable has different types — sign of inconsistent annotation:

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
-- How different functions call 'CreateFileW' — what patterns emerge?
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

---

## ctree Operation Names

Common Hex-Rays AST node types:

**Expressions (cot_*):**
- `cot_call` - Function call
- `cot_var` - Local variable
- `cot_obj` - Global object/function
- `cot_num` - Numeric constant
- `cot_str` - String literal
- `cot_ptr` - Pointer dereference
- `cot_ref` - Address-of
- `cot_asg` - Assignment
- `cot_add`, `cot_sub`, `cot_mul`, `cot_sdiv`, `cot_udiv` - Arithmetic
- `cot_eq`, `cot_ne`, `cot_lt`, `cot_gt` - Comparisons
- `cot_land`, `cot_lor`, `cot_lnot` - Logical
- `cot_band`, `cot_bor`, `cot_xor` - Bitwise

**Statements (cit_*):**
- `cit_if` - If statement
- `cit_for` - For loop
- `cit_while` - While loop
- `cit_do` - Do-while loop
- `cit_return` - Return statement
- `cit_block` - Code block

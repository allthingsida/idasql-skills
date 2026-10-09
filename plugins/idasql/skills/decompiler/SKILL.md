---
name: decompiler
description: "Decompile and analyze IDA functions. Use when asked for pseudocode, ctree AST analysis, local variables, labels, split expressions, or decompiler-driven cleanup."
metadata:
  argument-hint: "[function-name or address]"
allowed-tools:
  - Bash
  - Read
  - Glob
  - Grep
---

> **Links:** when an answer names functions, addresses, strings or types, make them clickable on IDA 9.4 builds: `[name](uri)` from the `deep_links` table, outside code blocks (skill `deep-links`).

---

## Trigger Intents

Use this skill when user asks for:
- "decompile this function"
- pseudocode understanding or AST-level analysis
- local variable semantics in decompiled form
- decompiler-centric pattern mining (returns/calls/conditions)
- "split expression": a merged `*(_QWORD *)&x = 0x...LL` store printed field by field

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
SELECT name, printf('0x%X', addr) AS addr, size
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
- A `decompiler_splits` write failed:
  - "piece_size must be 1, 2, 4 or 8": give bytes, not IDA's internal size code.
  - "is not the start of an instruction" / "is not in the function at": take `addr` from the
    merged assignment (`ctree.addr` of the `cot_asg`), and `func_addr` from `funcs`.
  - "is already split": `UPDATE decompiler_splits SET piece_size = ...` or `DELETE` it.
  - "unrecognised split state version" / "verified on IDA 9.0-9.4 only": this IDA stores split
    data in a form idasql does not know; use the pseudocode window's Split expression instead.
- A split row exists but the pseudocode did not change: nothing at that `addr` was merged (or
  it already prints in pieces that size); delete the row.

---

## Handoff Patterns

1. `decompiler` -> `types` for local type seeding and richer declarations.
2. `decompiler` -> `annotations` for persistent narrative and naming.
3. `decompiler` -> `disassembly` for opcode-level validation.

---

## Decompiler Tables (Hex-Rays Required)

**CRITICAL:** Always filter by `func_addr`. Without constraint, these tables will decompile EVERY function - extremely slow!

`func_addr` is a function's **entry address** on every decompiler table: an address
inside a function matches no row (as on the disassembly tables), and every row reports
the entry. Rowids are stable per (function, item), so `OR` across functions and
self-joins never drop or merge rows.

### pseudocode
The `pseudocode` table is a structured line-by-line pseudocode with writable comments. **Use `decompile(addr)` to view pseudocode; use this table only for surgical edits (comments) or structured queries.**

| Column | Type | Writable | Description |
|--------|------|----------|-------------|
| `func_addr` | INT | No | Function address |
| `line_num` | INT | No | Line number |
| `line` | TEXT | No | Pseudocode text |
| `addr` | INT | No | Corresponding assembly address (from COLOR_ADDR anchor); NULL for a line with no address (signature, blank or comment-only line) |
| `comment` | TEXT | **Yes** | Decompiler comment at this addr |
| `comment_placement` | TEXT | **Yes** | Comment placement: `semi` (inline, default), `block1` (above line) |

Filter behavior:
- `WHERE func_addr = X`: best performance; iterates pseudocode for one function only.
- `WHERE addr = X`: decompiles only the containing function and returns matching lines for that EA (a line in a tail shared by several functions is listed under each owner).
- `WHERE line_num = N`: scans functions and returns rows at that line index; use only when you need cross-function line alignment.

**Comment placements:** `semi` (after `;`), `block1` (own line above), `block2`, `curly1`, `curly2`, `brace1`, `brace2`, `colon`, `case`, `else`, `do`, `asm`, `try`. An unrecognized placement string is silently coerced to `semi`.

```sql
-- VIEWING: Use decompile() function, NOT the pseudocode table
SELECT decompile(0x401000);

-- COMMENTING: Use pseudocode table to add/edit/delete comments
UPDATE pseudocode SET comment_placement = 'semi',
                      comment = 'buffer overflow here'
WHERE func_addr = 0x401000 AND addr = 0x401020;

-- Add block comment (appears on own line above the statement)
UPDATE pseudocode SET comment_placement = 'block1', comment = 'vulnerable call'
WHERE func_addr = 0x401000 AND addr = 0x401020;

-- Delete comments at a resolved unique anchor
UPDATE pseudocode SET comment = NULL
WHERE func_addr = 0x401000 AND addr = 0x401020;
```

True function comments are not part of `pseudocode`:
- use `UPDATE funcs SET comment = ... WHERE addr = ...` for the regular function comment
- use `UPDATE funcs SET rpt_comment = ... WHERE addr = ...` for the repeatable function comment

### pseudocode_orphan_comments
Persisted Hex-Rays comments that no longer attach to the current decompiled output of a live function. Use it to inspect or delete stale comments.

| Column | Type | Writable | Description |
|--------|------|----------|-------------|
| `func_addr` | INT | No | Function address |
| `func_name` | TEXT | No | Current function name for triage |
| `addr` | INT | No | Stored orphan comment EA |
| `comment_placement` | TEXT | No | Stored `treeloc_t.itp` placement |
| `orphan_comment` | TEXT | **Delete-only** | Stored orphan comment text |

Rules:
- `UPDATE ... SET orphan_comment = NULL` or `''` deletes that orphan comment.
- Any non-empty write is rejected.

### pseudocode_v_orphan_comment_groups
Grouped, read-only orphan triage surface. One row per function with orphan comments.

Columns: `func_addr`, `func_name`, `orphan_count`, `orphan_comments_json`

### Comment Anchor Resolution (Critical)

Use this recipe before writing heading-style decompiler notes.

Rules:
- Do not assume `addr == func_addr`.
- The first displayed pseudocode row (the signature) has `addr` NULL and is not a write target.
- One `addr` can map to multiple rows (`{`, statement, `}`); prefer a unique non-brace anchor.
- For true function comments, update `funcs.comment` / `funcs.rpt_comment` instead of `pseudocode`.

```sql
-- Resolve the first attachable non-brace row near function start
SELECT line_num, addr, line
FROM pseudocode
WHERE func_addr = 0x401000
  AND addr IS NOT NULL
  AND TRIM(line) NOT IN ('{', '}')
  AND addr IN (
    SELECT addr
    FROM pseudocode
    WHERE func_addr = 0x401000 AND addr IS NOT NULL
    GROUP BY addr
    HAVING COUNT(*) = 1
  )
ORDER BY line_num
LIMIT 1;

-- Write a heading-style summary using the resolved addr
UPDATE pseudocode
SET comment_placement = 'block1',
    comment = 'One-paragraph summary of the function.'
WHERE func_addr = 0x401000
  AND addr = (
    SELECT addr
    FROM pseudocode
    WHERE func_addr = 0x401000
      AND addr IS NOT NULL
      AND TRIM(line) NOT IN ('{', '}')
      AND addr IN (
        SELECT addr
        FROM pseudocode
        WHERE func_addr = 0x401000 AND addr IS NOT NULL
        GROUP BY addr
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
| `op` | INT | Raw numeric op code |
| `op_name` | TEXT | Node type (`cot_call`, `cit_if`, etc.) |
| `addr` | INT | Address in binary |
| `parent_id` | INT | Parent node ID |
| `depth` | INT | Tree depth |
| `x_id`, `y_id`, `z_id` | INT | Child node IDs |
| `cond_id` | INT | Condition child ID (if/while/for) |
| `then_id` | INT | Then-branch child ID (if) |
| `else_id` | INT | Else-branch child ID (if) |
| `body_id` | INT | Body child ID (loops) |
| `init_id` | INT | Init child ID (for) |
| `step_id` | INT | Step child ID (for) |
| `var_idx` | INT | Local variable index |
| `obj_addr` | INT | Target address |
| `num_value` | INT | Numeric literal |
| `str_value` | TEXT | String literal |
| `helper_name` | TEXT | Helper function name (`cot_helper`) |
| `member_offset` | INT | Member offset (`cot_memptr`/`cot_memref`) |
| `var_name` | TEXT | Variable name |
| `var_is_stk` | INT | 1=variable is a stack variable |
| `var_is_reg` | INT | 1=variable is a register variable |
| `var_is_arg` | INT | 1=variable is a function argument |
| `obj_name` | TEXT | Symbol name |
| `label_num` | INT | Label number when node defines a label |
| `goto_label_num` | INT | Target label number for `cit_goto` nodes |

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
| `is_result` | INT | 1=holds the function result |
| `is_stk_var` | INT | 1=stack variable |
| `is_reg_var` | INT | 1=register variable |
| `stkoff` | INT | Stack offset |
| `mreg` | INT | Microcode register number (register variables) |

Mutation guidance:
- Prefer `idx`-based updates for deterministic writes.
- `type` accepts scalars, pointers, **and array types** — e.g. `SET type = 'WCHAR[6]'` or `'_BYTE[392]'` for wide stack strings / fixed buffers (the type must fit the local's stack slot).
- `comment` updates map to Hex-Rays local-variable comments (`lv.cmt`) and appear in `decompile(...)` output.
- A `type` UPDATE is read back: when Hex-Rays keeps the old type the UPDATE fails ("Hex-Rays kept ...") and nothing is left changed. The result variable (`is_result = 1`, often unnamed) usually follows the function prototype that way, so change the return type with `UPDATE funcs SET prototype = ...`. Its `comment` is writable.
- A rename can re-order the function's locals (IDA 9.2 does this for register arguments), so the next edit should re-select its `idx` (or address the variable by `mreg` / `stkoff`) rather than reuse an `idx` read before the rename.

### ctree_labels
Decompiler control-flow labels. Supports UPDATE (`name`) and mirrors label facilities on `cfunc_t`.

| Column | Type | RW | Description |
|--------|------|----|-------------|
| `func_addr` | INT | R | Function address |
| `label_num` | INT | R | Label number (`LABEL_<n>`) |
| `name` | TEXT | RW | Current label name |
| `item_id` | INT | R | Backing ctree item id for this label |
| `item_addr` | INT | R | Address of label-bearing ctree item (NULL when the item has none) |
| `is_user_defined` | INT | R | 1 if name differs from default `LABEL_<n>` |

### decompiler_splits
Hex-Rays "Split expression" without a pseudocode window (the window's Split/Unsplit expression;
`vdui_t::split_item` in `hexrays.hpp`). A row keeps the decompiler from merging narrower
operations into one wider one at `addr`, so a struct initialised by one 8-byte store prints
field by field.

| Column | Type | RW | Description |
|--------|------|----|-------------|
| `func_addr` | INT | R | Function entry (optional on INSERT: the function containing `addr`) |
| `addr` | INT | R | The merged instruction: the `addr` of the assignment in `ctree` |
| `piece_size` | INT | RW | Bytes per piece: 1, 2, 4 or 8 |

- `INSERT INTO decompiler_splits(addr, piece_size)` splits; `UPDATE ... SET piece_size` changes
  it; `DELETE` unsplits. The next `decompile(addr)` shows it.
- IDA's own action splits an 8-byte store into 4-byte pieces first, then 2, then 1.
- Saved with the database, stored exactly as IDA's own Split expression stores it (a split made
  in the GUI shows here, and the reverse), and rolled back by `checkpoints`.
- A split where nothing merges changes nothing. Supported on IDA 9.0-9.4; other versions, and
  split data in a form idasql does not recognise, are refused and never rewritten.
- `WHERE func_addr = X` reads one function; a full scan reads every function's stored settings
  without decompiling.

```sql
-- Before: *(_QWORD *)a1 = 0x600000001LL;
SELECT printf('0x%X', addr) AS addr FROM ctree
WHERE func_addr = 0x1400010A0 AND op_name = 'cot_asg';

INSERT INTO decompiler_splits(addr, piece_size) VALUES (0x1400010AA, 4);
SELECT decompile(0x1400010A0);   -- *(_DWORD *)a1 = 1; *((_DWORD *)a1 + 1) = 6;

UPDATE decompiler_splits SET piece_size = 2 WHERE addr = 0x1400010AA;
DELETE FROM decompiler_splits WHERE addr = 0x1400010AA;   -- merged again
SELECT func_addr, addr, piece_size FROM decompiler_splits WHERE func_addr = 0x1400010A0;
```

### ctree_call_args
Flattened call arguments for easy querying.

| Column | Type | Description |
|--------|------|-------------|
| `func_addr` | INT | Function address |
| `call_item_id` | INT | Call node ID |
| `call_addr` | INT | Call-site EA |
| `call_obj_name` | TEXT | Callee object name |
| `call_helper_name` | TEXT | Callee helper name |
| `arg_idx` | INT | Argument index (0-based) |
| `arg_item_id` | INT | Argument expression item ID |
| `arg_op` | TEXT | Argument type |
| `arg_var_idx` | INT | Local variable index when the argument is a variable |
| `arg_var_name` | TEXT | Variable name if applicable |
| `arg_var_is_stk` | INT | 1=argument variable is a stack variable |
| `arg_var_is_arg` | INT | 1=argument variable is itself a function argument |
| `arg_obj_addr` | INT | Object address when the argument is a global object |
| `arg_obj_name` | TEXT | Object name when the argument is a global object |
| `arg_num_value` | INT | Numeric value |
| `arg_str_value` | TEXT | String value |

### microcode

Hex-Rays **microcode** — the low-level 3-operand IR one layer *below* the ctree
(assembly → **microcode** → ctree → pseudocode), lifted at `MMAT_LVARS` by default
(lvar-aware, SSA-like). `ctree` is the AST; `microcode` is the register-transfer IR under
it. **Always filter by `func_addr`** — each query runs one `gen_microcode` per function
(~3 ms), so an unfiltered scan decompiles the whole program. The value must be
the exact function start; an interior EA matches no rows. Read-only.

A function Hex-Rays cannot lift has **no rows** on every path, so a join or an `IN`
list over many functions keeps going past it. `SELECT microcode_error(func_addr)`
(or `microcode_error(func_addr, 'generated')` for a rung) gives the reason, NULL when
it lifts.

| Column | Type | Description |
|--------|------|-------------|
| `func_addr` | INT | Containing function |
| `block_num` | INT | Microcode basic-block serial |
| `seq` | INT | Instruction index within the function |
| `addr` | INT | Source EA (NULL for a synthetic micro-instruction) |
| `opcode` | INT | Raw `mcode_t` opcode value |
| `canonical_op` | TEXT | Cross-tool canonical P-code-style op (`INT_ADD`, `CALL`, `LOAD`, …); empty when the mcode has no clean canonical |
| `maturity` | TEXT | Returned Hex-Rays lifting rung (`generated`…`lvars`; see below) |
| `stage` | TEXT | Coarse cross-tool ordinal; idasql microcode emits `raw`\|`optimized`\|`final` (it is SSA-like, never the explicit-`ssa` stage other tools use) |
| `text` | TEXT | Full rendered micro-instruction (e.g. `sub ecx2.4{1}, #1.4, ecx3.4{2}`) |
| `l_text` | TEXT | Rendered left operand (empty when void) |
| `r_text` | TEXT | Rendered right operand (empty when void) |
| `d_text` | TEXT | Rendered destination operand (empty when void) |

```sql
-- The microcode of one function, in order
SELECT block_num, seq, opcode, canonical_op, text
FROM microcode WHERE func_addr = 0x401000 ORDER BY seq;

-- Call micro-instructions (m_call = 0x38 / m_icall) in a function
SELECT seq, text FROM microcode
WHERE func_addr = 0x401000 AND text LIKE 'call%';
```

##### Maturity control (`WHERE maturity=…`)

By default `microcode` is lifted at `MMAT_LVARS` (`stage='final'`). Add
`AND maturity='<rung>'` to **re-lift the same function at a lower rung** — raw
pre-optimization microcode (`generated`) has ~9× more ops than the optimized `lvars` form.
The ladder (8 rungs), returned by `ir_maturities`:

| `maturity` | `stage` | `ordinal` | `is_default` |
|---|---|---|---|
| `generated` | `raw` | 0 | 0 |
| `preoptimized` | `optimized` | 1 | 0 |
| `locopt` | `optimized` | 2 | 0 |
| `calls` | `optimized` | 3 | 0 |
| `glbopt1` | `optimized` | 4 | 0 |
| `glbopt2` | `optimized` | 5 | 0 |
| `glbopt3` | `optimized` | 6 | 0 |
| `lvars` | `final` | 7 | 1 |

`maturity` is a **passthrough** filter: it pushes down to the generator and through
`ir_ops`. `=`, `IN`, `LIKE`, `<`, `<=`, `>` and `>=` each lift exactly the rungs whose
**name** satisfies the predicate (names compare as text, as in SQL: for ladder order,
pick the names from `ir_maturities` by `ordinal`). For `<>` or `NOT ...`, list the
wanted rungs with `IN`: those operators reach the table only as the default rung.
A requested rung returns rows only when Hex-Rays produces that exact rung; if Hex-Rays coerces the request, no non-matching rows
leak through. Without a maturity constraint, rows report the rung Hex-Rays
actually returned.

```sql
-- Raw pre-optimization microcode of one function (many more ops than the default)
SELECT seq, opcode, canonical_op, text
FROM microcode WHERE func_addr = 0x401000 AND maturity = 'generated' ORDER BY seq;

-- Discover the available lifting ladder
SELECT maturity, stage, ordinal, is_default, is_ssa FROM ir_maturities ORDER BY ordinal;
```

#### microcode_operands (5-kind operand model)

Structured operand rows — one per non-void `minsn_t` `l`/`r`/`d` slot. The five
portable value kinds are `reg`, `imm`, `mem`, `var`, and `result`; native
structural operands such as block/case references are retained with an empty
`kind`. Join back to `microcode` on `op_seq = seq`. Same
`func_addr`/`maturity` pushdown. Read-only.

| Column | Type | Description |
|--------|------|-------------|
| `func_addr` | INT | Containing function |
| `op_seq` | INT | The owning micro-instruction's `seq` (joins `microcode.seq`) |
| `operand_index` | INT | Slot order within the instruction |
| `role` | TEXT | `in` (`l`/`r`) or `out` (`d`) |
| `kind` | TEXT | `reg` \| `imm` \| `mem` \| `var` \| `result` (empty for structural operands) |
| `text` | TEXT | Rendered operand |
| `value` | INT | Immediate value (NULL unless an `imm`) |
| `size` | INT | Operand size in bytes |
| `maturity` / `stage` | TEXT | Same as `microcode` |

```sql
-- Immediate operands consumed in a function
SELECT op_seq, operand_index, value, text
FROM microcode_operands
WHERE func_addr = 0x401000 AND kind = 'imm' AND role = 'in' ORDER BY op_seq;
```

#### Cross-tool low-IR: `ir_ops` / `ir_v_*` / `ir_operands` / `ir_maturities` views

`ir_ops` is the **canonical low-IR projection** over `microcode`: `func_addr`, `seq`,
`addr`, `op` (canonical P-code-style op — `INT_ADD`, `CALL`, `LOAD`, …, or NULL where the
mcode has no clean canonical), `native_op` (the native microcode mnemonic), `is_ssa`
(0 — MMAT_LVARS microcode is SSA-like but not explicit SSA), the passthrough
**`maturity`** filter, and the returned **`stage`** classification. `stage` is
not a lifting selector: use `maturity` to request a rung, then use `stage` only
to classify/filter returned rows. The same `ir_ops` shape holds on every family
tool, so portable SQL can compare IR across engines.

The `ir_v_*` **semantic views** preserve the portable four-column schema and
classify the default-maturity op stream (`func_addr`, `seq`, `addr`, `op`):
`ir_v_calls`, `ir_v_mem_writes`, `ir_v_mem_reads`, `ir_v_branches`, `ir_v_arith`.
**`ir_operands`** is the portable projection of `microcode_operands` (`func_addr`,
`op_seq`, `operand_index`, `role`, `kind`, `text`, `value`, `size`). Its portable
eight-column schema has no maturity coordinate, so it is fixed to the default
`lvars` rung. Join it only to default-maturity `ir_ops` on
`func_addr` + `op_seq = seq`. **`ir_maturities`** advertises the lifting ladder.

```sql
-- Canonical op stream for one function
SELECT seq, op, native_op FROM ir_ops WHERE func_addr = 0x401000 ORDER BY seq;

-- Memory writes performed by a function (engine-agnostic)
SELECT seq, addr FROM ir_v_mem_writes WHERE func_addr = 0x401000 ORDER BY seq;

-- Each op with its operands (engine-agnostic)
SELECT o.seq, o.op, p.role, p.kind, p.text
FROM ir_ops o JOIN ir_operands p ON p.func_addr = o.func_addr AND p.op_seq = o.seq
WHERE o.func_addr = 0x401000 AND o.maturity = 'lvars'
ORDER BY o.seq, p.operand_index;

-- A non-default rung is IDASQL-native: constrain both native surfaces and
-- include maturity in the join because portable ir_operands has no such column.
SELECT o.seq, o.canonical_op, p.role, NULLIF(p.kind, '') AS kind, p.text
FROM microcode o JOIN microcode_operands p
  ON p.func_addr = o.func_addr AND p.op_seq = o.seq AND p.maturity = o.maturity
WHERE o.func_addr = 0x401000
  AND o.maturity = 'generated' AND p.maturity = 'generated'
ORDER BY o.seq, p.operand_index;
```

Always scope `ir_ops`/`ir_v_*`/`ir_operands` by an exact function-start
`func_addr`; it pushes down to the microcode generator. `maturity` pushes down
through `ir_ops`, but the four-column `ir_v_*` views and eight-column
`ir_operands` intentionally expose only the default rung.

---

## Decompiler Views

Pre-built views for common patterns (always filter by `func_addr`):

| View | Purpose |
|------|---------|
| `ctree_v_calls` | Function calls with callee info |
| `ctree_v_indirect_calls` | Indirect/dynamic call sites for call-site typing |
| `ctree_v_loops` | for/while/do loops |
| `ctree_v_ifs` | if statements |
| `ctree_v_comparisons` | Comparisons with operands |
| `ctree_v_signed_ops` | Signed comparison/arithmetic operations |
| `ctree_v_assignments` | Assignments with operands |
| `ctree_v_derefs` | Pointer dereferences |
| `ctree_v_returns` | Return statements with value details |
| `ctree_v_calls_in_loops` | Calls inside loops (recursive) |
| `ctree_v_calls_in_ifs` | Calls inside if branches (recursive) |
| `ctree_v_leaf_funcs` | Functions with no outgoing calls |
| `ctree_v_call_chains` | Call chain paths up to depth 10 |

---

## Type Tables and Views

For `types`, `types_members`, `types_enum_values`, `types_func_args` schemas, type views, and type CRUD examples, see `types` skill.

---

## SQL Functions — Decompilation

**When to use `decompile()` vs `pseudocode` table:**
- **Read/show pseudocode** -> always start with `SELECT decompile(addr)`. Returns full function as one text block with per-line prefixes.
- **Local declaration hints** -> declaration lines include compact local-variable index hints (`[lv:N]`) so rename operations can target `UPDATE ctree_lvars ... WHERE func_addr = ... AND idx = N` safely.
- **Need fresh output after edits** -> use `SELECT decompile(addr, 1)` to force re-decompilation.
- **Need structured line access or comment CRUD** -> query/update the `pseudocode` table.

| Function | Description |
|----------|-------------|
| `decompile(addr)` | **PREFERRED** -- Full pseudocode with line prefixes |
| `decompile(addr, 1)` | Same output but forces re-decompilation |
| `call_arg_addrs(call_addr)` | Read persisted argument-loader addresses as JSON |
| `set_union_selection(func_addr, addr, path)` | Set/clear union selection path at EA |
| `set_union_selection_item(func_addr, item_id, path)` | Set/clear union selection path by `ctree.item_id` |
| `set_union_selection_addr_arg(func_addr, addr, arg_idx, path[, callee])` | **PREFERRED** call-arg targeting helper |
| `call_arg_item(func_addr, addr, arg_idx[, callee])` | Resolve call-arg coordinate to explicit `arg_item_id` |
| `ctree_item_at(func_addr, addr[, op_name[, nth]])` | Resolve generic expression coordinate to explicit `ctree.item_id` |
| `set_union_selection_addr_expr(func_addr, addr, path[, op_name[, nth]])` | Set/clear union selection via generic expression coordinate |
| `get_union_selection(func_addr, addr)` | Read union selection path JSON at EA |
| `get_union_selection_item(func_addr, item_id)` | Read union selection path JSON by `ctree.item_id` |
| `get_union_selection_addr_arg(func_addr, addr, arg_idx[, callee])` | Read union selection JSON via call-arg coordinate |
| `get_union_selection_addr_expr(func_addr, addr[, op_name[, nth]])` | Read union selection JSON via generic expression coordinate |
| `set_numform(func_addr, addr, opnum, spec)` | Set/clear numform directly by EA + operand index |
| `get_numform(func_addr, addr, opnum)` | Read numform JSON directly by EA + operand index |
| `set_numform_item(func_addr, item_id, opnum, spec)` | Set/clear numform by explicit ctree item id |
| `get_numform_item(func_addr, item_id, opnum)` | Read numform JSON by explicit ctree item id |
| `set_numform_addr_arg(func_addr, addr, arg_idx, opnum, spec[, callee])` | Set/clear numform via call-arg coordinate |
| `get_numform_addr_arg(func_addr, addr, arg_idx, opnum[, callee])` | Read numform JSON via call-arg coordinate |
| `set_numform_addr_expr(func_addr, addr, opnum, spec[, op_name[, nth]])` | Set/clear numform via generic expression coordinate |
| `get_numform_addr_expr(func_addr, addr, opnum[, op_name[, nth]])` | Read numform JSON via generic expression coordinate |

Targeting guidance:
- Use `*_addr_arg` helpers for repeated callees and call-site arguments.
- Use `ctree_item_at(..., op_name, nth)` plus `*_addr_expr` helpers for non-call expressions and assignment-side struct/union population stores.

---

## SQL Functions — Modification

For `applied_types`, `parse_decls()`, and name writes via `names`/`funcs`, see `types` skill.

Preferred SQL write surface for function metadata:
- `UPDATE funcs SET name = '...', prototype = '...', comment = '...', rpt_comment = '...' WHERE addr = ...`
- `prototype` maps to `applied_types` behavior and invalidates decompiler cache.
- `comment` / `rpt_comment` map to `get_func_cmt()` / `set_func_cmt()`.

---

## Performance Rules

| Table | Architecture | Key Constraint | Notes |
|-------|-------------|----------------|-------|
| `pseudocode` | Cached | `func_addr` | Lazy per-function cache, freed after query |
| `pseudocode_orphan_comments` | Cached | `func_addr` | Query-scoped orphan rows; writable delete-only |
| `pseudocode_v_orphan_comment_groups` | Cached | `func_addr` | Query-scoped grouped orphan triage; start broad with `LIMIT` |
| `ctree` | Generator | `func_addr` | Lazy streaming, never materializes full result, respects LIMIT |
| `ctree_lvars` | Cached | `func_addr` | Lazy per-function cache, freed after query |
| `ctree_call_args` | Generator | `func_addr` | Lazy streaming, respects LIMIT |
| `decompiler_splits` | Cached | `func_addr` | Stored settings only, no decompilation; a full scan is cheap |

**Critical rules:**
- **ALL decompiler tables require `func_addr` constraint.** Without it, every function is decompiled.
- Generator tables (`ctree`, `ctree_call_args`) stream rows lazily and stop at LIMIT.
- Decompiler views (`ctree_v_calls`, `ctree_v_indirect_calls`, `ctree_v_loops`, etc.) inherit the `func_addr` constraint -- always filter.
- **Hex-Rays cfunc cache:** `decompile(addr)` is internally cached. `decompile(addr, 1)` forces a full re-decompilation -- only use when you need to see effects of a mutation.

**Cost model:**
```
decompile(addr)          -> ~50-200ms first call, ~0ms cached
decompile(addr, 1)       -> ~50-200ms always (forces re-decompile)
ctree WHERE func_addr=X  -> one decompilation + streaming rows
ctree (no constraint)    -> one decompilation per row in funcs
```

---

## Additional Resources

- For detailed workflows (capability probing, mutation loop, call-site typing, local type seeding, fallback patterns, full worked examples): [references/decompiler-workflows.md](references/decompiler-workflows.md)
- For detailed view schemas (ctree_v_indirect_calls, ctree_v_returns): [references/decompiler-views.md](references/decompiler-views.md)
- For ctree node types, manipulation patterns, and advanced CTEs: [references/ctree-manipulation.md](references/ctree-manipulation.md)

---

## See Also

- `data` — raw bytes and string content referenced by decompiled code (the `bytes` table for per-byte reads and bounded-window reads via `WHERE start_addr = X AND n = N`; `hex(blob_concat(value))` for hex output).
- `disassembly` — instruction-level ground truth for the same function (`disasm_func`, `instructions`, `disasm_calls`).
- `xrefs` — callers and callees of a decompiled function; pivot from pseudocode to call graph.
- `types` — applied prototypes drive ctree shape; retype via `applied_types` / `funcs.prototype` to clean up casts and indirect calls.

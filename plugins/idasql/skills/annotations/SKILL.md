---
name: annotations
description: "Edit IDA databases. Use when asked to add comments, rename symbols, apply types, create bookmarks, or clean up decompiled code for review."
allowed-tools:
  - Bash
  - Read
  - Glob
  - Grep
---

This skill is your guide for **editing** IDA databases through idasql. Use it whenever you need to annotate, rename, retype, comment, or otherwise modify decompiled output, disassembly, or type information. Every edit operation follows the Mandatory Mutation Loop (see `connect` Global Agent Contracts).

---

## Trigger Intents

Use this skill when user asks to:
- add/edit comments (pseudocode, disassembly, function summaries)
- rename symbols or local variables
- apply types/enums/struct representations
- create/update bookmarks for investigation workflow
- make pseudocode read more like source
- prepare decompiled code for side-by-side review against source
- annotate a function end-to-end, not just add one comment

Route to:
- `decompiler` for analysis before editing
- `types` when declarations or struct models need construction
- `re-source` for recursive narrative/source recovery passes

---

## Do This First (Warm-Start Sequence)

```sql
-- 1) Confirm target row/function before editing
SELECT * FROM funcs WHERE address = 0x401000;

-- 2) Inspect current comment state
SELECT ea, line, comment
FROM pseudocode
WHERE func_addr = 0x401000
LIMIT 30;

-- 3) Inspect existing disassembly comments
SELECT * FROM comments WHERE address BETWEEN 0x401000 AND 0x401100;
```

Interpretation guidance:
- Never edit blind: validate exact row identity before mutation.
- Prefer deterministic keys (`func_addr + ea`, `idx`, `slot`) over fuzzy name matches.

---

## Failure and Recovery

- Update appeared to "do nothing":
  - Re-read target row, refresh decompile view, verify placement fields.
- Wrong target mutated:
  - Tighten predicate and re-run read-first step before retry.
- Enum/struct rendering did not change:
  - Confirm type/numform/union-selection support and target context.

---

## Handoff Patterns

1. `annotations` -> `decompiler` when semantic meaning is unclear.
2. `annotations` -> `types` when edits imply missing declarations.
3. `annotations` -> `re-source` when function-level notes must become recursive campaign notes.

---

## Annotate a Function Contract

Treat `annotate this function` as a full-function workflow, not a single comment operation.

Default behavior:
- inspect the current decompilation and local/label state
- apply types/prototypes that make the function read more like source
- rename locals, globals, and labels when they materially improve readability
- add targeted line comments where they help interpretation
- always finish with exactly one repeatable function comment summary on `funcs.rpt_comment`
- refresh with `decompile(addr, 1)` and verify the result

Use narrower intents only when the user asks narrowly:
- `add a comment` -> comment only
- `func-summary` / `function summary` -> summary only
- `annotate this function` -> full cleanup plus summary

Why the summary is mandatory:
- it orients a human reviewer immediately
- it creates semantic/searchable program knowledge for later whole-program understanding

---

## Editing Function Comments

True IDA function comments live on `funcs`, not on `pseudocode` and not on the address-level `comments` table.

Use:
- `funcs.comment` for the regular function comment
- `funcs.rpt_comment` for the repeatable function comment

Default function-summary behavior:
- treat singular `add function comment` as `UPDATE funcs SET rpt_comment = ...`
- use `funcs.comment` only when the user explicitly asks for a non-repeatable function comment
- use a heading-style `pseudocode` block comment only when the user explicitly asks for a decompiler note/summary rather than a true function comment

Canonical SQL pattern:

```sql
SELECT address, name, comment, rpt_comment
FROM funcs
WHERE address = 0x401000;

UPDATE funcs
SET rpt_comment = 'One-paragraph summary of what the function does, inputs/outputs, and key behavior.'
WHERE address = 0x401000;
```

---

## Editing Decompiler Comments (Pseudocode)

The `pseudocode` table is the editing surface for decompiler comments. Use `decompile(addr)` to view; use the table to edit. For full table schema, see `decompiler` skill.

Important separation:
- `pseudocode.comment` edits Hex-Rays decompiler comments only.
- `pseudocode` writes never call `set_func_cmt()`.
- Use `funcs.comment` / `funcs.rpt_comment` for true function comments.

Writable columns: `comment`, `comment_placement`. Placements: `semi` (after `;`), `block1` (own line above), `block2`, `curly1`, `curly2`, `colon`, `case`, `else`, `do`.

Anchor guidance:
- Prefer a concrete pseudocode statement row, not a guessed function-entry row.
- If an `ea` maps to multiple pseudocode rows (`{`, statement, `}`), resolve a unique non-brace anchor first.
- Use `line_num` only to inspect candidate rows. Comment writes persist by `ea + comment_placement`; shared-`ea` rows need extra care, so do not assume every displayed shared-`ea` row is independently writable.

Inspect anchors before writing:

```sql
SELECT line_num, ea, line, comment
FROM pseudocode
WHERE func_addr = 0x401000
ORDER BY line_num;
```

```sql
-- The example UPDATEs below assume 0x401020 is an already resolved writable
-- non-brace anchor from the inspection query above; do not substitute func_addr.
-- Edit: Add inline comment to decompiled code
UPDATE pseudocode SET comment_placement = 'semi',
                      comment = 'buffer overflow here'
WHERE func_addr = 0x401000 AND ea = 0x401020;

-- Edit: Add block comment (own line above statement)
UPDATE pseudocode SET comment_placement = 'block1', comment = 'vulnerable call'
WHERE func_addr = 0x401000 AND ea = 0x401020;

-- Edit: Delete comments at a resolved unique anchor
-- Warning: comment = NULL currently clears all placements at that ea.
UPDATE pseudocode SET comment = NULL
WHERE func_addr = 0x401000 AND ea = 0x401020;

-- Read edited pseudocode with comments
SELECT ea, line, comment FROM pseudocode WHERE func_addr = 0x401000;
```

### Cleaning Up Orphan Decompiler Comments

If the database contains stale decompiler comments that no longer attach to current pseudocode, use the orphan comment surfaces instead of trying to clear them through `pseudocode`.

Read-first pattern:
```sql
SELECT func_addr, func_name, orphan_count
FROM pseudocode_v_orphan_comment_groups
ORDER BY orphan_count DESC
LIMIT 20;

SELECT ea, comment_placement, orphan_comment
FROM pseudocode_orphan_comments
WHERE func_addr = 0x401000
ORDER BY ea, comment_placement;
```

Delete-only mutation pattern:
```sql
UPDATE pseudocode_orphan_comments
SET orphan_comment = NULL
WHERE func_addr = 0x401000
  AND ea = 0x401020
  AND comment_placement = 'semi';
```

Notes:
- `pseudocode_orphan_comments` is delete-only.
- Non-empty writes are rejected.
- Use the grouped surface for triage, then the precise table for cleanup.
- After triage, switch to `WHERE func_addr = ...` on both surfaces for the fast path.

---

## Function Summary (func-summary)

Use `function summary` and `func-summary` as equivalent intent.

Trigger contract:
- If the user says `function summary` or `func-summary`, add or update exactly one repeatable function comment on `funcs.rpt_comment`.
- If the user says `add function comment` (singular) without line-specific targets, treat it as a repeatable function comment update.
- If the user explicitly asks for a decompiler heading note or pseudocode block comment, use `pseudocode.comment` with a resolved writable anchor instead.
- Only add many line comments when the user explicitly asks for line-by-line/deep annotation.

Default behavior:
- Write the summary to `funcs.rpt_comment`.
- Use `funcs.comment` only when the user explicitly asks for a non-repeatable function comment.
- Do not expand into line-by-line annotation unless the user explicitly asks for deep annotation.
- When a function is being fully annotated, always add/update this summary as the last semantic step.

Length guidance:
- Use one paragraph minimum when applicable.
- For trivial wrappers/thunks, a shorter concise summary is acceptable.
- Capture function role, key inputs/outputs, important state changes, and notable side effects when relevant.

Canonical SQL pattern:

```sql
SELECT address, name, comment, rpt_comment
FROM funcs
WHERE address = 0x401000;

UPDATE funcs
SET rpt_comment = 'One-paragraph summary of what the function does, inputs/outputs, and key behavior.'
WHERE address = 0x401000;
```

Prompt examples:
- `function summary 0x401000`
- `func-summary DriverEntry`
- `func-summary this function`

---

## Editing Disassembly Comments

SQL functions for editing disassembly-level comments:

| Function | Description |
|----------|-------------|
| `comment_at(addr)` | Get comment at address |
| `set_comment(addr, text)` | Edit/set regular comment |
| `set_comment(addr, text, 1)` | Edit/set repeatable comment |

The `comments` table supports INSERT, UPDATE, and DELETE:

| Table | INSERT | UPDATE columns | DELETE |
|-------|--------|---------------|--------|
| `comments` | Yes | `comment`, `rpt_comment` | Yes |

Notes:
- `comments` edits address comments via `set_cmt()`.
- `funcs.comment` / `funcs.rpt_comment` edit true function comments via `set_func_cmt()`.

---

## bookmarks

The `bookmarks` table supports full CRUD for editing marked positions:

| Column | Type | Description |
|--------|------|-------------|
| `slot` | INT | Bookmark slot index |
| `address` | INT | Bookmarked address |
| `description` | TEXT | Bookmark description |

```sql
-- List all bookmarks
SELECT printf('0x%X', address) as addr, description FROM bookmarks;

-- Edit: Add bookmark
INSERT INTO bookmarks (address, description) VALUES (0x401000, 'interesting branch');

-- Edit: Update bookmark description
UPDATE bookmarks SET description = 'confirmed branch' WHERE slot = 0;

-- Edit: Delete bookmark
DELETE FROM bookmarks WHERE slot = 0;
```

For canonical schema and owner mapping, see `../connect/references/schema-catalog.md` (`bookmarks`).

---

## Editing Local Variables (Rename, Retype, Comment)

The `ctree_lvars` table is the editing surface for decompiler local variables. Writable columns: `name`, `type`, `comment`. For full table schema, see `decompiler` skill.

Key SQL functions: `rename_lvar(func_addr, lvar_idx, new_name)`, `rename_lvar_by_name(func_addr, old_name, new_name)`, `set_lvar_comment(func_addr, lvar_idx, text)`.

Local-variable edit guidance:
- Prefer `rename_lvar*` for name changes. They are more robust for split locals, array locals, and scripted flows, and they return structured `success`/`applied`/`reason` feedback.
- Use direct `UPDATE ctree_lvars SET type = ...` / `comment = ...` normally.
- Treat direct `UPDATE ctree_lvars SET name = ...` as a simple current-row path after inspection, not the preferred rename primitive.

```sql
-- Inspect current locals before renaming
SELECT idx, name, type, comment
FROM ctree_lvars
WHERE func_addr = 0x401000
ORDER BY idx;

-- Edit: Rename a local variable by index (canonical, deterministic)
SELECT rename_lvar(0x401000, 2, 'buffer_size');

-- Edit: Rename by current name (convenience)
SELECT rename_lvar_by_name(0x401000, 'v2', 'buffer_size');

-- Edit: Set local-variable comment by index
SELECT set_lvar_comment(0x401000, 2, 'points to decrypted buffer');

-- Edit: Change variable type
UPDATE ctree_lvars SET type = 'char *'
WHERE func_addr = 0x401000 AND idx = 2;
```

---

## Editing Decompiler Labels

Read the current labels first, then rename the exact label you observed. Prefer `label_num` identity over guessing from line text.

```sql
-- Inspect labels before renaming
SELECT label_num, name, printf('0x%X', item_ea) AS item_ea
FROM ctree_labels
WHERE func_addr = 0x401000
ORDER BY label_num;

-- Rename deterministically by label number
SELECT rename_label(0x401000, 12, 'fail');

-- Equivalent UPDATE path
UPDATE ctree_labels
SET name = 'fail'
WHERE func_addr = 0x401000 AND label_num = 12;
```

---

## Editing Types (Create, Modify, Apply)

For type creation, member CRUD, enum values, `parse_decls()`, `set_type()`, and `set_name()`, see `types` skill.

Quick apply patterns used in annotation workflows:

```sql
-- Apply type to a function
UPDATE funcs SET prototype = 'void __fastcall exec_command(command_t *cmd);'
WHERE address = 0x140001BD0;

-- Apply via set_type function
SELECT set_type(0x140001BD0, 'void __fastcall exec_command(command_t *cmd);');
```

---

## Editing Operand Representation (Enum/Struct in Disassembly)

The `instructions` table `operand*_format_spec` columns allow editing operand display:

```sql
-- Edit: Apply enum representation to operand 1
UPDATE instructions
SET operand1_format_spec = 'enum:MY_ENUM'
WHERE address = 0x401020;

-- Edit: Apply struct-offset representation
UPDATE instructions
SET operand0_format_spec = 'stroff:MY_STRUCT,delta=0'
WHERE address = 0x401030;

-- Edit: Clear representation back to plain
UPDATE instructions
SET operand1_format_spec = 'clear'
WHERE address = 0x401020;
```

---

## Editing Union Selection in Decompiled Code

For union selection helpers (`set_union_selection*`, `get_union_selection*`), see `decompiler` skill.

---

## Editing Number Format (Enum Rendering in Decompiled Code)

**Recommended:** Retype the variable to an enum type — IDA's decompiler will then automatically render all constants using enum names:

```sql
-- 1. Define the enum type (skip if it already exists)
SELECT parse_decls('typedef enum { DLL_PROCESS_DETACH=0, DLL_PROCESS_ATTACH=1 } fdw_reason_t;');

-- 2. Retype the parameter/variable
UPDATE ctree_lvars SET type = 'fdw_reason_t'
WHERE func_addr = 0x180001050 AND idx = 1;

-- 3. Verify
SELECT decompile(0x180001050, 1);
```

For per-operand numform control (`set_numform*`, `get_numform*`), see `decompiler` skill.

---

## Mandatory Mutation Loop (For All Edits)

> Follow the read -> edit -> refresh -> verify cycle defined in `connect` Global Agent Contracts.

---

## Performance Tips for Batch Editing

When editing many functions or annotations, keep these costs in mind:

- **`decompile(addr, 1)` triggers a full re-decompilation** (~50-200ms per function). When editing multiple items in the same function, batch all edits before the refresh:
  ```sql
  -- Good: structural typing first, then refresh, then naming cleanup
  UPDATE ctree_lvars SET type = 'MY_CTX *' WHERE func_addr = 0x401000 AND idx = 0;
  SELECT decompile(0x401000, 1);
  SELECT rename_lvar(0x401000, 0, 'ctx');
  SELECT rename_lvar(0x401000, 1, 'size');
  SELECT decompile(0x401000, 1);  -- final refresh after cleanup
  ```
- **`pseudocode` comment writes are lightweight** — they persist to IDA's user comments store without triggering re-decompilation. You can write comments to many functions without calling `decompile(addr, 1)` between each.
- **`ctree_lvars` type changes invalidate the decompiler cache** — after changing a variable type, refresh before you trust `idx`/name-based cleanup. The decompiler may split locals or re-render expressions.
- **`save_database()` can be costly** on large databases. Batch all writes and save once at the end of an annotation campaign, not after each edit.

---

## Additional Resources

- For full cleanup workflows, bulk annotation patterns, and complete worked examples: [references/annotation-workflows.md](references/annotation-workflows.md)

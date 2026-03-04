---
name: annotations
description: "Edit IDA databases: comments, renames, types, bookmarks, enum/struct rendering."
---

This skill is your guide for **editing** IDA databases through idasql. Use it whenever you need to annotate, rename, retype, comment, or otherwise modify decompiled output, disassembly, or type information. Every edit operation follows the Mandatory Mutation Loop (see `connect` Global Agent Contracts).

---

## Trigger Intents

Use this skill when user asks to:
- add/edit comments (pseudocode, disassembly, function summaries)
- rename symbols or local variables
- apply types/enums/struct representations
- create/update bookmarks for investigation workflow

Route to:
- `decompiler` for analysis before editing
- `types` when declarations or struct models need construction
- `resource` for recursive narrative/source recovery passes

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
3. `annotations` -> `resource` when function-level notes must become recursive campaign notes.

---

## Editing Decompiler Comments (Pseudocode)

The `pseudocode` table is the editing surface for decompiler comments. Use `decompile(addr)` to view; use the table to edit. For full table schema, see `decompiler` skill.

Writable columns: `comment`, `comment_placement`. Placements: `semi` (after `;`), `block1` (own line above), `block2`, `curly1`, `curly2`, `colon`, `case`, `else`, `do`.

```sql
-- Edit: Add inline comment to decompiled code
UPDATE pseudocode SET comment = 'buffer overflow here'
WHERE func_addr = 0x401000 AND ea = 0x401020;

-- Edit: Add block comment (own line above statement)
UPDATE pseudocode SET comment_placement = 'block1', comment = 'vulnerable call'
WHERE func_addr = 0x401000 AND ea = 0x401020;

-- Edit: Delete a comment
UPDATE pseudocode SET comment = NULL
WHERE func_addr = 0x401000 AND ea = 0x401020;

-- Read edited pseudocode with comments
SELECT ea, line, comment FROM pseudocode WHERE func_addr = 0x401000;
```

---

## Function Summary (func-summary)

Use `function summary` and `func-summary` as equivalent intent.

Trigger contract:
- If the user says `function summary` or `func-summary`, add or update exactly one heading summary at function entry (`ea == func_addr`).
- If the user says `add function comment` (singular) without line-specific targets, treat it as `func-summary`.
- Only add many line comments when the user explicitly asks for line-by-line/deep annotation.

Default behavior:
- Add or update a function-heading summary at the function entry row (`ea == func_addr`).
- Use `comment_placement = 'block1'` so the summary appears as a heading-style block comment.
- Do not expand into line-by-line annotation unless the user explicitly asks for deep annotation.

Length guidance:
- Use one paragraph minimum when applicable.
- For trivial wrappers/thunks, a shorter concise summary is acceptable.

Canonical SQL pattern:

```sql
UPDATE pseudocode
SET comment_placement = 'block1',
    comment = 'One-paragraph summary of what the function does, inputs/outputs, and key behavior.'
WHERE func_addr = 0x401000 AND ea = 0x401000;
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

```sql
-- Edit: Rename a local variable by index (canonical, deterministic)
SELECT rename_lvar(0x401000, 2, 'buffer_size');

-- Edit: Rename by current name (convenience)
SELECT rename_lvar_by_name(0x401000, 'v2', 'buffer_size');

-- Edit: Set local-variable comment by index
SELECT set_lvar_comment(0x401000, 2, 'points to decrypted buffer');

-- Edit: Equivalent UPDATE path for rename
UPDATE ctree_lvars SET name = 'buffer_size'
WHERE func_addr = 0x401000 AND idx = 2;

-- Edit: Change variable type
UPDATE ctree_lvars SET type = 'char *'
WHERE func_addr = 0x401000 AND idx = 2;

-- Edit: Equivalent UPDATE path for comments
UPDATE ctree_lvars SET comment = 'points to decrypted buffer'
WHERE func_addr = 0x401000 AND idx = 2;

-- Fallback when direct UPDATE comment edit fails on a specific lvar:
SELECT set_lvar_comment(0x401000, 2, 'points to decrypted buffer');
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

> Follow the read → edit → refresh → verify cycle defined in `connect` Global Agent Contracts.

---

## Performance Tips for Batch Editing

When editing many functions or annotations, keep these costs in mind:

- **`decompile(addr, 1)` triggers a full re-decompilation** (~50-200ms per function). When editing multiple items in the same function, batch all edits before the refresh:
  ```sql
  -- Good: batch edits, then refresh once
  SELECT rename_lvar(0x401000, 0, 'ctx');
  SELECT rename_lvar(0x401000, 1, 'size');
  UPDATE ctree_lvars SET type = 'MY_CTX *' WHERE func_addr = 0x401000 AND idx = 0;
  SELECT decompile(0x401000, 1);  -- one refresh for all edits
  ```
- **`pseudocode` comment writes are lightweight** — they persist to IDA's user comments store without triggering re-decompilation. You can write comments to many functions without calling `decompile(addr, 1)` between each.
- **`ctree_lvars` type changes invalidate the decompiler cache** — after changing a variable type, always refresh and verify. The decompiler may adjust other variables or expressions based on the new type.
- **`save_database()` can be costly** on large databases. Batch all writes and save once at the end of an annotation campaign, not after each edit.

---

## Bulk Annotation Patterns

### Batch-annotate all callers of a specific API

Add comments to every call site of a security-sensitive function:

```sql
-- Annotate every call to malloc with a reminder comment
UPDATE pseudocode SET comment = 'TODO: verify allocation size'
WHERE ea IN (
    SELECT ea FROM disasm_calls WHERE callee_name LIKE '%malloc%'
)
AND func_addr IN (
    SELECT DISTINCT func_addr FROM disasm_calls WHERE callee_name LIKE '%malloc%'
);
```

### Find and annotate functions with TODO/FIXME markers

Discover existing analyst breadcrumbs and consolidate them:

```sql
-- Find functions with TODO comments already present
SELECT func_at(func_addr) AS func_name,
       printf('0x%X', ea) AS addr,
       comment
FROM pseudocode
WHERE func_addr IN (SELECT address FROM funcs WHERE name NOT LIKE 'sub_%')
  AND comment LIKE '%TODO%' OR comment LIKE '%FIXME%' OR comment LIKE '%HACK%'
ORDER BY func_addr;
```

### Callee-context annotation pattern

Decompile a function, identify all callees, and annotate each with caller context:

```sql
-- Step 1: List callees of the target function
SELECT callee_name, printf('0x%X', callee_addr) AS addr,
       COUNT(*) AS call_count
FROM disasm_calls
WHERE func_addr = 0x401000
GROUP BY callee_addr
ORDER BY call_count DESC;

-- Step 2: For each callee, add a block comment noting who calls it and why
-- (repeat per callee)
UPDATE pseudocode SET comment_placement = 'block1',
       comment = 'Called by init_driver to set up dispatch table'
WHERE func_addr = 0x401050 AND ea = 0x401050;
```

---

## Complete Annotation Editing Workflow

A typical annotation editing session:

```sql
-- 1. View the function
SELECT decompile(0x401000);

-- 2. Edit: Rename local variables to meaningful names
SELECT rename_lvar(0x401000, 0, 'input_buffer');
SELECT rename_lvar(0x401000, 1, 'buffer_length');

-- 3. Edit: Apply types to improve readability
UPDATE ctree_lvars SET type = 'char *'
WHERE func_addr = 0x401000 AND idx = 0;

-- 4. Edit: Add inline comments explaining logic
UPDATE pseudocode SET comment = 'validate input before processing'
WHERE func_addr = 0x401000 AND ea = 0x401010;

-- 5. Edit: Add block comment for function summary
UPDATE pseudocode SET comment_placement = 'block1',
       comment = 'Processes user input buffer and validates length'
WHERE func_addr = 0x401000 AND ea = 0x401000;

-- 6. Verify all edits
SELECT decompile(0x401000, 1);

-- 7. Persist edits
SELECT save_database();
```

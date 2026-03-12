---
name: annotations
description: "Edit IDA databases: comments, renames, types, bookmarks, enum/struct rendering, and source-like decompilation cleanup for review."
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

## Annotate a Function Contract

Treat `annotate this function` as a full-function workflow, not a single comment operation.

Default behavior:
- inspect the current decompilation and local/label state
- apply types/prototypes that make the function read more like source
- rename locals, globals, and labels when they materially improve readability
- add targeted line comments where they help interpretation
- always finish with exactly one heading-style top-of-function summary comment
- refresh with `decompile(addr, 1)` and verify the result

Use narrower intents only when the user asks narrowly:
- `add a comment` -> comment only
- `func-summary` / `function summary` -> summary only
- `annotate this function` -> full cleanup plus summary

Why the summary is mandatory:
- it orients a human reviewer immediately
- it creates semantic/searchable program knowledge for later whole-program understanding

---

## Editing Decompiler Comments (Pseudocode)

The `pseudocode` table is the editing surface for decompiler comments. Use `decompile(addr)` to view; use the table to edit. For full table schema, see `decompiler` skill.

Writable columns: `comment`, `comment_placement`. Placements: `semi` (after `;`), `block1` (own line above), `block2`, `curly1`, `curly2`, `colon`, `case`, `else`, `do`.

Anchor guidance:
- Prefer a concrete pseudocode statement row, not a guessed function-entry row.
- If an `ea` maps to multiple pseudocode rows (`{`, statement, `}`), resolve a unique non-brace anchor first.
- Use `line_num` only to inspect candidate rows. Comment writes persist by `ea + comment_placement`, and shared-`ea` rows are not independently writable.

Inspect anchors before writing:

```sql
SELECT line_num, ea, line, comment
FROM pseudocode
WHERE func_addr = 0x401000
ORDER BY line_num;
```

```sql
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

---

## Function Summary (func-summary)

Use `function summary` and `func-summary` as equivalent intent.

Trigger contract:
- If the user says `function summary` or `func-summary`, add or update exactly one heading summary on a resolved writable pseudocode anchor near function start.
- If the user says `add function comment` (singular) without line-specific targets, treat it as `func-summary`.
- Only add many line comments when the user explicitly asks for line-by-line/deep annotation.

Default behavior:
- Resolve the first non-brace pseudocode statement whose `ea` is unique within the function.
- Use `comment_placement = 'block1'` so the summary appears as a heading-style block comment.
- Use `line_num` only to inspect/select the anchor; the persisted write is keyed by `ea + comment_placement`.
- Do not expand into line-by-line annotation unless the user explicitly asks for deep annotation.
- When a function is being fully annotated, always add/update this summary as the last semantic step.

Length guidance:
- Use one paragraph minimum when applicable.
- For trivial wrappers/thunks, a shorter concise summary is acceptable.
- Capture function role, key inputs/outputs, important state changes, and notable side effects when relevant.

Canonical SQL pattern:

```sql
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

UPDATE pseudocode
SET comment_placement = 'block1',
    comment = 'One-paragraph summary of what the function does, inputs/outputs, and key behavior.'
WHERE func_addr = 0x401000 AND ea = 0x401020;
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

-- Edit: If you located the target by stack slot, resolve idx first and still rename through helper
SELECT rename_lvar(
  0x401000,
  (SELECT idx
   FROM ctree_lvars
   WHERE func_addr = 0x401000 AND stkoff = 32
   ORDER BY idx
   LIMIT 1),
  'ctx');

-- Edit: Set local-variable comment by index
SELECT set_lvar_comment(0x401000, 2, 'points to decrypted buffer');

-- Edit: Simple current-row UPDATE path for rename
-- Prefer rename_lvar* instead for split/array locals or scripted bulk cleanup
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

## High-Fidelity Cleanup Workflow

Use this workflow when the goal is "make the decompilation read like source" or "prepare a function for side-by-side review."

High-fidelity guidance:
- Optimize for readable semantics, not exact source syntax. IDA may still emit forms like `qmemcpy(...)` for struct copies.
- Front-load decls, prototypes, and local/global type changes, then refresh once so the typed ctree/lvars exist before cleanup.
- After that typed refresh, rename what the decompiler currently calls things, then apply labels, union/numform shaping, and comments.
- Prefer `rename_lvar*` for local names; reserve raw `UPDATE ctree_lvars SET name = ...` for simple current-row edits you already inspected.
- Judge success by recovered member paths and fewer casts/temp locals. String constants may still render as named objects like `aRb`, which is fine.
- Treat the heading-style function summary comment as mandatory for a completed annotation pass.

Worked example:

```sql
-- 1. Start from the current decompilation
SELECT decompile(0x14000107E);

-- 2. Import declarations that unlock field access and enums
SELECT parse_decls('
#pragma pack(push, 1)
typedef enum AnnotOpcode { OP_NONE=0, OP_INIT=11, OP_APPLY=22, OP_PATCH=33 } AnnotOpcode;
typedef enum AnnotMode { MODE_ZERO=0, MODE_ALPHA=0x10, MODE_BETA=0x20, MODE_GAMMA=0x30 } AnnotMode;
typedef struct AnnotVec { int x; int y; } AnnotVec;
typedef struct AnnotStats { int count; int limit; } AnnotStats;
typedef union AnnotPayload { unsigned __int64 raw; AnnotVec coords; AnnotStats stats; } AnnotPayload;
typedef struct AnnotRequest { AnnotOpcode opcode; unsigned int flags; const char *label; void *data; unsigned __int64 size; AnnotPayload payload; unsigned __int64 result; } AnnotRequest;
typedef struct AnnotSession { unsigned int state; AnnotMode mode; AnnotPayload current; unsigned __int64 checksum; char scratch[32]; } AnnotSession;
#pragma pack(pop)
');

-- 3. Apply the function prototype and global names/types
UPDATE funcs
SET prototype = 'int __fastcall dispatch_request(AnnotSession *session, AnnotRequest *request);'
WHERE address = 0x14000107E;

SELECT set_name(0x1400050C0, 'g_last_status');
SELECT set_type(0x1400050C0, 'int g_last_status;');
SELECT set_name(0x1400050C8, 'g_trace');
SELECT set_type(0x1400050C8, 'unsigned __int64 g_trace;');

-- 4. Refresh once so typed ctree/lvars reflect the new declarations
SELECT decompile(0x14000107E, 1);

-- 5. Inspect current locals and labels, then rename what exists today
SELECT idx, name, type FROM ctree_lvars WHERE func_addr = 0x14000107E ORDER BY idx;
SELECT label_num, name FROM ctree_labels WHERE func_addr = 0x14000107E ORDER BY label_num;

SELECT rename_lvar_by_name(0x14000107E, 'x', 'status');
SELECT rename_lvar_by_name(0x14000107E, 'request_union_slot_raw', 'payload_value');
UPDATE ctree_lvars SET comment = 'Final status for the current request path.'
WHERE func_addr = 0x14000107E AND name = 'status';

UPDATE ctree_labels SET name = 'fail'
WHERE func_addr = 0x14000107E AND name = 'LABEL_12';
UPDATE ctree_labels SET name = 'done'
WHERE func_addr = 0x14000107E AND name = 'LABEL_13';

-- 6. Add one heading-style summary comment at the first writable anchor
UPDATE pseudocode
SET comment_placement = 'block1',
    comment = 'Apply a request to a session and mirror the result into the globals.'
WHERE func_addr = 0x14000107E
  AND ea = (
    SELECT ea
    FROM pseudocode
    WHERE func_addr = 0x14000107E
      AND ea != 0
      AND TRIM(line) NOT IN ('{', '}')
      AND ea IN (
        SELECT ea
        FROM pseudocode
        WHERE func_addr = 0x14000107E AND ea != 0
        GROUP BY ea
        HAVING COUNT(*) = 1
      )
    ORDER BY line_num
    LIMIT 1
  );

-- 7. Refresh once and verify the final readable form
SELECT decompile(0x14000107E, 1);
```

Expected review markers:
- typed signature and field access
- named globals, locals, and labels
- one heading-style summary comment near function start
- less raw pointer math and fewer generic temp names

---

## Mandatory Mutation Loop (For All Edits)

> Follow the read → edit → refresh → verify cycle defined in `connect` Global Agent Contracts.

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
WHERE func_addr = 0x401050 AND ea = 0x401060;
```

---

## Complete Annotation Editing Workflow

A typical annotation editing session:

```sql
-- 1. View the function
SELECT decompile(0x401000);

-- 2. Inspect current locals and labels before renaming
SELECT idx, name, type FROM ctree_lvars WHERE func_addr = 0x401000 ORDER BY idx;
SELECT label_num, name FROM ctree_labels WHERE func_addr = 0x401000 ORDER BY label_num;

-- 3. Edit: Rename local variables to meaningful names
SELECT rename_lvar(0x401000, 0, 'input_buffer');
SELECT rename_lvar(0x401000, 1, 'buffer_length');

-- 4. Edit: Apply types to improve readability
UPDATE ctree_lvars SET type = 'char *'
WHERE func_addr = 0x401000 AND idx = 0;

-- 5. Inspect pseudocode anchors before writing comments
SELECT line_num, ea, line, comment
FROM pseudocode
WHERE func_addr = 0x401000
ORDER BY line_num;

-- 6. Edit: Add inline comments explaining logic
UPDATE pseudocode SET comment = 'validate input before processing'
WHERE func_addr = 0x401000 AND ea = 0x401010;

-- 7. Edit: Add block comment for function summary
--    First resolve a unique non-brace anchor; do not assume ea == func_addr.
UPDATE pseudocode SET comment_placement = 'block1',
       comment = 'Processes user input buffer and validates length'
WHERE func_addr = 0x401000 AND ea = 0x401020;

-- 8. Verify all edits
SELECT decompile(0x401000, 1);

-- 9. Persist edits
SELECT save_database();
```

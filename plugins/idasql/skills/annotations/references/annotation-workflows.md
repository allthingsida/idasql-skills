# Annotation Workflows Reference

## High-Fidelity Cleanup Workflow

Use this workflow when the goal is "make the decompilation read like source" or "prepare a function for side-by-side review."

High-fidelity guidance:
- Optimize for readable semantics, not exact source syntax. IDA may still emit forms like `qmemcpy(...)` for struct copies.
- Front-load decls, prototypes, and local/global type changes, then refresh once so the typed ctree/lvars exist before cleanup.
- After that typed refresh, rename what the decompiler currently calls things, then apply labels, union/numform shaping, and comments.
- Prefer `rename_lvar*` for local names; reserve raw `UPDATE ctree_lvars SET name = ...` for simple current-row edits you already inspected.
- Judge success by recovered member paths and fewer casts/temp locals. String constants may still render as named objects like `aRb`, which is fine.
- Treat the repeatable function comment summary (`funcs.rpt_comment`) as mandatory for a completed annotation pass.

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

-- 6. Add one repeatable function comment summary
UPDATE funcs
SET rpt_comment = 'Apply a request to a session and mirror the result into the globals.'
WHERE address = 0x14000107E;

-- 7. Refresh once and verify the final readable form
SELECT decompile(0x14000107E, 1);
```

Expected review markers:
- typed signature and field access
- named globals, locals, and labels
- one repeatable function comment summary
- less raw pointer math and fewer generic temp names

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
-- Resolve a writable anchor in the callee first; do not guess from the entry row.
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
--    Example below uses a previously resolved writable anchor from step 5.
UPDATE pseudocode SET comment = 'validate input before processing'
WHERE func_addr = 0x401000 AND ea = 0x401010;

-- 7. Edit: Add repeatable function comment summary
UPDATE funcs
SET rpt_comment = 'Processes user input buffer and validates length'
WHERE address = 0x401000;

-- 8. Verify all edits
SELECT decompile(0x401000, 1);

-- 9. Persist edits
SELECT save_database();
```

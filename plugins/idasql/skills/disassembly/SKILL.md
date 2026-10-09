---
name: disassembly
description: "Query IDA disassembly. Use when asked about functions, segments, instructions, blocks, operands, control flow, raw code structure, or FLIRT signatures (apply / list / which functions are library code)."
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
- Function/segment/instruction inspection
- Call-site or control-flow analysis from disassembly
- Operand formatting and low-level code structure
- Raw byte/instruction-level evidence
- FLIRT signatures: apply one, list what is applied and what it found, tell library code from the program's own

Route to:
- `decompiler` for AST/pseudocode semantics
- `xrefs` for relationship-heavy caller/callee workflows
- `debugger` for patching/breakpoint actions

---

## Do This First (Warm-Start Sequence)

```sql
-- 1) Orientation
SELECT * FROM binary;

-- 2) Segment map
SELECT name, printf('0x%X', start_addr) AS start_addr, printf('0x%X', end_addr) AS end_addr, perm
FROM segments
ORDER BY segments.start_addr;

-- 3) Library code already recognized (FLIRT): skip it in triage
SELECT name, title, matches FROM signatures;
SELECT COUNT(*) AS library_functions FROM funcs WHERE flags & 4;

-- 4) Largest functions (triage anchors)
SELECT name, printf('0x%X', addr) AS addr, size
FROM funcs
ORDER BY size DESC
LIMIT 20;
```

Interpretation guidance:
- Start from executable segments and largest/highly connected functions.
- Use `func_addr` constraints early when querying instruction-heavy surfaces.

---

## Failure and Recovery

- Slow queries on `instructions`/`heads`:
  - Add `WHERE func_addr = X` or tight EA ranges.
- Missing expected symbol names:
  - Apply the matching FLIRT signature (`available_signatures`, then `INSERT INTO signatures`), or pivot to address-based workflows and enrich via `names` updates later.
- `INSERT INTO signatures` refused:
  - "no signature file": pick a name from `available_signatures`, or give the `.sig` path.
  - "is for processor id": the file is another processor's; choose one for this database.
  - "already in the list": read its row in `signatures` instead.
- `DELETE FROM signatures` refused for an applied signature: roll back a checkpoint taken before the INSERT.
- Ambiguous control-flow behavior:
  - Cross-check with `disasm_calls` and then escalate to `decompiler`.

---

## Handoff Patterns

1. `disassembly` -> `xrefs` for relation expansion.
2. `disassembly` -> `decompiler` for semantic interpretation.
3. `disassembly` -> `debugger` for patch/breakpoint execution.

---

## Entity Tables

### funcs
All detected functions in the binary with prototype information.

| Column | Type | Description |
|--------|------|-------------|
| `addr` | INT | Function start (entry) address |
| `name` | TEXT | Function name |
| `size` | INT | Total bytes over **all** chunks (entry chunk + tails) |
| `end_addr` | INT | End of the **entry chunk** only, not of the whole function (see "Non-contiguous functions") |
| `flags` | INT | Function flags |
| `folder_path` | TEXT | RW function folder relative to Function window root; `NULL`/`''` means root |
| `full_path` | TEXT | RO full dirtree path, including function name |
| `chunk_count` | INT | RO number of chunks (1 = contiguous); last column |

**Prototype columns** (populated when type info available):

| Column | Type | Description |
|--------|------|-------------|
| `return_type` | TEXT | Return type string (e.g., "int", "void *") |
| `return_is_ptr` | INT | 1 if return type is pointer |
| `return_is_int` | INT | 1 if return type is exactly int |
| `return_is_integral` | INT | 1 if return type is int-like (int, long, DWORD, BOOL) |
| `return_is_void` | INT | 1 if return type is void |
| `arg_count` | INT | Number of function arguments |
| `calling_conv` | TEXT | Calling convention (cdecl, stdcall, fastcall, etc.) |

```sql
-- 10 largest functions (size counts tail chunks too)
SELECT name, size FROM funcs ORDER BY size DESC LIMIT 10;

-- Non-contiguous functions, most fragmented first
SELECT name, printf('0x%X', addr) AS addr, chunk_count, size
FROM funcs WHERE chunk_count > 1 ORDER BY chunk_count DESC LIMIT 20;

-- Functions starting with "sub_" (auto-named, not analyzed)
SELECT name, printf('0x%X', addr) as addr FROM funcs WHERE name LIKE 'sub_%';

-- Functions returning integers with 3+ arguments
SELECT name, return_type, arg_count FROM funcs
WHERE return_is_integral = 1 AND arg_count >= 3;

-- Functions organized by IDASQL annotation folders
SELECT addr, name, folder_path
FROM funcs
WHERE folder_path LIKE 'idasql/%'
ORDER BY folder_path, name;
```

**Write operations:**
```sql
-- Create a function (a name or prototype IDA refuses fails the whole INSERT;
-- no function is left behind)
INSERT INTO funcs (addr) VALUES (0x401000);

-- Rename a function
UPDATE funcs SET name = 'my_func' WHERE addr = 0x401000;

-- Move a function into an IDA Function window folder
INSERT INTO dirtree_folders(tree, path) VALUES ('funcs', 'idasql/triage/network');
UPDATE funcs SET folder_path = 'idasql/triage/network' WHERE addr = 0x401000;

-- Move it back to root
UPDATE funcs SET folder_path = NULL WHERE addr = 0x401000;

-- Delete a function
DELETE FROM funcs WHERE addr = 0x401000;
```

Folder paths are relative `/` paths. IDASQL rejects `.`/`..`, duplicate separators, backslashes, non-empty folder deletes, and folder renames whose destination already exists.

### segments
Memory segments. Full CRUD: INSERT a region, DELETE it, and UPDATE `start_addr`
(rebase/move), `end_addr` (resize), `name`, `class`, `perm`.

| Column | Type | RW | Description |
|--------|------|----|-------------|
| `start_addr` | INT | RW | Segment start; UPDATE rebases (moves) the segment |
| `end_addr` | INT | RW | Segment end; UPDATE resizes the segment |
| `name` | TEXT | RW | Segment name (.text, .data, etc.) |
| `class` | TEXT | RW | Segment class (CODE, DATA) |
| `perm` | INT | RW | Permissions (R=4, W=2, X=1) |
| `bitness` | INT | R (INSERT) | Addressing: 16, 32 or 64. Read-only after creation |

An INSERT takes the database's addressing (64-bit on a 64-bit database) and a flat
base (selector 0) unless it names a `bitness`. Addresses may be integers, `'0x...'`
text or names. An overlap with an existing segment, a bad `perm` or a bad `bitness`
is refused with the reason; nothing is created.

```sql
-- Find executable segments
SELECT name, printf('0x%X', start_addr) as start FROM segments WHERE perm & 1 = 1;

-- Rename a segment
UPDATE segments SET name = '.mytext' WHERE start_addr = 0x401000;

-- Add a region (e.g. SRAM for a raw firmware image), then rebase it
INSERT INTO segments(start_addr, end_addr, name, class, perm)
  VALUES (0x20000000, 0x20005000, 'SRAM', 'DATA', 6);
UPDATE segments SET start_addr = 0x08000000 WHERE name = '.text';  -- rebase
```

### names
All named locations (functions, labels, data). Supports INSERT, UPDATE, and DELETE.

| Column | Type | RW | Description |
|--------|------|----|-------------|
| `addr` | INT | R | Address |
| `name` | TEXT | RW | Name |
| `folder_path` | TEXT | RW | Name-folder path; `NULL` means root |
| `full_path` | TEXT | R | Full name dirtree path |

```sql
-- Create/set a name
INSERT INTO names (addr, name) VALUES (0x401000, 'my_symbol');

-- Rename
UPDATE names SET name = 'my_symbol_renamed' WHERE addr = 0x401000;

-- Organize globals/labels into IDA name folders
UPDATE names SET folder_path = 'idasql/names/globals' WHERE name LIKE 'g_%';
UPDATE names SET folder_path = NULL WHERE addr = 0x401000;
```

### entries
Entry points / exports (exported symbols, program entry, tls callbacks, etc.).

| Column | Type | Description |
|--------|------|-------------|
| `ordinal` | INT | Export ordinal |
| `addr` | INT | Entry/export address |
| `name` | TEXT | Entry/export name |

---

### signatures (FLIRT)
The database's FLIRT signature list: apply a signature with `INSERT`, read what each one
found, remove a planned one with `DELETE`. A signature names the library functions it
recognizes and flags them as library code (`FUNC_LIB`), so triage can skip them.

| Column | Type | Description |
|--------|------|-------------|
| `idx` | INT | Position in IDA's list (shifts after a DELETE) |
| `name` | TEXT | As IDA stores it: a short name (`vc32rtf`) or an absolute `.sig` path; the INSERT value |
| `title` | TEXT | The library's name (`Microsoft VisualC v7/14 32bit runtime`); NULL when the file is gone |
| `state` | TEXT | `applied`, `current` (being applied) or `planned` |
| `matches` | INT | Library functions the signature recognized |
| `optlibs` | TEXT | Optional libraries string |

- **INSERT INTO signatures(name)** applies the signature and returns once auto-analysis has
  applied it (FLIRT is turned on for it and the database's setting restored). A short name
  is looked up where IDA looks: each IDAUSR directory, `$IDASGN`, then IDA's own `sig`
  folder, all for this database's processor. A path names the file directly.
- **Refused, with the reason, nothing changed:** NULL or empty name; no such file; a file
  that is not a FLIRT signature; another processor's signature (read from its header);
  already in the list (in any spelling: `vc32rtf`, `vc32rtf.sig`, the same path).
- **DELETE** removes a `planned` entry. An `applied` one is refused: IDA cannot unapply a
  signature and records nothing of what it changed. Take a checkpoint before applying and
  roll back with it (the `annotations` skill, `checkpoints`):

```sql
-- What is applied, and what each signature found
SELECT name, title, state, matches FROM signatures;

-- Apply one (short name or path), then see what it named
INSERT INTO signatures(name) VALUES ('vc32rtf');
SELECT name, printf('0x%X', addr) AS addr FROM funcs WHERE flags & 4;
```

```sql
-- Undo an application: checkpoint first, roll back if the result is not wanted
INSERT INTO checkpoints(label) VALUES ('before vc32rtf');
INSERT INTO signatures(name) VALUES ('vc32rtf');
UPDATE checkpoints SET state = 'undone' WHERE label = 'before vc32rtf';
```

### available_signatures
The `.sig` files IDA would find for this database's processor, in IDA's search order (the
first file of a name wins). Read-only; it makes `INSERT INTO signatures` discoverable.

| Column | Type | Description |
|--------|------|-------------|
| `name` | TEXT | File name without `.sig`: what INSERT takes |
| `title` | TEXT | The library's name |
| `path` | TEXT | Full path |
| `source` | TEXT | `idausr`, `idasgn` or `idadir` (IDA's own folder) |
| `is_startup` | INT | 1 for a startup signature (IDA uses those to pick runtime libraries; not for INSERT) |
| `modules` | INT | Library modules in the file |
| `in_list` | INT | 1 when it is already in `signatures` |

```sql
-- Which runtime libraries could apply here?
SELECT name, title, modules FROM available_signatures
WHERE NOT is_startup AND name LIKE 'vc32%' AND title LIKE 'Microsoft VisualC%' ORDER BY name;

-- Apply every one that matches, in one statement
INSERT INTO signatures(name)
SELECT name FROM available_signatures WHERE name LIKE 'vc32%' AND title LIKE 'Microsoft VisualC%' AND NOT in_list AND NOT is_startup;
```

---

## Instruction Tables

### instructions

`instructions` is the disassembly table. For scalar disassembly text at a specific EA, use `disasm_at(addr[, context])`.
Use `disasm_func()` or `disasm_range()` when you explicitly need a function/range listing.
Decoded instructions support DELETE (converts instruction to unexplored bytes) and operand representation updates via `operand*_format_spec`.
An instruction that other code still flows into (the one before it falls through, or a jump lands on it) is re-created by auto-analysis right after it is undefined; such a DELETE fails with "re-created by auto-analysis" instead of reporting a deleted row. Delete the whole range or function in one statement (the instructions are undefined in address order), or undefine the function first.

`WHERE func_addr = X` is the fast path (function-item iterator). `X` must be the
exact function start; an interior EA matches no rows. Without the filter, the
table scans all code heads.

| Column | Type | Description |
|--------|------|-------------|
| `addr` | INT | Instruction address |
| `func_addr` | INT | Containing function (one row per owner for a shared tail; NULL for code outside every function) |
| `itype` | INT | Instruction type (architecture-specific) |
| `mnemonic` | TEXT | Instruction mnemonic |
| `size` | INT | Instruction size |
| `operand0..operand7` | TEXT | Operand text (`0..7`) |
| `disasm` | TEXT | Full disassembly line |
| `operand0_class..operand7_class` | TEXT | Operand class: `reg`, `imm`, `displ`, `mem`, ... |
| `operand0_repr_kind..operand7_repr_kind` | TEXT | Current representation: `plain`, `hex`, `dec`, `oct`, `bin`, `char`, `float`, `enum`, `offset`, `stroff`, `sizeof`, `segment`, `stkvar`, `forced` |
| `operand0_repr_type_name..operand7_repr_type_name` | TEXT | Enum/stroff/sizeof type, offset base (hex), or forced text |
| `operand0_format_spec..operand7_format_spec` | TEXT (RW) | Apply/clear representation for a specific operand (see vocabulary below) |

```sql
-- Instruction profile of a function (FAST)
SELECT mnemonic, COUNT(*) as count
FROM instructions WHERE func_addr = 0x401330
GROUP BY mnemonic ORDER BY count DESC;

-- Find all call instructions in a function
SELECT addr, disasm FROM instructions
WHERE func_addr = 0x401000 AND mnemonic = 'call';

-- Apply enum representation to operand 1
UPDATE instructions
SET operand1_format_spec = 'enum:MY_ENUM'
WHERE addr = 0x401020;

-- Apply struct-offset representation to operand 0
-- e.g. makes `[rax+10h]` display as `[rax+command_t.field_name]`
UPDATE instructions
SET operand0_format_spec = 'stroff:command_t'
WHERE addr = 0x140001BE8;

-- Struct-offset with a base delta (subtracted before member resolution)
UPDATE instructions
SET operand0_format_spec = 'stroff:command_t,delta=16'
WHERE addr = 0x140001BE8;

-- Nested member path: separate type names with '/'
UPDATE instructions
SET operand0_format_spec = 'stroff:outer_t/inner_t'
WHERE addr = 0x140001BE8;

-- Clear representation back to plain
UPDATE instructions
SET operand1_format_spec = 'clear'
WHERE addr = 0x401020;
```

The format-spec is verified after apply: the UPDATE re-reads the operand and
fails (as a SQL error) if the resulting `repr_kind`, type path, or delta don't
match what was requested. Read back `operandN_repr_kind` /
`operandN_repr_type_name` to confirm.

**Full `operandN_format_spec` vocabulary** (all disassembly-level, no IDAPython
needed):

| Spec | Effect |
|---|---|
| `hex` `dec` `oct` `bin` | number base (radix) |
| `char` | character constant |
| `float` | floating-point |
| `offset` | plain offset, base 0 |
| `offset:<base>` | offset with a user-defined base (`<base>` = symbol name or address) |
| `enum:<NAME>[,serial=N]` / `enum:<NAME>::<MEMBER>` | enum constant |
| `stroff:<Type[/Nested...]>[,delta=N]` | struct-member offset |
| `sizeof:<STRUCT>` | struct-size constant — renders `size STRUCT` |
| `segment` | segment selector |
| `stkvar` | stack variable (operand must be a stack reference) |
| `forced:<text>` | forced (manual) operand text, e.g. `forced:5 shl 3` |
| `clear` / `plain` / `none` | revert to default representation |

Combinable modifiers (suffix on any base, or standalone to modify the current
representation): `,signed` / `,unsigned` (toggle negative display) and
`,bnot` / `,nobnot` (toggle bitwise-not display). Example: `dec,signed`,
`hex,bnot`, or just `signed`.

```sql
-- Number base, character, and sign/bitwise-not modifiers
UPDATE instructions SET operand1_format_spec = 'hex'        WHERE addr = 0x401020;
UPDATE instructions SET operand1_format_spec = 'dec,signed' WHERE addr = 0x401020;
UPDATE instructions SET operand1_format_spec = 'char'       WHERE addr = 0x401020;

-- Offsets (plain and user-defined base)
UPDATE instructions SET operand1_format_spec = 'offset'            WHERE addr = 0x401020;
UPDATE instructions SET operand1_format_spec = 'offset:tbl_start'  WHERE addr = 0x401020;

-- sizeof: an immediate equal to sizeof(STRUCT) renders as `size STRUCT`
UPDATE instructions SET operand1_format_spec = 'sizeof:FILEDEF' WHERE addr = 0x4015EB;

-- Forced operand text
UPDATE instructions SET operand1_format_spec = 'forced:5 shl 3' WHERE addr = 0x401020;
```

### instruction_operands
One row per decoded non-void operand. Use this table for operand type/value details and for joinable replacements of old operand/decode helper functions.

| Column | Type | Description |
|--------|------|-------------|
| `addr` | INT | Instruction address |
| `func_addr` | INT | Containing function (NULL outside every function) |
| `operand_index` | INT | Operand index (canonical; was `opnum`) |
| `text` | TEXT | Operand text |
| `type_code` | INT | IDA operand type code |
| `type_name` | TEXT | Operand type name (`reg`, `imm`, `near`, ...) |
| `dtype` | INT | Operand dtype |
| `reg` | INT | Register number when applicable |
| `op_addr` | INT | Referenced address/displacement when applicable |
| `raw_value` | INT | Raw operand value |
| `value` | INT | Best-effort scalar operand value |

> **Note (addr vs op_addr):** `addr` is the **instruction** address; the operand's
> **referenced** address is `op_addr`. If you want the target an operand points at
> (e.g. a jump/call/data reference), select `op_addr` — `addr` identifies the
> instruction the operand belongs to, not what it references.

```sql
SELECT operand_index, text, type_name, value
FROM instruction_operands
WHERE addr = 0x401000
ORDER BY operand_index;

SELECT i.addr, i.itype, i.mnemonic, o.operand_index, o.text, o.type_name, o.value
FROM instructions i
LEFT JOIN instruction_operands o
  ON o.addr = i.addr AND o.func_addr = 0x401000
WHERE i.func_addr = 0x401000
ORDER BY i.addr, o.operand_index;
```

**Performance:** `WHERE addr = X` decodes one instruction; `WHERE func_addr = X`
uses O(function_size) iteration and requires the exact function start. Without
one of these constraints, it scans the entire database.

### disasm_calls
The call instructions of functions, with resolved targets and optional call-site
prototype overrides. A call outside every function has no row (a call in a tail shared
by several functions is one row per owner).

| Column | Type | Description |
|--------|------|-------------|
| `func_addr` | INT | Function containing the call |
| `addr` | INT | Call instruction address |
| `callee_addr` | INT | Target address (0 if unknown) |
| `callee_name` | TEXT | Target name |
| `callee_type` | TEXT | RW nullable call-site prototype; `UPDATE` applies/replaces, `NULL` or empty clears |

```sql
-- Functions that call malloc
SELECT DISTINCT (SELECT name FROM funcs WHERE addr = func_addr) as caller
FROM disasm_calls WHERE callee_name LIKE '%malloc%';

-- Apply/replace a call-site prototype, then clear it
UPDATE disasm_calls
SET callee_type = 'int (*)(const char *path)'
WHERE addr = 0x401234;
UPDATE disasm_calls SET callee_type = NULL WHERE addr = 0x401234;
```

Applying `callee_type` on a **direct** call preserves the real callee symbol, so
re-decompiling the caller afterward is safe (no microcode `INTERR`); on an indirect
call it types that site. Empty/`NULL` clears the override.

The prototype must fit the arguments the call passes. IDA refuses one that does not, and
the error names the address: `IDA refused callee_type '...' at 0x...: the prototype must
fit the arguments this call passes`. A 32-bit `__fastcall` prototype whose arguments all
go in registers, at a call that pushes one, is such a case. Leave the calling convention
out unless the callee really uses another one. A declaration IDA cannot parse fails with
`callee_type is not a function prototype IDA can parse`.

---

## blocks
Basic blocks within functions. **Use `func_addr` constraint for performance.**

| Column | Type | Description |
|--------|------|-------------|
| `func_addr` | INT | Containing function |
| `start_addr` | INT | Block start |
| `end_addr` | INT | Block end |
| `size` | INT | Block size |

```sql
-- Blocks in a specific function (FAST - uses constraint pushdown)
SELECT * FROM blocks WHERE func_addr = 0x401000;

-- Functions with most basic blocks
SELECT (SELECT name FROM funcs WHERE addr = func_addr) as name, COUNT(*) as blocks
FROM blocks GROUP BY func_addr ORDER BY blocks DESC LIMIT 10;
```

### cfg_edges

Control flow graph edges between basic blocks. **Always use
`WHERE func_addr = X`** with the exact function start (filter_eq pushdown,
O(blocks in function)); an interior EA matches no rows.

| Column | Type | Description |
|--------|------|-------------|
| `func_addr` | INT | Containing function |
| `from_addr` | INT | Source block address |
| `to_addr` | INT | Target block address |
| `edge_type` | TEXT | `true`: the arm taken when the branch condition holds (the jump target); `false`: the fall-through; `normal`: a single successor, a switch dispatch, or a two-way block with no fall-through arm |

```sql
-- Get CFG structure
SELECT * FROM cfg_edges WHERE func_addr = 0x401000;

-- Find branch points (conditional blocks)
SELECT from_addr, COUNT(*) as succ_count
FROM cfg_edges WHERE func_addr = 0x401000
GROUP BY from_addr HAVING succ_count > 1;

-- Find merge points (blocks with multiple predecessors)
SELECT to_addr, COUNT(*) as pred_count
FROM cfg_edges WHERE func_addr = 0x401000
GROUP BY to_addr HAVING pred_count > 1;

-- Branch-site ranking (for a ready-made per-function ranking: func_summary)
SELECT f.name, f.size,
       (SELECT COUNT(*)
        FROM (
            SELECT ce.from_addr
            FROM cfg_edges ce
            WHERE ce.func_addr = f.addr
            GROUP BY ce.from_addr
            HAVING COUNT(*) > 1
        ) branch_blocks) as branch_sites,
       (SELECT COUNT(*) FROM disasm_loops dl WHERE dl.func_addr = f.addr) as loops,
       (SELECT COUNT(*) FROM disasm_calls dc WHERE dc.func_addr = f.addr) as calls_made
FROM funcs f
WHERE f.size > 32
ORDER BY branch_sites DESC
LIMIT 20;
```

### switch_tables

Reconstructed switch/case jump tables (via IDA's `get_switch_info`). Canonical
cross-tool schema, aligned with ghidrasql. Filter by an exact function-start
`func_addr` (filter_eq pushdown).

| Column | Type | Description |
|--------|------|-------------|
| `func_addr` | INT | Containing function |
| `instr_addr` | INT | The indirect-jump (switch) instruction |
| `table_addr` | INT or NULL | Jump-table start address, or NULL when no standard table address is available |
| `min_case` | INT or NULL | Lowest recovered case label, or NULL when labels cannot be recovered |
| `max_case` | INT or NULL | Highest recovered case label, including for sparse/non-contiguous switches |
| `case_count` | INT | Number of non-default case labels |
| `default_addr` | INT or NULL | Default-case target, or NULL when there is no default |

```sql
-- Switches in a function
SELECT * FROM switch_tables WHERE func_addr = 0x401000;

-- Large switches across the whole program
SELECT func_addr, instr_addr, case_count
FROM switch_tables ORDER BY case_count DESC LIMIT 20;
```

### switch_cases

Per-case detail for reconstructed switches (via the kernel `calc_switch_cases`): one row
per case value → target. `switch_tables` is the summary (one row per switch); `switch_cases`
is the drill-down. Filter by an exact function-start `func_addr` (filter_eq pushdown).

| Column | Type | Description |
|--------|------|-------------|
| `func_addr` | INT | Containing function |
| `switch_instr_addr` | INT | The switch instruction — joins `switch_tables.instr_addr` |
| `case_index` | INT | 0-based row index within the switch |
| `case_value` | INT | The case value; **NULL** on the default row |
| `target_addr` | INT | The case's target address |
| `is_default` | INT | 1 for the default row, 0 for a real case |

Multiple case labels that share one target each get their own row (IDA groups labels per
target). The default row (`is_default=1`, `case_value` NULL) carries `switch_tables.default_addr`.

```sql
-- Every case value -> target for one switch
SELECT case_value, target_addr, is_default
FROM switch_cases WHERE func_addr = 0x401000 ORDER BY case_index;

-- Cases joined to their switch summary
SELECT sc.case_value, sc.target_addr, st.case_count
FROM switch_cases sc
JOIN switch_tables st
  ON st.instr_addr = sc.switch_instr_addr AND st.func_addr = sc.func_addr
WHERE sc.is_default = 0 AND sc.func_addr = 0x401000;
```

### function_frames

Per-function stack-frame layout, decompiler-free (from IDA's function frame fields).
The first seven columns are the canonical cross-tool schema. Filter by an exact
function-start `func_addr` for an O(1) single-function read.

| Column | Type | Description |
|--------|------|-------------|
| `func_addr` | INT | Function |
| `frame_size` | INT | Aggregate stack footprint (locals + saved regs + return address + purged args) |
| `arg_size` | INT | The stack-argument area: bytes of every stack argument, whatever the calling convention |
| `local_size` | INT | Local variables size (`func_t::frsize`) |
| `saved_reg_size` | INT | Saved registers size (`func_t::frregs`) |
| `stack_base_reg` | TEXT | The program's stack-pointer register (`rsp` in x64, `esp` in 32-bit x86); NULL when the processor has no register named `sp` |
| `has_frame_pointer` | INT | 1 if the function uses a frame pointer (`FUNC_FRAME`) |
| `func_name` | TEXT | Function name (as `funcs.name`) |
| `uses_chkstk` | INT | 1 if a call in the function reaches a stack-probe helper (`__chkstk`, `__alloca_probe`, `___chkstk_ms`, `__rust_probestack`, ...): directly, through a `jmp` thunk, or through an import slot. Compilers emit the probe for frames larger than a page. Computed only when the column is read. |
| `purged_size` | INT | Bytes the function pops on return (`func_t::argsize`): a `__stdcall` function's argument bytes, 0 for `__cdecl` |

```sql
-- Functions with the largest stack frames
SELECT func_addr, func_name, frame_size, local_size FROM function_frames
ORDER BY frame_size DESC LIMIT 20;

-- Functions that probe the stack (frames bigger than a page)
SELECT func_name, frame_size FROM function_frames
WHERE uses_chkstk = 1 ORDER BY frame_size DESC;
```

### data_items

Defined data items (data heads — every head where `is_data(get_flags)` is true).
Canonical cross-tool schema, aligned with ghidrasql. Full-scan generator; a
`WHERE addr = X` predicate is an O(1) exact-head lookup. An address inside a
multi-byte item matches no row.

| Column | Type | Description |
|--------|------|-------------|
| `addr` | INT | Item head address |
| `name` | TEXT | Symbol name at the item, or empty |
| `data_type` | TEXT | Applied `tinfo` type string, else the flag class (`byte`/`word`/`dword`/`qword`/`string`/`struct`/`data`) |
| `size` | INT | Item size in bytes (`get_item_size`) |
| `value_repr` | TEXT | Best-effort value: string contents for strlits, hex scalar for 1/2/4/8-byte items, else empty |
| `segment_name` | TEXT | Containing segment name |
| `is_string` | INT | 1 for string literals (`is_strlit`) |
| `is_initialized` | INT | 0 for BSS / unmapped bytes (`is_loaded`), 1 otherwise |

```sql
-- All defined strings, largest first
SELECT addr, size, value_repr FROM data_items
WHERE is_string = 1 ORDER BY size DESC LIMIT 20;

-- The data item at a specific address (O(1) point lookup)
SELECT * FROM data_items WHERE addr = 0x404000;
```

### dominators / post_dominators / loops

Canonical cross-tool CFG-graph tables (aligned with ghidrasql). Each maps a
function's `qflow_chart_t` basic blocks onto opaque node ids and runs the generic
`xsql::graph` module (dominance / natural loops). Always filter by an exact
function-start `func_addr`; an interior EA matches no rows.

| Table | Columns |
|-------|---------|
| `dominators` | `func_addr`, `node_addr`, `idom_addr` (NULL at entry), `depth`, `is_entry` |
| `post_dominators` | `func_addr`, `node_addr`, `ipdom_addr` (NULL to exit), `depth`, `is_exit` |
| `loops` | `func_addr`, `header_addr`, `latch_addr`, `start_addr`, `end_addr`, `depth`, `loop_kind`, `block_count` |

`loops.depth` is loop-nesting depth (outermost = 1); a self-loop is a legitimate
1-block loop (`header_addr == latch_addr`, `block_count = 1`). `start_addr`..`end_addr`
is the address hull of the loop's blocks; for a loop spanning chunks it includes code
outside the loop, so test membership with the blocks, not the range. `dominators.depth`
and `post_dominators.depth` are depths in the dominator tree (entry/exit = 0).

```sql
-- Immediate dominator of each block in a function
SELECT printf('0x%x', node_addr) AS block, printf('0x%x', idom_addr) AS idom, depth
FROM dominators WHERE func_addr = 0x401000 ORDER BY depth;

-- Deepest-nested loops across a function
SELECT header_addr, block_count, depth FROM loops
WHERE func_addr = 0x401000 ORDER BY depth DESC;
```

### Non-contiguous functions

A function can own **tail chunks** outside its entry chunk (exception handlers, cold
paths, code placed elsewhere by the compiler or linker), and one tail can be owned by
several functions. `funcs.addr`..`funcs.end_addr` is the entry chunk only, so an
address-range check against it misses every tail. Use `func_at(addr)` for "which
function owns X", the owner columns (`func_addr`, `xrefs.from_func`) for joins, and
`function_chunks` for a function's full extent. `disasm_func(addr)` lists every chunk.

### function_chunks

Every chunk of every function, **one row per owner**: a tail shared by several
functions appears once under each of them. `WHERE func_addr = X` is the fast path
(charts only that function's chunks); aggregate by `func_addr` for function-level
span or density metrics.

| Column | Type | Description |
|--------|------|-------------|
| `func_addr` | INT | Owning function (entry address) |
| `chunk_start` | INT | Chunk start address |
| `chunk_end` | INT | Chunk end address (exclusive) |
| `block_count` | INT | Number of basic blocks in this chunk |
| `total_size` | INT | Bytes in this chunk |
| `is_tail` | INT | 0 = entry chunk, 1 = tail chunk |
| `flags` | INT | The chunk's IDA function flags (64-bit) |

```sql
-- All chunks of one function, entry chunk first
SELECT printf('0x%X', chunk_start) AS start_hex, printf('0x%X', chunk_end) AS end_hex,
       is_tail, block_count, total_size
FROM function_chunks
WHERE func_addr = 0x401000
ORDER BY is_tail, chunk_start;

-- Tails shared by more than one function
SELECT printf('0x%X', chunk_start) AS tail, COUNT(*) AS owners
FROM function_chunks
WHERE is_tail = 1
GROUP BY chunk_start
HAVING COUNT(*) > 1;
```

### func_at

Table-valued function: the function(s) owning an address, tail chunks included.
`func_at(addr)` needs its `addr` argument; it returns one row per owning function
(a shared tail yields several) and **no rows** when `addr` is outside every function.

| Column | Type | Description |
|--------|------|-------------|
| `func_addr` | INT | Owning function (entry address) |
| `name` | TEXT | Owning function name |
| `chunk_start` | INT | Start of the chunk containing `addr` |
| `chunk_end` | INT | End of that chunk (exclusive) |
| `is_tail` | INT | 1 when `addr` lies in a tail chunk |

```sql
-- Which function owns this address?
SELECT printf('0x%X', func_addr) AS func, name, is_tail FROM func_at(0x401000);

-- Owning function of each call site of a target
SELECT printf('0x%X', x.from_addr) AS site, fa.name
FROM xrefs x JOIN func_at(x.from_addr) fa
WHERE x.to_addr = 0x401000 AND x.is_code = 1;

-- Does a given function contain an address?
SELECT EXISTS (SELECT 1 FROM func_at(0x401010) WHERE func_addr = 0x401000) AS contains;
```

---

## SQL Functions -- Disassembly

| Function | Description |
|----------|-------------|
| `disasm_at(addr)` | Canonical listing line for containing head (works for code/data) |
| `disasm_at(addr, n)` | Canonical listing line with +/- `n` neighboring heads |
| `disasm(addr)` | Single disassembly line at address |
| `disasm(addr, n)` | Next N instructions from address (count-based) |
| `disasm_range(start, end)` | All disassembly lines in address range [start, end) |
| `disasm_func(addr)` | Full disassembly of the function containing address: every chunk, entry first, with a `; ---------- tail chunk <start>-<end> (of <name>) ----------` line before each tail |
| `make_code(addr)` | Create instruction at address (returns 1/0) |
| `make_code_range(start, end)` | Create instructions in range, returns created count |

### Disassembly Examples

```sql
-- Canonical single-EA disassembly (safe for code or data)
SELECT disasm_at(0x401000);

-- Canonical context window (+/- 2 heads)
SELECT disasm_at(0x401000, 2);

-- Full function disassembly: every chunk, tails after a separator line
SELECT disasm_func(addr) FROM funcs WHERE name = '_main';

-- Disassemble a specific address range
SELECT disasm_range(0x401000, 0x401100);

-- Sliding window: next 5 instructions from an address
SELECT disasm(0x401000, 5);
```

---

## SQL Functions -- Names & Functions

Use table lookups for address and containing-function metadata. Resolve symbol names to integer EAs before using these patterns.

| Pattern | Description |
|---------|-------------|
| `SELECT name FROM names WHERE addr = :addr LIMIT 1` | Name at address |
| `SELECT name FROM func_at(:addr)` | Function(s) containing address (tail chunks included; one row per owner) |
| `SELECT func_addr FROM func_at(:addr)` | Entry address of the containing function(s) |
| `SELECT chunk_start, chunk_end, is_tail FROM func_at(:addr)` | The chunk containing the address |
| `SELECT chunk_count, size FROM funcs WHERE addr = :func` | Chunk count and total size of a function |
| `SELECT * FROM function_chunks WHERE func_addr = :func` | Every chunk of a function |

Function count and index lookup are table-driven:

```sql
SELECT COUNT(*) AS function_count FROM funcs;
SELECT addr FROM funcs WHERE rowid = 0;
```

---

## SQL Functions -- Navigation

Use `heads` ordering for defined-item navigation and SQLite formatting functions for display strings. Address equality/range filters are optimized; `ORDER BY addr` or `ORDER BY addr DESC` is consumed for next/previous-item lookups.

```sql
SELECT addr
FROM heads
WHERE addr > 0x401000
ORDER BY addr
LIMIT 1;

SELECT addr
FROM heads
WHERE addr < 0x401000
ORDER BY addr DESC
LIMIT 1;

SELECT printf('0x%llx', addr) AS address_hex
FROM heads
LIMIT 10;
```

### High addresses (>= 2^63)

In a kernel image (`0xFFFFF800...`, `0xFFFFFFFF8...`) every address is at or
above `0x8000000000000000`, which SQL holds as a **negative INTEGER**. So
`ORDER BY addr` lists the high half first (most negative first), then the low
half, and `heads`, `applied_types`, `instructions`, `funcs`, `names` and
`segments` all return and order rows that way.

- Write high addresses as hex literals (`0xFFFFF80000100000`) or the negative
  decimal, **never** as a decimal >= 2^63 (`18446735277617577984` is a REAL
  to SQLite and matches nothing).
- `addr > 0xFFFFF80000100000` is "signed-greater": it also includes every
  low-half address. Bound the high half with `AND addr < 0` (or
  `BETWEEN <high hex> AND -1`); `-1` is `0xFFFFFFFFFFFFFFFF`, above every address.
- Next/previous navigation works unchanged within the high half:

```sql
-- The head after 0xFFFFF80000100000, staying in the high half
SELECT printf('0x%llX', addr) AS next_head FROM heads
WHERE addr > 0xFFFFF80000100000 AND addr < 0
ORDER BY addr LIMIT 1;

-- The highest head in the database (the top of the high half, if any)
SELECT printf('0x%llX', addr) AS top_head FROM heads
WHERE addr < 0 ORDER BY addr DESC LIMIT 1;
```

The highest segment end IDA accepts is `0xFFFFFFFFFFFFFFFE`; `segments` rejects
an `end_addr` of `-1` (BADADDR) instead of letting IDA silently create a 1-byte
segment.

Segment lookup is table-driven:

```sql
SELECT name
FROM segments
WHERE 0x401000 >= start_addr
  AND 0x401000 < end_addr
LIMIT 1;
```

---

## SQL Functions -- Item Analysis

Use `heads` for item classification, size, and raw flags:

```sql
SELECT addr, size, type, flags, disasm
FROM heads
WHERE addr = 0x401000;
```

---

## SQL Functions -- Instruction Details

Use `instructions` and `instruction_operands` for decoded instruction facts:

```sql
SELECT addr, itype, mnemonic
FROM instructions
WHERE func_addr = 0x401000
LIMIT 10;

SELECT operand_index, text, type_code, type_name, value
FROM instruction_operands
WHERE addr = 0x401000
ORDER BY operand_index;

SELECT i.addr, i.itype, i.mnemonic, i.size, o.operand_index, o.text, o.type_name, o.value
FROM instructions i
LEFT JOIN instruction_operands o
  ON o.addr = i.addr AND o.addr = 0x401000
WHERE i.addr = 0x401000
ORDER BY o.operand_index;
```

---

## SQL Functions -- File Generation

| Function | Description |
|----------|-------------|
| `gen_listing(path)` | Generate full-database listing output (LST) |

---

## SQL Functions -- Graph Generation

| Function | Description |
|----------|-------------|
| `gen_cfg_dot(addr)` | Generate CFG as DOT graph string |
| `gen_cfg_dot_file(addr, path)` | Write CFG DOT to file |
| `gen_schema_dot()` | Generate database schema as DOT |

```sql
-- Get CFG for a function as DOT format
SELECT gen_cfg_dot(0x401000);
```

---

## Performance Rules

| Table | Architecture | Key Constraint | Notes |
|-------|-------------|----------------|-------|
| `funcs` | Index-Based | none needed | O(1) per row via `getn_func(i)` -- always fast |
| `instructions` | Iterator | `func_addr` | Function-item iterator (fast) vs full code-head scan (slow) |
| `blocks` | Iterator | `func_addr` | Constraint pushdown: iterates blocks of one function |
| `function_chunks` | Cached | `func_addr` | filter_eq pushdown charts one function's chunks; full scan builds every function's |
| `func_at(addr)` | Generator | `addr` (required) | Resolves the owners of one address; errors without `addr` |
| `cfg_edges` | Iterator | `func_addr` | filter_eq pushdown: O(blocks in function) |
| `disasm_calls` | Generator | `func_addr`, `addr` for writes | Lazy streaming, respects LIMIT; `callee_type` is writable |
| `heads` | Generator | `addr =`, addr range | Consumes `ORDER BY addr` for next/previous navigation; broad scans can still be large |
| `instruction_operands` | Iterator | `addr`, `func_addr` | Address lookup decodes one instruction; function lookup iterates one function |
| `segments` | Index-Based | none needed | Small table, always fast |
| `names` | Iterator | none needed | Iterates IDA's name list |
| `signatures` | Cached | none needed | The list is small; an INSERT waits for auto-analysis to apply the signature (seconds on a large database) |
| `available_signatures` | Cached | none needed | Lists IDA's sig folders and reads each file's header |

**Key rules:**
- `funcs` is always fast -- no constraint needed.
- `instructions` without `func_addr` scans every code head -- use `func_addr` for per-function queries.
- `blocks` without `func_addr` iterates all functions' flowcharts -- always constrain.
- "Is X in function f" is `func_at(X)`, never an `addr`..`end_addr` range check: `end_addr` ends the entry chunk, so a range check misses tail chunks.
- `heads` is often large. Use `addr = X` for item facts and address range plus `ORDER BY addr [DESC] LIMIT 1` for navigation.

**Cost model:**
```
funcs (full scan)            -> O(number of functions), typically ~1000s, fast
instructions WHERE func_addr -> O(function_size / avg_insn_size)
instructions (no constraint) -> O(total_code_heads), potentially 100K+
blocks WHERE func_addr         -> O(block_count_in_func), fast
function_chunks WHERE func_addr -> O(chunks_in_func), fast
func_at(addr)                -> O(owners of one address), fast
cfg_edges WHERE func_addr      -> O(block_count_in_func), fast
disasm_calls WHERE func_addr -> O(instructions_in_func), streaming
disasm_calls UPDATE callee_type WHERE addr -> O(1) call-site lookup
heads WHERE addr          -> O(1) IDA head check
heads next/prev LIMIT 1      -> O(distance to next/previous defined head)
instruction_operands addr    -> O(operands in one instruction)
instruction_operands func    -> O(operands in one function)
```

---

## Additional Resources

- For advanced CTE patterns and instruction lifecycle playbooks: [references/disassembly-examples.md](references/disassembly-examples.md)
- For additional table schemas (fchunks, heads, bytes, signatures, problems, fixups, etc.): [references/disassembly-tables.md](references/disassembly-tables.md). `fchunks` is the raw one-row-per-chunk list with only the primary `owner`; prefer `function_chunks` / `func_at` for ownership.

---

## See Also

- `decompiler` — pseudocode and ctree on the same function; pivot when disassembly is too noisy.
- `xrefs` — call graph and data references centered on a function or call site; `xrefs.from_func` is the function owning each reference source (tail chunks included).
- `functions` — the containing-function patterns (`func_at`, `function_chunks`) in the SQL function catalog.
- `data` — operand-targeted bytes/strings; `bytes` table for per-byte reads and bounded windows via `WHERE start_addr = X AND n = N` composed with `hex(blob_concat(value))` for bulk hex.

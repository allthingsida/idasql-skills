---
name: connect
description: "Connect to IDA databases and bootstrap sessions. Use when starting analysis, routing to other skills, or setting up CLI/HTTP/MCP connections."
allowed-tools:
  - Bash
  - Read
  - Glob
  - Grep
---

## Additional Resources

- For canonical schema catalog: [references/schema-catalog.md](references/schema-catalog.md)
- For CLI reference, REPL commands, server modes, and runtime controls: [references/cli-reference.md](references/cli-reference.md)
- For legacy parity tracking: [references/legacy-parity-matrix.md](references/legacy-parity-matrix.md)
- For optimization quality gate: [references/optimization-checklist.md](references/optimization-checklist.md)
- For HTTP server guide: [references/server-guide.md](references/server-guide.md)

---

## Quick Start CLI (Do This First)

Use these commands first to avoid guessing behavior or schema:

```bash
# Single query
idasql -s database.i64 -q "SELECT * FROM welcome"

# Interactive REPL
idasql -s database.i64 -i

# Long-lived HTTP server for iterative analysis
idasql -s database.i64 --http 8081

# Query over HTTP
curl -X POST http://127.0.0.1:8081/query -d "SELECT name, size FROM funcs LIMIT 5"
```

Critical guardrails:
- Always provide `-s <db>` (`.idb` / `.i64`).
- Use `--write` when you want edits persisted on exit.
- Discover schema before writing queries:
  - REPL: `.schema <table>`
  - SQL: `PRAGMA table_xinfo(<table>);` (or `PRAGMA table_info(<table>);`)
- Start orientation with `SELECT * FROM welcome;`.

---

## Schema Catalog (Canonical)

Canonical table/view formats live in `references/schema-catalog.md`.

- Source of truth for column shapes and owner skill mapping.
- Sourced from SQL metadata (`pragma_table_list` + `pragma_table_xinfo`).
- Use this before assuming column names for less-common surfaces.
- Legacy parity tracker: `references/legacy-parity-matrix.md`
- Optimization quality gate: `references/optimization-checklist.md`

Manual refresh:
1. `SELECT schema, name, type, ncol FROM pragma_table_list WHERE schema='main' ORDER BY type, name;`
2. `PRAGMA table_xinfo(<surface>);`
3. Update `references/schema-catalog.md` owner mapping when surfaces change.

---

## Session Bootstrap Contract

Use this exact startup flow before deep analysis:

1. Connect to database (`-s`, `-i`, or `--http`).
2. Run orientation query:
```sql
SELECT * FROM welcome;
```
3. Validate key entities exist:
```sql
SELECT COUNT(*) AS funcs FROM funcs;
SELECT COUNT(*) AS xrefs FROM xrefs;
SELECT COUNT(*) AS strings FROM strings;
```
4. Introspect schema for target surfaces before authoring complex SQL:
```sql
PRAGMA table_xinfo(funcs);
PRAGMA table_xinfo(xrefs);
```
5. Route to domain skill using routing matrix below.

Never skip steps 2-4 when the user prompt is broad or ambiguous.

---

## Global Agent Contracts

These contracts apply across all idasql skills and should be treated as one shared agent behavior model.

### Read-First Contract
- Read current state first (`SELECT`) before writes (`INSERT`/`UPDATE`/`DELETE`).
- Confirm target precision using stable identifiers (`address`, `func_addr`, `idx`, `label_num`).

### Anti-Guessing Contract
- Do not assume columns/types for long-tail surfaces.
- Introspect via `.schema` or `PRAGMA table_xinfo(...)` before issuing uncertain queries.

### Mandatory Mutation Loop
1. Read current state.
2. Apply mutation.
3. Refresh if needed (`decompile(..., 1)` for decompiler surfaces).
4. Re-read and verify expected change.

### Performance Contract
- Always constrain high-cost surfaces (`xrefs`, `instructions`, `ctree*`, `pseudocode`) by key columns.
- For decompiler surfaces, enforce `func_addr = X` unless explicitly asked for broad scans.

### Failure Recovery Contract
- On `no such table/column`: introspect schema and retry.
- On empty results: validate address range, table freshness (`rebuild_strings()`), and runtime capabilities.
- On timeout: narrow scope, add constraints, paginate, or split query.

---

## Skill Routing Matrix (Intent -> Skill)

Use this deterministic mapping for initial routing:

| User intent | Primary skill | Typical first query |
|-------------|---------------|---------------------|
| "what does this binary do?" / triage | `analysis` | `SELECT * FROM entries;` |
| disassembly, segments, instructions | `disassembly` | `SELECT * FROM funcs LIMIT 20;` |
| xrefs/callers/callees/import dependencies | `xrefs` | `SELECT * FROM xrefs WHERE to_ea = ...;` |
| find functions/types/labels/members by name pattern | `grep` | `SELECT name, kind, address FROM grep WHERE pattern = 'main' LIMIT 20;` |
| strings/bytes/pattern search | `data` | `SELECT * FROM strings LIMIT 20;` |
| decompile/pseudocode/ctree/lvars | `decompiler` | `SELECT decompile(0x...);` |
| comments/renames/retyping/bookmarks | `annotations` | `SELECT ...` on target row before update |
| type creation/struct/enum/member work | `types` | `SELECT * FROM types LIMIT 20;` |
| breakpoints/patching | `debugger` | `SELECT * FROM breakpoints;` |
| persistent key/value notes | `storage` | `SELECT * FROM netnode_kv LIMIT 20;` |
| SQL function lookup/signature recall | `functions` | `SELECT * FROM pragma_function_list;` |
| live IDA UI context questions | `ui-context` | `SELECT get_ui_context_json();` (when available) |
| IDA SDK-only logic not in SQL surfaces | `idapython` | `PRAGMA idasql.enable_idapython = 1; SELECT idapython_snippet('print(...)');` |
| recursive source/structure recovery | `re-source` | start from function + recurse/handoff |

When prompts span domains, execute in this order:
1. Orientation in `connect`
2. Primary domain skill
3. Adjacent skills for enrichment (for example `xrefs` + `decompiler` + `annotations`)

---

## Cross-Skill Execution Recipes

### Recipe: Unknown binary triage -> suspicious function deep dive -> annotate
1. `analysis`: identify candidates from imports/strings/call patterns.
2. `xrefs`/`disassembly`: map call graph and call sites.
3. `decompiler`: inspect logic and variable semantics.
4. `annotations`: apply comments/renames/types with mutation loop.

### Recipe: String IOC -> reference graph -> patch
1. `data`: locate candidate strings and addresses.
2. `xrefs`: map references to caller functions.
3. `debugger` or `annotations`: patch or annotate specific sites.

### Recipe: Type recovery from pseudocode
1. `decompiler`: inspect lvars, call args, and ctree patterns.
2. `types`: create/refine structs/enums and apply declarations.
3. `annotations`: finalize naming/comments and verify rendered pseudocode.

---

## UI Context Routing

For prompts like "what am I looking at?", "what's selected?", "what is on the screen?", "look at what I'm doing", or references to "this/current/that", use the dedicated `ui-context` skill.

`ui-context` owns:
- `get_ui_context_json()` capture/reuse policy
- temporal reference rules (`this` vs `that`)
- response template, examples, and fallback messaging

Runtime caveat:
- `get_ui_context_json()` is plugin GUI runtime only, not idalib/CLI mode.
- If unavailable, state that UI context is unavailable and continue with non-UI SQL workflows.

---

## welcome

Database orientation surface for quick session metadata.
This is metadata-only and not a replacement for UI context capture.

| Column | Type | Description |
|--------|------|-------------|
| `summary` | TEXT | One-line database summary |
| `processor` | TEXT | Processor/module name |
| `is_64bit` | INT | 1=64-bit database, 0=32-bit |
| `min_ea` | TEXT | Minimum address in database |
| `max_ea` | TEXT | Maximum address in database |
| `start_ea` | TEXT | Entry/start address |
| `entry_name` | TEXT | Entry symbol name (if known) |
| `funcs_count` | INT | Number of detected functions |
| `segments_count` | INT | Number of segments |
| `names_count` | INT | Number of named addresses |

```sql
SELECT * FROM welcome;
```

For canonical schema and owner mapping, see `references/schema-catalog.md`.

---

## What is IDA and Why SQL?

**IDA Pro** is the industry-standard disassembler and reverse engineering tool. It analyzes compiled binaries (executables, DLLs, firmware) and produces:
- **Disassembly** - Human-readable assembly code
- **Functions** - Detected code boundaries with names
- **Cross-references** - Who calls what, who references what data
- **Types** - Structures, enums, function prototypes
- **Decompilation** - C-like pseudocode (with Hex-Rays plugin)

**IDASQL** exposes all this analysis data through SQL virtual tables, enabling:
- Complex queries across multiple data types (JOINs)
- Aggregations and statistics (COUNT, GROUP BY)
- Pattern detection across the entire binary
- Scriptable analysis without writing IDA plugins or IDAPython scripts

---

## Core Concepts for Binary Analysis

### Addresses (ea_t)
Everything in a binary has an **address** - a memory location where code or data lives. IDA uses `ea_t` (effective address) as unsigned 64-bit integers. SQL shows these as integers; use `printf('0x%X', address)` for hex display.

Address-taking SQL functions accept:
- integer EA values (preferred for deterministic scripts)
- numeric strings (`'4198400'`, `'0x401000'`)
- symbol names resolved with `get_name_ea(BADADDR, name)` (global names)

Examples:
```sql
SELECT decompile('DriverEntry');
SELECT set_type('DriverEntry', 'NTSTATUS DriverEntry(PDRIVER_OBJECT, PUNICODE_STRING);');
SELECT comment_at('0x401000');
```

If a symbol cannot be resolved, SQL functions return an explicit error like:
`Could not resolve name to address: <name>`.

Local label lookup that depends on a specific `from` context is not consulted by default (`BADADDR` resolution). Use explicit numeric EAs when needed.

### Functions
IDA groups code into **functions** with:
- `address` / `start_ea` - Where the function begins
- `end_ea` - Where it ends
- `name` - Assigned or auto-generated name (e.g., `main`, `sub_401000`)
- `size` - Total bytes in the function

There will be addresses and disassembly listing not belonging to a function. IDASQL can still get the bytes, disassembly listing ranges, etc.
For single-EA disassembly (code or data), prefer `disasm_at(ea[, context])` over function-scoped queries.

### Cross-References (xrefs)
Binary analysis is about understanding **relationships**:
- **Code xrefs** - Function calls, jumps between code
- **Data xrefs** - Code reading/writing data locations, or data referring to other data (pointers)
- `from_ea` -> `to_ea` represents "address X references address Y"
Use table: `xrefs(from_ea, to_ea, type, is_code)`.

### Segments

Use table: `segments(start_ea, end_ea, name, class, perm)`.

Memory is divided into **segments** with different purposes. For example, a typical PE file, has these segments:

- `.text` - Executable code (typically)
- `.data` - Initialized global data
- `.rdata` - Read-only data (strings, constants)
- `.bss` - Uninitialized data

Of course, segment names and types can vary. You may query the `segments` table to understand memory layout.

### Basic Blocks
Within a function, **basic blocks** are straight-line code sequences:
- No branches in the middle
- Single entry, single exit
- Useful for control flow analysis
Use table: `blocks(start_ea, end_ea, func_ea, size)`.

### Decompilation (Hex-Rays)
The **Hex-Rays decompiler** converts assembly to C-like **pseudocode**:
- **ctree** - The Abstract Syntax Tree of decompiled code
- **lvars** - Local variables detected by the decompiler
- Much easier to analyze than raw assembly

Core decompiler surfaces:
- `decompile(addr)` (**PRIMARY read/display surface**)
  - Returns the entire function as one text block.
  - Each output line is prefixed for address grounding:
    - Addressed line: `/* 401010 */ ...`
    - Non-anchored line: `/*          */ ...` (no address anchor for that line)
  - Use this first when the user asks to "decompile", "show code", "show pseudocode", or "explain function logic".
- `pseudocode` table (**structured/edit surface**)
  - Use for line-level filtering (`func_addr`, `ea`, `line_num`) and comment writes keyed by `ea + comment_placement`.
  - Resolve a writable pseudocode anchor first; do not assume `ea == func_addr`.
  - Not the preferred display surface for full-function code.
- `ctree` and `ctree_call_args` for AST-level analysis
- `ctree_lvars` for local variable rename/type/comment updates

---

## Performance Rules

### CRITICAL: Constraint Pushdown

Some tables have **optimized filters** that use efficient IDA SDK APIs:

| Table | Optimized Filter | Without Filter |
|-------|------------------|----------------|
| `instructions` | `func_addr = X` | O(all instructions) - SLOW |
| `blocks` | `func_ea = X` | O(all blocks) |
| `xrefs` | `to_ea = X` or `from_ea = X` | O(all xrefs) |
| `pseudocode` | `func_addr = X` | **Decompiles ALL functions** |
| `ctree*` | `func_addr = X` | **Decompiles ALL functions** |

**Always filter decompiler tables by `func_addr`!**

### Use Integer Comparisons

```sql
-- SLOW: String comparison
WHERE mnemonic = 'call'

-- FAST: Integer comparison
WHERE itype IN (16, 18)  -- x86 call opcodes
```

### O(1) Random Access

```sql
-- SLOW: O(n) - sorts all rows
SELECT address FROM funcs ORDER BY RANDOM() LIMIT 1;

-- FAST: O(1) - direct index access
SELECT func_at_index(ABS(RANDOM()) % func_qty());
```

### CTE-First Mutation Workflow

For instruction lifecycle edits, use a CTE to identify precise targets first, then mutate:

```sql
WITH target AS (
    SELECT address
    FROM instructions
    WHERE func_addr = 0x401000
    ORDER BY address DESC
    LIMIT 1
)
DELETE FROM instructions
WHERE address IN (SELECT address FROM target);

SELECT make_code_range(address, end_ea) FROM funcs WHERE address = 0x401000;
```

This keeps mutation scope explicit and predictable for both humans and agents.

---

## Summary: When to Use What

| Goal | Table/Function |
|------|----------------|
| List all functions | `funcs` |
| Functions by return type | `funcs WHERE return_is_integral = 1` |
| Functions by arg count | `funcs WHERE arg_count >= N` |
| Void functions | `funcs WHERE return_is_void = 1` |
| Pointer-returning functions | `funcs WHERE return_is_ptr = 1` |
| Functions by calling convention | `funcs WHERE calling_conv = 'fastcall'` |
| Find who calls what | `xrefs` with `is_code = 1` |
| Find data references | `xrefs` with `is_code = 0` |
| Analyze imports | `imports` |
| Find strings | `strings` |
| Configure string types | `rebuild_strings(types, minlen)` |
| Instruction analysis | `instructions WHERE func_addr = X` |
| Recreate deleted instructions | `make_code(addr)`, `make_code_range(start, end)` |
| Create function at EA | `INSERT INTO funcs(address) VALUES (...)` |
| View function disassembly | `disasm_func(addr)` or `disasm_range(start, end)` |
| View decompiled code | `decompile(addr)` |
| UI/screen context questions | `ui-context` skill (`get_ui_context_json()`, plugin UI only) |
| Edit decompiler comments | `Resolve writable anchor, then UPDATE pseudocode SET comment = '...' WHERE func_addr = X AND ea = Y` |
| AST pattern matching | `ctree WHERE func_addr = X` |
| Call patterns | `ctree_v_calls`, `disasm_calls` |
| Control flow | `ctree_v_loops`, `ctree_v_ifs` |
| Return value analysis | `ctree_v_returns` |
| Functions returning specific values | `ctree_v_returns WHERE return_num = 0` |
| Pass-through functions | `ctree_v_returns WHERE returns_arg = 1` |
| Wrapper functions | `ctree_v_returns WHERE returns_call_result = 1` |
| Variable analysis | `ctree_lvars WHERE func_addr = X` |
| Type information | `types`, `types_members` |
| Function signatures | `types_func_args` (with type classification) |
| Functions by return type | `types_func_args WHERE arg_index = -1` |
| Typedef-aware type queries | `types_func_args` (surface vs resolved) |
| Hidden pointer types | `types_func_args WHERE is_ptr = 0 AND is_ptr_resolved = 1` |
| Manage breakpoints | `breakpoints` (full CRUD) |
| Modify segments | `segments` (INSERT/UPDATE/DELETE) |
| Rename decompiler labels | `rename_label(...)` or `UPDATE ctree_labels SET name=...` |
| Delete instructions | `instructions` (DELETE converts to unexplored bytes) |
| Recreate instructions | `make_code`, `make_code_range` |
| Bulk patch from file bytes | `load_file_bytes(path, file_offset, address, size[, patchable])` |
| EA to physical offset mapping | `bytes.fpos` (`NULL` means unmapped) |
| Create types | `types` (INSERT struct/union/enum) |
| Add struct members | `types_members` (INSERT) |
| Add enum values | `types_enum_values` (INSERT) |
| Modify database | `funcs`, `names`, `comments`, `bookmarks` (INSERT/UPDATE/DELETE) |
| Store custom key-value data | `netnode_kv` (full CRUD, persists in IDB) |
| Entity search (structured) | `grep` skill + `grep WHERE pattern = '...'` |
| Entity search (JSON) | `grep` skill + `grep('pattern', limit, offset)` |

**Remember:** Always use `func_addr = X` constraints on instruction and decompiler tables for acceptable performance.

---

## Error Handling

- **No Hex-Rays license:** Decompiler tables (`pseudocode`, `ctree*`, `ctree_lvars`) will be empty or unavailable
- **No constraint on decompiler tables:** Query will be extremely slow (decompiles all functions)
- **Invalid address:** Functions like `func_at(addr)` return NULL
- **Missing function:** JOINs may return fewer rows than expected

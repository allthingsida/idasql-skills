# SQL Surface Catalog

Compact owner-mapping index for idasql surfaces. For column details, use `PRAGMA table_xinfo(<surface>)` at runtime.

Manual refresh procedure:
1. `SELECT schema, name, type, ncol FROM pragma_table_list WHERE schema='main' ORDER BY type, name;`
2. `PRAGMA table_xinfo(<surface>);`
3. Update owner mapping here when new surfaces appear.

## Tables

| Surface | Kind | Owner Skill | Cols | Writable | Notes |
|---------|------|-------------|------|----------|-------|
| `applied_types` | virtual | types | 4 | INSERT / UPDATE (`decl`) / DELETE | Address equality accepts EA, numeric string, or symbol name; point lookup can synthesize an untyped mapped row; ranges return typed rows only |
| `blocks` | virtual | disassembly | 4 | — | Filter by `func_addr` |
| `bookmarks` | virtual | annotations | 6 | INSERT/UPDATE/DELETE | Writable: `description`, `folder_path`; `inode` and `full_path` are read-only |
| `breakpoints` | virtual | debugger | 21 | INSERT/UPDATE/DELETE | Writable: `enabled`, `type`, `size`, `flags`, `pass_count`, `condition`, `group`, `folder_path`; `folder_path` aliases IDA breakpoint group |
| `bytes` | virtual | data / debugger | 9 (+ hidden `start_addr`, `n`) | UPDATE (`value`/`word`/`dword`/`qword`) / DELETE (revert patch) | Pure mapped-byte rows; filter by `addr` (point), `WHERE start_addr = X AND n = N` (bounded read; `start_addr` is a separate hidden input so predicates on `addr` stay enforceable), or tight `addr` ranges; `WHERE is_patched = 1` enumerates patches fast. Writes take exact integers (text `'0x90'`, fractions and blobs are refused). `value` is NULL where `is_initialized = 0` (BSS), and `blob_concat` skips NULLs — add `AND is_initialized = 1` or `COALESCE(value, 0)` for a fixed-width window. Bulk hex: `hex(blob_concat(value))`. Bulk BLOB: `blob_concat(value)`. |
| `byte_search` | virtual | data | 8 (+ hidden `pattern`, `start_addr`, `end_addr`, `max_results`) | — | Requires `WHERE pattern = '<IDA byte pattern>'`; optional bounds via hidden columns or `addr` range predicates; outputs `addr`, `matched_hex`, `matched_bytes`, `size` |
| `data_items` | virtual | disassembly | 8 | — | Defined data items (`is_data` heads): `addr`, `name`, `data_type`, `size`, `value_repr`, `segment_name`, `is_string`, `is_initialized`; full-scan generator, `WHERE addr = X` O(1) exact-head lookup (interior EAs match no row) |
| `deep_link_parse` | virtual | deep-links | 13 | — | IDA 9.4 builds only. Requires `WHERE uri = '<ida:// link>'`; one row: `source`, `idb_name`, `resource`, `addr`, `rva`, `name`, `view`, `idb_path`, `is_ke`, `valid`, `diagnostic`, `ida_uri` (the exact string handed to IDA: the link without `idb_path`) |
| `deep_links` | virtual | deep-links | 14 | — | IDA 9.4 builds only. Requires `WHERE resource = ... AND addr = ...` (or `rva`, or `name` for types); JOIN per row (`JOIN deep_links dl ON dl.resource='functions' AND dl.addr=f.addr AND dl.view='pseudocode'`). Outputs `uri` (IDA's Copy Link format plus `&idb_path=`); `view` defaults to code (`pseudocode` for functions, `disasm` for other addresses); `valid = 0` + `diagnostic` when the target does not resolve |
| `dominators` | virtual | disassembly | 5 | — | Dominator tree over CFG blocks via `xsql::graph`: `func_addr`, `node_addr`, `idom_addr` (NULL at entry), `depth` (dominator-tree depth, entry = 0), `is_entry`; filter by exact function-start `func_addr` |
| `post_dominators` | virtual | disassembly | 5 | — | Post-dominator tree via `xsql::graph`: `func_addr`, `node_addr`, `ipdom_addr` (NULL to exit), `depth`, `is_exit`; filter by exact function-start `func_addr` |
| `loops` | virtual | disassembly | 8 | — | Natural loops via `xsql::graph`: `func_addr`, `header_addr`, `latch_addr`, `start_addr`, `end_addr` (address hull of the loop's blocks), `depth`, `loop_kind`, `block_count`; filter by exact function-start `func_addr` |
| `call_graph` | virtual (TVF) | xrefs | 4 | — | `start` HIDDEN, `direction` HIDDEN, `max_depth` HIDDEN → func_addr, func_name, depth, parent_addr |
| `cfg_edges` | virtual | disassembly | 4 | — | Filter by exact function-start `func_addr` (filter_eq pushdown); `edge_type` `true` = branch taken (jump target), `false` = fall-through, `normal` otherwise |
| `checkpoints` | virtual | annotations | 7 | INSERT (`label`) / UPDATE (`state`) | Named IDA undo points for this database session: `seq` (rowid), `label`, `created_at`, `kind` (`user`/`auto`), `writes_since`, `statement` (auto only), `state` (`live`/`undone`). INSERT creates one (label optional; empty, duplicate and `auto#` labels refused); `SET state='undone'` rolls back to it (newer included), `SET state='live'` redoes the next undone one (refused after any newer write). DELETE refused. Not a database write itself; SQLite ROLLBACK does not undo IDA writes |
| `switch_tables` | virtual | disassembly | 7 | — | Switch/case summaries (`func_addr`, `instr_addr`, nullable `table_addr`, nullable recovered `min_case`/`max_case`, `case_count` = non-default label count, nullable `default_addr`); filter by exact function-start `func_addr` |
| `switch_cases` | virtual | disassembly | 6 | — | Per-case value→target detail (`func_addr`, `switch_instr_addr`, `case_index`, `case_value` NULL on default, `target_addr`, `is_default`); via `calc_switch_cases`; filter by exact function-start `func_addr` |
| `function_frames` | virtual | disassembly | 10 | — | Per-function stack frame (`func_addr`, `frame_size` including the return address, `arg_size` (the stack-argument area), `local_size`, `saved_reg_size`, `stack_base_reg`, `has_frame_pointer`, `func_name`, `uses_chkstk`, `purged_size` (bytes popped on return)); `stack_base_reg` is the program's stack pointer (`rsp`, `esp`); `uses_chkstk` = calls a stack probe; filter by exact function-start `func_addr` (O(1)) |
| `comments` | virtual | annotations | 3 | INSERT/UPDATE/DELETE | |
| `ctree` | virtual | decompiler | 30 | — | Filter by `func_addr` — generator |
| `microcode` | virtual | decompiler | 12 | — | Hex-Rays microcode (default MMAT_LVARS — the IR below ctree), in exact schema order: `func_addr`, `block_num`, `seq`, `addr`, `opcode`, `canonical_op` (cross-tool canonical P-code-style op), `maturity`, `stage`, `text`, `l_text`, `r_text`, `d_text`; filter by exact function-start `func_addr` (one gen_microcode/func) and optionally `maturity` (`=`/`IN`/`LIKE`/`<`/`<=`/`>`/`>=` on the rung name; exact equality re-lifts at that rung; a coerced non-matching rung yields no rows) |
| `microcode_operands` | virtual | decompiler | 10 | — | Operand rows over every non-void `minsn_t` l/r/d slot: `func_addr`, `op_seq` (joins `microcode.seq`), `operand_index`, `role` (in\|out), `kind` (reg\|imm\|mem\|var\|result; empty for retained native structural operands), `text`, `value` (integer immediates only; floating immediates remain in `text` with SQL NULL `value`), `size`, `maturity`, `stage`; filter by exact function-start `func_addr` (+ exact `maturity`) |
| `ctree_call_args` | virtual | decompiler | 16 | — | Filter by `func_addr` — generator |
| `ctree_lvars` | virtual | decompiler | 12 | UPDATE (`name`, `type`, `comment`) | Filter by `func_addr` |
| `data_refs` | virtual | xrefs | 6 | — | Cached table of non-code xrefs from every head of each function body (inline data included), with containing function info; `kind` = read / write / offset / text / info / data |
| `db_info` | virtual | disassembly | 3 | — | |
| `dirtree_entries` | virtual | annotations / disassembly / types | 11 | — | Raw IDA dirtree listing for `funcs`, `local_types`, `names`, `imports`, `idaplace_bookmarks`, `bpts`, `ltypes_bookmarks`; push down `tree`, `path`, `path LIKE`, `parent_path`, `inode`, `is_dir`, `is_file` (exact SQL comparison: entry paths are absolute, `/idasql/x`) |
| `dirtree_folders` | virtual | annotations / types | 3 | INSERT / UPDATE (`path`) / DELETE for all standard dirtrees | Empty folder lifecycle for `funcs`, `local_types`, `names`, `imports`, `idaplace_bookmarks`, `bpts`, `ltypes_bookmarks`; DELETE removes only empty folders |
| `disasm_calls` | virtual | disassembly | 5 | UPDATE (`callee_type`) | Calls made by functions (none outside every function); filter by `func_addr` — generator; `addr` identifies call-site writes |
| `disasm_loops` | virtual | disassembly | 6 | — | Natural loops (one row per back edge whose header dominates its latch); `loop_id` is the header's block index; filter by exact function-start `func_addr` |
| `entries` | virtual | disassembly | 3 | — | Entry points / exports (`ordinal`, `addr`, `name`) |
| `fchunks` | virtual | disassembly | 6 | — | Raw IDA chunk list, one row per chunk; `owner` is the **primary** owner only (a shared tail lists one owner); `flags` is 64-bit. Use `function_chunks` / `func_at` for complete ownership |
| `fixups` | virtual | disassembly | 4 | — | |
| `func_at` | virtual (TVF) | disassembly | 5 (+ hidden `addr`) | — | `func_at(addr)` → `func_addr`, `name`, `chunk_start`, `chunk_end`, `is_tail`: the function(s) owning an address, tail chunks included; one row per owner, no rows outside a function; `addr` is required (errors without it) |
| `funcs` | virtual | disassembly / annotations | 18 | INSERT/UPDATE/DELETE | Writable: `name`, `prototype`, `comment`, `rpt_comment`, `flags`, `folder_path`; `full_path` and `chunk_count` (last column) are read-only; `size` is the total over all chunks, `end_addr` ends the **entry chunk** only |
| `function_chunks` | virtual | disassembly | 7 | — | `func_addr`, `chunk_start`, `chunk_end`, `block_count`, `total_size`, `is_tail`, `flags`; one row per **owner** (a shared tail appears under every owner); fast `WHERE func_addr = X` |
| `grep` | virtual | grep | 7 | — | Requires `pattern` |
| `heads` | virtual | disassembly | 5 | — | Optimized `addr =` and address range/order navigation |
| `hidden_ranges` | virtual | disassembly | 8 | — | |
| `ida_config` | virtual | connect | 7 | UPDATE (`value`) | IDA configuration keys listed from the option files IDA reads (`ida.cfg` for the current processor, `hexrays.cfg`, `idagui.cfg`, `idauser.cfg`; IDADIR/cfg then IDAUSR/cfg): `key`, `file`, `value` (`.cfg` syntax), `value_source` (`runtime`/`inf`/`session`/`file`), `writable`, `persisted` (1 = saved with the database), `message` (IDA's warning from the last UPDATE, e.g. a clamp; a clamped `session` value shows the bound IDA applied). UPDATE applies `KEY=VALUE` and reads it back; a rejected value fails with IDA's message. No INSERT/DELETE; nothing writes `.cfg` files |
| `ida_info` | virtual | disassembly | 3 | — | |
| `imports` | virtual | xrefs | 7 | UPDATE (`folder_path`) | Import folder moves do not change module/name/ordinal |
| `local_type_bookmarks` | virtual | types / annotations | 7 | INSERT (`ordinal`,`description`), UPDATE (`description`,`folder_path`), DELETE | Enumerates the `bookmarks_t` store; INSERT marks a bookmark at a local-type ordinal (refused under idalib on IDA 9.2, whose bookmark store crashes on it). Folder moves require an already-linked bookmark |
| `instructions` | virtual | disassembly | 70 | UPDATE (format_spec) / DELETE | Filter by exact function-start `func_addr` (NULL outside every function; one row per owner for a shared tail); a DELETE that auto-analysis immediately undoes (code still flows into the instruction) fails |
| `instruction_operands` | virtual | disassembly | 11 | — | Structured decoded operands; filter by `addr` for one instruction or exact function-start `func_addr` for a function |
| `local_types` | virtual | types | 6 | — | |
| `mappings` | virtual | disassembly | 3 | — | |
| `names` | virtual | disassembly | 6 | INSERT/UPDATE/DELETE | Writable: `name`, `folder_path`; `full_path` is read-only; a refused name says why (inside an item, already used, invalid) |
| `notepad` | virtual | annotations | 2 | UPDATE (`text`) / DELETE (clears) | The database notepad, one row: `text` (LF line ends; stored with CRLF like IDA's window), `size` (stored bytes, no NUL). Refuses NULL, NUL bytes and text above 1,024,000 bytes with CRLF and the NUL; INSERT refused. In the GUI an open notepad window shows an UPDATE at IDA's next UI refresh and drops its own unsaved typing |
| `problems` | virtual | disassembly | 4 | — | |
| `runtime_settings` | virtual | connect | 6 | UPDATE (`value`) | Writable discovery view over the runtime controls: `(key, value, type, scope, kind, settable)`, one row per setting. `kind` is `value`/`action`; `settable` is 1 only when `UPDATE` is accepted, so writable keys are discoverable with `WHERE settable = 1`. Shared keys `query_timeout_ms`, `queue_admission_timeout_ms`, `max_queue`, `hints_enabled`, `timeout_stack_depth`, `max_timeout_stack_depth` (scope `common`), `timeout_push`, `timeout_pop` (scope `action`); idasql-only `enable_idapython`, `idapython_output_max`, `auto_checkpoint` (`off`/`statement`) (scope `idasql`). `type ∈ {int, bool, string}`. Change a value setting via `UPDATE runtime_settings SET value=... WHERE key=...`; `key`/`type`/`scope`, the read-only rows, and the action verbs reject writes; `timeout_push`/`timeout_pop` are PRAGMAs |
| `pseudocode` | virtual | decompiler | 6 | UPDATE (`comment`, `comment_placement`) | Filter by exact function-start `func_addr`; `addr` is NULL for a line with no address |
| `pseudocode_orphan_comments` | virtual | decompiler | 5 | UPDATE (`orphan_comment`, delete-only) | Filter by `func_addr` |
| `pseudocode_v_orphan_comment_groups` | virtual | decompiler | 4 | — | Grouped orphan triage; filter by `func_addr` after `LIMIT` discovery |
| `segments` | virtual | disassembly | 6 | INSERT/UPDATE/DELETE | UPDATE `start_addr` rebases, `end_addr` resizes; `bitness` (16/32/64) is set by INSERT only (default: the database's) |
| `shortest_path` | virtual (TVF) | xrefs | 3 | — | `from_addr` HIDDEN, `to_addr` HIDDEN, `max_depth` HIDDEN → step, func_addr, func_name |
| `signatures` | virtual | disassembly | 6 | INSERT (`name`: applies) / DELETE (planned only) | The FLIRT signature list: `idx`, `name`, `title`, `state` (`applied`/`current`/`planned`), `matches`, `optlibs`. INSERT returns once analysis applied it; an applied signature cannot be deleted (roll back a checkpoint) |
| `available_signatures` | virtual | disassembly | 7 | — | `.sig` files IDA would find for this processor: `name`, `title`, `path`, `source` (`idausr`/`idasgn`/`idadir`), `is_startup`, `modules`, `in_list` |
| `strings` | virtual | data | 10 | — | Use `rebuild_strings()` first; `COUNT(*)` uses optimized count path |
| `undo_state` | virtual | annotations | 5 | — | One row: `next_undo_label`, `next_redo_label` (IDA's own labels, GUI steps included), `redo_safe`, `last_rollback_steps`, `last_rollback_foreign` |
| `types` | virtual | types | 18 | INSERT/UPDATE/DELETE | Writable: `name`, `folder_path`, `is_fixed` (struct freeze offsets), `is_bitmask` (enum bitmask), `size` (fixed-struct total via set_struct_size / enum width via set_nbytes); `full_path` read-only; pushdown on `ordinal`/`name` (exact) and `name LIKE 'prefix%'` — avoid `name LIKE '%substr%'` / unfiltered scans on large IDBs |
| `types_enum_values` | virtual | types | 7 | INSERT/UPDATE/DELETE | Writable: `value_name`, `value`, `comment`; filter by `type_ordinal`; value edits preserve the enum local type ordinal |
| `types_func_args` | virtual | types | 22 | — | Filter by `type_ordinal` |
| `types_members` | virtual | types | 19 | INSERT/UPDATE/DELETE | Writable: `member_name`, `member_type`, `offset`, `offset_bits`, `comment`; read-only `is_gap` flags IDA gap placeholders; filter by `type_ordinal`; DELETE is non-collapsing on **any** struct (leaves a gap, preserving the following members' offsets — like IDA's Undefine) and INSERT at a gap offset absorbs it; to compact/repack set `is_fixed` 1→0; refinements preserve the parent local type ordinal and dependent `member_type_ordinal` references |
| `struct_member_xrefs` | virtual | types | 19 | — | Cross-references TO a struct/union member; requires a filter on `type_ordinal`, `type_name`, or `member_id` (unfiltered errors); full nested-member expansion (dotted `member_path`); columns include `xref_from`, `xref_kind`, `function_name`, `instruction_text`, `operand_index` (the struct-offset or struct-typed stack-variable operand), `access_offset` (offset inside the member), `access_size` (NULL when the member's address is taken), `access_root_type` (the structure the access starts from) |
| `type_gaps` | virtual | types | 4 | — | Free byte ranges in a struct (`gap_offset`, `gap_size`) — where a new field can be inserted; requires a filter on `type_ordinal` or `type_name` |
| `binary` | virtual | connect | 3 | — | Key/value metadata: `(key, value, type)`, one row per fact, `type ∈ {string, hex, bool, int}` (family-canonical shape). Canonical keys `tool_name`, `tool_version`, `processor`, `filetype`, `image_base`, `entry_point`, `min_addr`, `max_addr`, `is_64bit`, `bits`, `endianness`, `filename`, `summary`, `md5`, `sha256`; idasql extras `idasql_version`, `entry_name`, `funcs_count`, `segments_count`, `names_count`, `strings_count` (orientation only — use `COUNT(*) FROM strings` for canonical string counts), `input_file_path`, `idb_path` |
| `xrefs` | virtual | xrefs | 6 | — | Filter by `to_addr` or `from_addr`; includes `from_func` (NULL for orphan sources; one row per owner for a shared tail); `kind` = call / jump / code or read / write / offset / text / info / data; real refs only — ordinary fall-through flow edges are excluded on every path |
| `netnode_kv` | virtual | storage | 2 | INSERT/UPDATE/DELETE | O(1) key lookup |
| `ctree_labels` | virtual | decompiler | 6 | UPDATE (`name`) | Filter by exact function-start `func_addr`; `item_addr` NULL when the item has none |
| `decompiler_splits` | virtual | decompiler | 3 | INSERT (`addr`, `piece_size`; `func_addr` optional) / UPDATE (`piece_size`) / DELETE (unsplits) | Hex-Rays "Split expression" settings: `func_addr`, `addr` (the merged instruction), `piece_size` (1/2/4/8 bytes). Stored as IDA's own Split expression stores it; reads no pseudocode, so a full scan is cheap; filter by `func_addr` to read one function. IDA 9.0-9.4 only, and split data in an unrecognised format is refused (see Runtime Notes) |
| `sqlite_schema` | table | connect | 5 | — | |

## Views

| Surface | Owner Skill | Cols | Notes |
|---------|-------------|------|-------|
| `callees` | xrefs | 4 | |
| `callers` | xrefs | 4 | |
| `ctree_v_assignments` | decompiler | 11 | Filter by `func_addr` |
| `ctree_v_call_chains` | decompiler | 3 | |
| `ctree_v_calls` | decompiler | 8 | Filter by `func_addr` |
| `ctree_v_indirect_calls` | decompiler | 10 | Filter by `func_addr` |
| `ctree_v_calls_in_ifs` | decompiler | 9 | Filter by `func_addr` |
| `ctree_v_calls_in_loops` | decompiler | 9 | Filter by `func_addr` |
| `ctree_v_comparisons` | decompiler | 10 | Filter by `func_addr` |
| `ctree_v_derefs` | decompiler | 7 | Filter by `func_addr` |
| `ctree_v_ifs` | decompiler | 30 | Filter by `func_addr` |
| `ctree_v_leaf_funcs` | decompiler | 2 | |
| `ctree_v_loops` | decompiler | 30 | Filter by `func_addr` |
| `ctree_v_returns` | decompiler | 14 | Filter by `func_addr` |
| `ctree_v_signed_ops` | decompiler | 30 | Filter by `func_addr` |
| `disasm_v_call_chains` | disassembly | 3 | |
| `disasm_v_calls_in_loops` | disassembly | 8 | |
| `disasm_v_funcs_with_loops` | disassembly | 3 | |
| `disasm_v_leaf_funcs` | disassembly | 2 | |
| `func_summary` | analysis | 17 | One triage row per function, decompiler-free: size, chunk_count, block_count, edge_count, cyclomatic, call_sites_out, callees, call_sites_in, callers, loop_count, switch_count, data_reads, data_writes, frame_size, uses_chkstk. `WHERE func_addr = X` costs one function |
| `ir_ops` | decompiler | 8 | Canonical low-IR over `microcode`: `func_addr`, `seq`, `addr`, `op` (canonical or NULL), `native_op` (native mnemonic), `is_ssa` (0), passthrough `maturity`, returned `stage` classification. Filter by exact function-start `func_addr` (+ exact `maturity`); `stage` does not select a lift rung |
| `ir_operands` | decompiler | 8 | Portable default-maturity (`lvars`) projection of `microcode_operands`: `func_addr`, `op_seq`, `operand_index`, `role`, `kind` (5-kind or NULL), `text`, `value`, `size`; its fixed eight-column cross-tool schema has no maturity coordinate, so join only to default-maturity `ir_ops` on `func_addr` + `op_seq = seq`. For a non-default rung, join native `microcode` to `microcode_operands` on `func_addr` + `op_seq = seq` + `maturity` |
| `ir_maturities` | decompiler | 5 | Lifting ladder advertised per tool: `maturity`, `stage`, `ordinal`, `is_default`, `is_ssa` (idasql = 8 rungs, `lvars` default, none SSA) |
| `ir_v_calls` / `ir_v_mem_writes` / `ir_v_mem_reads` / `ir_v_branches` / `ir_v_arith` | decompiler | 4 | Portable four-column low-IR semantic views over default-maturity `microcode` (`func_addr`, `seq`, `addr`, `op`); classify the op stream. Filter by `func_addr` |
| `string_refs` | xrefs | 6 | string_addr, string_value, string_length, ref_addr, func_addr, func_name |
| `types_v_enums` | types | 18 | |
| `types_v_funcs` | types | 18 | |
| `types_v_inheritance` | types | 5 | derived_ordinal, derived_name, base_type_name, base_ordinal, base_offset |
| `types_v_structs` | types | 18 | |
| `types_v_typedefs` | types | 18 | |
| `types_v_unions` | types | 18 | |

## Runtime Notes

- Some builds expose additional surfaces (e.g., `netnode_kv`) not present in every runtime.
- `ida_config` depends on where it runs: `idagui.cfg` keys are `writable = 1` only in the GUI plugin, `hexrays.cfg` keys only when the decompiler is loaded, and the row set follows the database's processor and the IDA version's option files.
- `decompiler_splits` exists wherever the decompiler does, and reads and writes on IDA 9.0-9.4 only (the versions its stored form was checked on); on another version every read and write fails with that reason. Split data in a form it does not recognise is refused, never rewritten.
- `checkpoints` needs IDA 9.0 SP1 or later (IDA 9.0 GA cannot report its undo labels; there INSERT/UPDATE and `auto_checkpoint = 'statement'` fail with that reason). Checkpoints last for the database session (they survive `save_database()`, not closing the database).
- `import idasql` (SQL from IDAPython) exists wherever IDAPython does; idasql itself never links Python, and without IDAPython every surface here is unchanged. See the `idapython` skill.
- Deep links (`deep_links`, `deep_link_parse`, `ida_open_link()`, the `enable_deep_link_navigation` setting) exist only in builds for IDA 9.4 or later. Absent from `pragma_table_list` means this build predates them: emit no links.
- When a surface is absent in `pragma_table_list`, treat it as runtime-optional.
- Prefer object-table `folder_path` columns for normal organization workflows: `funcs`, `types`, `names`, `imports`, `bookmarks`, `breakpoints`, and `local_type_bookmarks`. Use `dirtree_entries` for raw tree inspection and `dirtree_folders` for empty-folder lifecycle.
- Folder writes accept relative `/` paths and reject `.`/`..`, duplicate separators, backslashes, non-empty folder deletes, and folder renames whose destination already exists.
- `dirtree_entries` is read-only. Recursive folder delete and recovery/link primitives are intentionally not part of the SQL surface.
- **High addresses (>= 2^63).** Every `addr`-like column holds an address at or above `0x8000000000000000` as a negative INTEGER, and every table returns and orders such rows the way SQLite does: `ORDER BY addr` lists the high half first. Write those addresses as hex literals or the negative decimal, never as a decimal >= 2^63 (a REAL that matches nothing). `addr >= <high hex>` also includes the low half; the high half alone is `addr BETWEEN <high hex> AND -1`. `byte_search`'s hidden `start_addr` / `end_addr` are unsigned scan bounds. `-1` (BADADDR) is never an address: the top is `0xFFFFFFFFFFFFFFFE`, and `segments` rejects an `end_addr` of `-1`. The disassembly and data skills carry the examples.

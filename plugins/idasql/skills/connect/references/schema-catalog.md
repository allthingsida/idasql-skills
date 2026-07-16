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
| `bytes` | virtual | data / debugger | 8 (+ hidden `start_addr`, `n`) | UPDATE (`value`/`word`/`dword`/`qword`) / DELETE (revert patch) | Pure mapped-byte rows; filter by `addr` (point), `WHERE start_addr = X AND n = N` (bounded read; `start_addr` is a separate hidden input so predicates on `addr` stay enforceable), or tight `addr` ranges; `WHERE is_patched = 1` enumerates patches fast. Bulk hex: `hex(blob_concat(value))`. Bulk BLOB: `blob_concat(value)`. |
| `byte_search` | virtual | data | 8 (+ hidden `pattern`, `start_addr`, `end_addr`, `max_results`) | — | Requires `WHERE pattern = '<IDA byte pattern>'`; optional bounds via hidden columns or `addr` range predicates; outputs `addr`, `matched_hex`, `matched_bytes`, `size` |
| `call_graph` | virtual (TVF) | xrefs | 4 | — | `start` HIDDEN, `direction` HIDDEN, `max_depth` HIDDEN → func_addr, func_name, depth, parent_addr |
| `cfg_edges` | virtual | disassembly | 4 | — | Filter by `func_addr` (filter_eq pushdown) |
| `comments` | virtual | annotations | 3 | INSERT/UPDATE/DELETE | |
| `ctree` | virtual | decompiler | 30 | — | Filter by `func_addr` — generator |
| `ctree_call_args` | virtual | decompiler | 16 | — | Filter by `func_addr` — generator |
| `ctree_lvars` | virtual | decompiler | 12 | UPDATE (`name`, `type`, `comment`) | Filter by `func_addr` |
| `data_refs` | virtual | xrefs | 5 | — | Cached table of non-code xrefs with containing function info |
| `db_info` | virtual | disassembly | 3 | — | |
| `dirtree_entries` | virtual | annotations / disassembly / types | 11 | — | Raw IDA dirtree listing for `funcs`, `local_types`, `names`, `imports`, `idaplace_bookmarks`, `bpts`, `ltypes_bookmarks`; push down `tree`, `path`, `path LIKE`, `parent_path`, `inode`, `is_dir`, `is_file` |
| `dirtree_folders` | virtual | annotations / types | 3 | INSERT / UPDATE (`path`) / DELETE for all standard dirtrees | Empty folder lifecycle for `funcs`, `local_types`, `names`, `imports`, `idaplace_bookmarks`, `bpts`, `ltypes_bookmarks`; DELETE removes only empty folders |
| `disasm_calls` | virtual | disassembly | 5 | UPDATE (`callee_type`) | Filter by `func_addr` — generator; `addr` identifies call-site writes |
| `disasm_loops` | virtual | disassembly | 6 | — | |
| `entries` | virtual | disassembly | 3 | — | |
| `fchunks` | virtual | disassembly | 6 | — | |
| `fixups` | virtual | disassembly | 4 | — | |
| `funcs` | virtual | disassembly / annotations | 17 | INSERT/UPDATE/DELETE | Writable: `name`, `prototype`, `comment`, `rpt_comment`, `flags`, `folder_path`; `full_path` is read-only |
| `function_chunks` | virtual | disassembly | 5 | — | Cached table; one row per function chunk |
| `grep` | virtual | grep | 7 | — | Requires `pattern` |
| `heads` | virtual | disassembly | 5 | — | Optimized `addr =` and address range/order navigation |
| `hidden_ranges` | virtual | disassembly | 8 | — | |
| `ida_info` | virtual | disassembly | 3 | — | |
| `imports` | virtual | xrefs | 7 | UPDATE (`folder_path`) | Import folder moves do not change module/name/ordinal |
| `local_type_bookmarks` | virtual | types / annotations | 7 | INSERT (`ordinal`,`description`), UPDATE (`description`,`folder_path`), DELETE | Enumerates the `bookmarks_t` store; INSERT marks a bookmark at a local-type ordinal. Folder moves require an already-linked bookmark |
| `instructions` | virtual | disassembly | 70 | UPDATE (format_spec) / DELETE | Filter by `func_addr` |
| `instruction_operands` | virtual | disassembly | 11 | — | Structured decoded operands; filter by `addr` for one instruction or `func_addr` for a function |
| `local_types` | virtual | types | 6 | — | |
| `mappings` | virtual | disassembly | 3 | — | |
| `names` | virtual | disassembly | 6 | INSERT/UPDATE/DELETE | Writable: `name`, `folder_path`; `full_path` is read-only |
| `problems` | virtual | disassembly | 4 | — | |
| `runtime_settings` | virtual | connect | 4 | — | Read-only discovery view over the `PRAGMA idasql.*` runtime controls: `(key, value, type, scope)`, one row per setting. Shared keys `query_timeout_ms`, `queue_admission_timeout_ms`, `max_queue`, `hints_enabled`, `timeout_stack_depth`, `max_timeout_stack_depth` (scope `common`), `timeout_push`, `timeout_pop` (scope `action`); idasql-only `enable_idapython`, `idapython_output_max` (scope `idasql`). `type ∈ {int, bool}`. Values track PRAGMA writes; change a setting via `PRAGMA idasql.<key> = <value>` |
| `pseudocode` | virtual | decompiler | 6 | UPDATE (`comment`, `comment_placement`) | Filter by `func_addr` |
| `pseudocode_orphan_comments` | virtual | decompiler | 5 | UPDATE (`orphan_comment`, delete-only) | Filter by `func_addr` |
| `pseudocode_v_orphan_comment_groups` | virtual | decompiler | 4 | — | Grouped orphan triage; filter by `func_addr` after `LIMIT` discovery |
| `segments` | virtual | disassembly | 5 | INSERT/UPDATE/DELETE | UPDATE `start_addr` rebases, `end_addr` resizes |
| `shortest_path` | virtual (TVF) | xrefs | 3 | — | `from_addr` HIDDEN, `to_addr` HIDDEN, `max_depth` HIDDEN → step, func_addr, func_name |
| `signatures` | virtual | disassembly | 4 | — | |
| `strings` | virtual | data | 10 | — | Use `rebuild_strings()` first; `COUNT(*)` uses optimized count path |
| `types` | virtual | types | 18 | INSERT/UPDATE/DELETE | Writable: `name`, `folder_path`, `is_fixed` (struct freeze offsets), `is_bitmask` (enum bitmask), `size` (fixed-struct total via set_struct_size / enum width via set_nbytes); `full_path` read-only; pushdown on `ordinal`/`name` (exact) and `name LIKE 'prefix%'` — avoid `name LIKE '%substr%'` / unfiltered scans on large IDBs |
| `types_enum_values` | virtual | types | 7 | INSERT/UPDATE/DELETE | Writable: `value_name`, `value`, `comment`; filter by `type_ordinal`; value edits preserve the enum local type ordinal |
| `types_func_args` | virtual | types | 22 | — | Filter by `type_ordinal` |
| `types_members` | virtual | types | 19 | INSERT/UPDATE/DELETE | Writable: `member_name`, `member_type`, `offset`, `offset_bits`, `comment`; read-only `is_gap` flags IDA gap placeholders; filter by `type_ordinal`; DELETE is non-collapsing on **any** struct (leaves a gap, preserving the following members' offsets — like IDA's Undefine) and INSERT at a gap offset absorbs it; to compact/repack set `is_fixed` 1→0; refinements preserve the parent local type ordinal and dependent `member_type_ordinal` references |
| `struct_member_xrefs` | virtual | types | 18 | — | Cross-references TO a struct/union member; requires a filter on `type_ordinal`, `type_name`, or `member_id` (unfiltered errors); full nested-member expansion (dotted `member_path`); columns include `xref_from`, `xref_kind`, `function_name`, `instruction_text`, `access_offset/size` (best-effort) |
| `type_gaps` | virtual | types | 4 | — | Free byte ranges in a struct (`gap_offset`, `gap_size`) — where a new field can be inserted; requires a filter on `type_ordinal` or `type_name` |
| `binary` | virtual | connect | 3 | — | Key/value metadata: `(key, value, type)`, one row per fact, `type ∈ {string, hex, bool, int}` (family-canonical shape). Canonical keys `tool_name`, `tool_version`, `processor`, `filetype`, `image_base`, `entry_point`, `min_addr`, `max_addr`, `is_64bit`, `bits`, `endianness`, `filename`, `summary`, `md5`, `sha256`; idasql extras `idasql_version`, `entry_name`, `funcs_count`, `segments_count`, `names_count`, `strings_count` (orientation only — use `COUNT(*) FROM strings` for canonical string counts), `input_file_path`, `idb_path` |
| `xrefs` | virtual | xrefs | 5 | — | Filter by `to_addr` or `from_addr`; includes `from_func` (NULL for orphan sources); real refs only — ordinary fall-through flow edges are excluded on every path |
| `netnode_kv` | virtual | storage | 2 | INSERT/UPDATE/DELETE | O(1) key lookup |
| `ctree_labels` | virtual | decompiler | 6 | UPDATE (`name`) | Filter by `func_addr` |
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
| `string_refs` | xrefs | 6 | string_addr, string_value, string_length, ref_addr, func_addr, func_name |
| `types_v_enums` | types | 18 | |
| `types_v_funcs` | types | 18 | |
| `types_v_inheritance` | types | 5 | derived_ordinal, derived_name, base_type_name, base_ordinal, base_offset |
| `types_v_structs` | types | 18 | |
| `types_v_typedefs` | types | 18 | |
| `types_v_unions` | types | 18 | |

## Runtime Notes

- Some builds expose additional surfaces (e.g., `netnode_kv`) not present in every runtime.
- When a surface is absent in `pragma_table_list`, treat it as runtime-optional.
- Prefer object-table `folder_path` columns for normal organization workflows: `funcs`, `types`, `names`, `imports`, `bookmarks`, `breakpoints`, and `local_type_bookmarks`. Use `dirtree_entries` for raw tree inspection and `dirtree_folders` for empty-folder lifecycle.
- Folder writes accept relative `/` paths and reject `.`/`..`, duplicate separators, backslashes, non-empty folder deletes, and folder renames whose destination already exists.
- `dirtree_entries` is read-only. Recursive folder delete and recovery/link primitives are intentionally not part of the SQL surface.

# SQL Surface Catalog

Compact owner-mapping index for idasql surfaces. For column details, use `PRAGMA table_xinfo(<surface>)` at runtime.

Manual refresh procedure:
1. `SELECT schema, name, type, ncol FROM pragma_table_list WHERE schema='main' ORDER BY type, name;`
2. `PRAGMA table_xinfo(<surface>);`
3. Update owner mapping here when new surfaces appear.

## Tables

| Surface | Kind | Owner Skill | Cols | Writable | Notes |
|---------|------|-------------|------|----------|-------|
| `blocks` | virtual | disassembly | 4 | — | Filter by `func_ea` |
| `bookmarks` | virtual | annotations | 3 | INSERT/UPDATE/DELETE | |
| `breakpoints` | virtual | debugger | 19 | INSERT/UPDATE/DELETE | |
| `bytes` | virtual | disassembly | 6 | UPDATE (`value`) | Filter by `ea` — maps entire address space |
| `comments` | virtual | annotations | 3 | INSERT/UPDATE/DELETE | |
| `ctree` | virtual | decompiler | 28 | — | Filter by `func_addr` — generator |
| `ctree_call_args` | virtual | decompiler | 16 | — | Filter by `func_addr` — generator |
| `ctree_lvars` | virtual | decompiler | 12 | UPDATE (`name`, `type`, `comment`) | Filter by `func_addr` |
| `db_info` | virtual | disassembly | 3 | — | |
| `disasm_calls` | virtual | disassembly | 4 | — | Filter by `func_addr` — generator |
| `disasm_loops` | virtual | disassembly | 6 | — | |
| `entries` | virtual | disassembly | 3 | — | |
| `fchunks` | virtual | disassembly | 6 | — | |
| `fixups` | virtual | disassembly | 4 | — | |
| `funcs` | virtual | disassembly | 13 | INSERT/UPDATE/DELETE | |
| `grep` | virtual | xrefs | 7 | — | Requires `pattern` |
| `heads` | virtual | disassembly | 5 | — | Filter by address range |
| `hidden_ranges` | virtual | disassembly | 8 | — | |
| `ida_info` | virtual | disassembly | 3 | — | |
| `imports` | virtual | xrefs | 5 | — | |
| `instructions` | virtual | disassembly | 70 | UPDATE (format_spec) / DELETE | Filter by `func_addr` |
| `local_types` | virtual | types | 6 | — | |
| `mappings` | virtual | disassembly | 3 | — | |
| `names` | virtual | disassembly | 4 | INSERT/UPDATE/DELETE | |
| `patched_bytes` | virtual | debugger | 4 | — | |
| `problems` | virtual | disassembly | 4 | — | |
| `pseudocode` | virtual | decompiler | 6 | UPDATE (`comment`, `comment_placement`) | Filter by `func_addr` |
| `segments` | virtual | disassembly | 5 | INSERT/UPDATE/DELETE | |
| `signatures` | virtual | disassembly | 4 | — | |
| `strings` | virtual | data | 10 | — | Use `rebuild_strings()` first |
| `types` | virtual | types | 14 | INSERT/UPDATE/DELETE | |
| `types_enum_values` | virtual | types | 7 | INSERT/UPDATE/DELETE | Filter by `type_ordinal` |
| `types_func_args` | virtual | types | 22 | — | Filter by `type_ordinal` |
| `types_members` | virtual | types | 18 | INSERT/UPDATE/DELETE | Filter by `type_ordinal` |
| `welcome` | virtual | connect | 10 | — | |
| `xrefs` | virtual | xrefs | 4 | — | Filter by `to_ea` or `from_ea` |
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
| `ctree_v_calls_in_ifs` | decompiler | 9 | Filter by `func_addr` |
| `ctree_v_calls_in_loops` | decompiler | 9 | Filter by `func_addr` |
| `ctree_v_comparisons` | decompiler | 10 | Filter by `func_addr` |
| `ctree_v_derefs` | decompiler | 7 | Filter by `func_addr` |
| `ctree_v_ifs` | decompiler | 28 | Filter by `func_addr` |
| `ctree_v_leaf_funcs` | decompiler | 2 | |
| `ctree_v_loops` | decompiler | 28 | Filter by `func_addr` |
| `ctree_v_returns` | decompiler | 14 | Filter by `func_addr` |
| `ctree_v_signed_ops` | decompiler | 28 | Filter by `func_addr` |
| `disasm_v_call_chains` | disassembly | 3 | |
| `disasm_v_calls_in_loops` | disassembly | 8 | |
| `disasm_v_funcs_with_loops` | disassembly | 3 | |
| `disasm_v_leaf_funcs` | disassembly | 2 | |
| `types_v_enums` | types | 14 | |
| `types_v_funcs` | types | 14 | |
| `types_v_structs` | types | 14 | |
| `types_v_typedefs` | types | 14 | |
| `types_v_unions` | types | 14 | |

## Runtime Notes

- Some builds expose additional surfaces (e.g., `netnode_kv`) not present in every runtime.
- When a surface is absent in `pragma_table_list`, treat it as runtime-optional.

# Legacy Prompt Parity Matrix

Legacy source: `idasql_agent.md` (single-file agent guide).

This matrix tracks where legacy strengths now live in modular skills.

| Legacy capability | New primary location | Secondary location(s) | Status |
|-------------------|----------------------|------------------------|--------|
| CLI startup and server lifecycle | `connect` | `decompiler`, `idapython` | Preserved |
| Binary orientation (`welcome`, key counts) | `connect` | `ui-context` | Preserved |
| Core concepts (addresses/functions/xrefs/segments/decompiler) | `connect` | `disassembly`, `xrefs`, `decompiler` | Preserved |
| Full table/view schema awareness | `connect/references/schema-catalog.md` | all owner skills | Strengthened |
| Quick start triage flows | `analysis` | `connect` | Preserved |
| Natural language to SQL examples | `analysis` | `disassembly`, `decompiler`, `xrefs`, `types` | Preserved |
| Cross-reference and call graph workflows | `xrefs` | `analysis`, `disassembly` | Preserved |
| Decompiler mutation workflows | `decompiler` | `annotations` | Preserved |
| Type system editing and classification | `types` | `decompiler`, `annotations` | Preserved |
| Annotation/editing patterns | `annotations` | `re-source`, `decompiler` | Preserved |
| Byte/patching + breakpoints | `debugger` | `data`, `disassembly` | Preserved |
| String and byte search workflows | `data` | `analysis`, `xrefs` | Preserved |
| SQL function catalog and signatures | `functions` | domain skills | Preserved |
| Advanced SQL patterns (CTE/window/subqueries) | `analysis` | `xrefs`, `disassembly` | Preserved |
| Performance guardrails | `connect` | `decompiler`, `xrefs`, `disassembly` | Strengthened |
| Mandatory mutation loop | `connect` | `annotations`, `decompiler` | Strengthened |
| Error/fallback guidance | `connect` | domain skills | Strengthened |
| Single-agent narrative throughline | `connect` routing + contracts | all major skills | Strengthened |

## Notes
- A capability is "Preserved" when scope is maintained in at least one primary skill.
- A capability is "Strengthened" when modular structure now adds explicit ownership, schema guidance, or deterministic routing contracts.

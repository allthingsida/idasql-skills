# IDASQL Skills Optimization Checklist

Use this checklist before merging major skill rewrites.

## 1) Routing Clarity
- [ ] `connect` includes explicit intent -> skill routing matrix.
- [ ] Every major skill includes trigger-intent examples in plain user language.
- [ ] Cross-skill handoff instructions are present and unambiguous.

## 2) Anti-Guessing Behavior
- [ ] Schema introspection guidance appears in `connect` and in high-risk skills.
- [ ] Long-tail surfaces reference canonical schema catalog.
- [ ] Decompiler and instruction-heavy queries emphasize required constraints.

## 3) In-Context Learning Strength
- [ ] Every major skill includes warm-start query sequence (`Do This First`).
- [ ] Every major skill includes NL -> SQL examples (not only raw SQL snippets).
- [ ] Examples include interpretation hints (how to read output and decide next step).

## 4) Mutation Safety
- [ ] Mandatory mutation loop is present or referenced.
- [ ] Write examples use precise keys (`func_addr`, `ea`, `idx`, `slot`, etc.).
- [ ] Verify/refresh steps exist after mutation examples.

## 5) Legacy Parity
- [ ] Legacy prompt sections are mapped in `legacy-parity-matrix.md`.
- [ ] No critical legacy capability is marked missing.
- [ ] Fragmented capabilities have a clear ownership destination.

## 6) Performance and Failure Handling
- [ ] Skills include timeout/empty-result fallback patterns.
- [ ] Skills document high-cost query constraints and safe alternatives.
- [ ] HTTP/REPL/CLI startup patterns remain deterministic.

## 7) Consistency
- [ ] Terminology is consistent across skills (`ea`, `func_addr`, `start_ea`, etc.).
- [ ] Table/view names match live SQL metadata.
- [ ] Cross-links between related skills are accurate.

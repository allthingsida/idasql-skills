# Disassembly Examples Reference

## Advanced Disassembly Patterns (CTEs)

CTE notes for predictable performance:
- Seed CTEs with constrained function sets (for example: `funcs ORDER BY size DESC LIMIT N`).
- Keep `func_addr`/`func_addr` constraints inside inner CTEs when touching `instructions`/`blocks`.
- For mutation workflows, run candidate CTEs first, then execute bounded `DELETE`/`make_code*` using those results.
- Avoid recursive/unbounded CTEs over unconstrained `instructions` on large IDBs.

### Instruction mnemonic frequency across functions (complexity fingerprinting)

Fingerprint functions by their instruction mix -- useful for finding similar functions or detecting obfuscation:

```sql
-- Top 10 most "complex" functions by unique mnemonic count
WITH mnemonic_profile AS (
    SELECT func_addr,
           (SELECT name FROM funcs WHERE addr = func_addr) AS func_name,
           COUNT(DISTINCT mnemonic) AS unique_mnemonics,
           COUNT(*) AS total_insns
    FROM instructions
    WHERE func_addr IN (SELECT addr FROM funcs ORDER BY size DESC LIMIT 50)
    GROUP BY func_addr
)
SELECT func_name,
       printf('0x%X', func_addr) AS addr,
       unique_mnemonics,
       total_insns,
       ROUND(unique_mnemonics * 1.0 / total_insns, 3) AS diversity_ratio
FROM mnemonic_profile
ORDER BY unique_mnemonics DESC
LIMIT 10;
```

### Functions with the most unique callee APIs (dispatch/hub detection)

Hub functions that call many different APIs are often dispatchers, init routines, or main loops:

```sql
-- Functions calling the most distinct callees
WITH callee_counts AS (
    SELECT func_addr,
           (SELECT name FROM funcs WHERE addr = func_addr) AS func_name,
           COUNT(DISTINCT callee_name) AS unique_callees
    FROM disasm_calls
    WHERE callee_name IS NOT NULL AND callee_name != ''
    GROUP BY func_addr
)
SELECT func_name,
       printf('0x%X', func_addr) AS addr,
       unique_callees
FROM callee_counts
ORDER BY unique_callees DESC
LIMIT 15;
```

### Function complexity score (blocks x instructions x calls)

A composite complexity metric combining structural and call complexity:

```sql
-- Composite complexity score
WITH block_counts AS (
    SELECT func_addr AS addr, COUNT(*) AS n_blocks
    FROM blocks GROUP BY func_addr
),
insn_counts AS (
    SELECT func_addr AS addr, COUNT(*) AS n_insns
    FROM instructions
    WHERE func_addr IN (SELECT addr FROM funcs ORDER BY size DESC LIMIT 100)
    GROUP BY func_addr
),
call_counts AS (
    SELECT func_addr AS addr, COUNT(*) AS n_calls
    FROM disasm_calls GROUP BY func_addr
)
SELECT (SELECT name FROM funcs WHERE addr = i.addr) AS name,
       printf('0x%X', i.addr) AS addr,
       COALESCE(b.n_blocks, 0) AS blocks,
       i.n_insns AS insns,
       COALESCE(c.n_calls, 0) AS calls,
       COALESCE(b.n_blocks, 1) * i.n_insns * (1 + COALESCE(c.n_calls, 0)) AS complexity
FROM insn_counts i
LEFT JOIN block_counts b ON b.addr = i.addr
LEFT JOIN call_counts c ON c.addr = i.addr
ORDER BY complexity DESC
LIMIT 15;
```

### Rank functions by instruction count per segment

Find the largest functions in each segment -- useful for triage:

```sql
-- Top 3 largest functions per segment (by instruction count)
WITH ranked AS (
    SELECT s.name AS seg,
           f.name,
           f.size,
           ROW_NUMBER() OVER (PARTITION BY s.start_addr ORDER BY f.size DESC) AS rank
    FROM funcs f
    JOIN segments s
      ON f.addr >= s.start_addr
     AND f.addr < s.end_addr
)
SELECT seg, name, size
FROM ranked
WHERE rank <= 3
ORDER BY seg, rank;
```

### Name library code first (FLIRT), then triage the rest

Runtime and library functions recognized by a FLIRT signature are named and flagged as
library code (`FUNC_LIB`, `flags & 4`); leave them out of triage.

```sql
-- Which signatures are applied, and which could apply?
SELECT name, title, state, matches FROM signatures;
SELECT name, title, modules FROM available_signatures WHERE NOT is_startup AND NOT in_list
  AND name LIKE 'vc32%' AND title LIKE 'Microsoft VisualC%';

-- Apply one, then compare library code with the program's own
INSERT INTO signatures(name) VALUES ('vc32rtf');
SELECT (flags & 4) != 0 AS library, COUNT(*) AS functions, SUM(size) AS bytes
FROM funcs GROUP BY library;

-- Triage anchors among the program's own functions only
SELECT name, printf('0x%X', addr) AS addr, size FROM funcs
WHERE NOT (flags & 4) ORDER BY size DESC LIMIT 20;
```

## In-Context Learning Playbooks

Use these prompt-to-SQL templates in agent sessions:

```sql
-- 1) Safe instruction lifecycle at one EA
-- (fails with "re-created by auto-analysis" when other code still flows into it)
SELECT addr, disasm FROM instructions WHERE addr = 0x401000;
DELETE FROM instructions WHERE addr = 0x401000;
SELECT make_code(0x401000);
SELECT addr, disasm FROM instructions WHERE addr = 0x401000;

-- 2) Range lifecycle with verification
SELECT COUNT(*) FROM instructions WHERE addr >= 0x401000 AND addr < 0x401100;
DELETE FROM instructions WHERE addr >= 0x401000 AND addr < 0x401100;
SELECT make_code_range(0x401000, 0x401100);
SELECT COUNT(*) FROM instructions WHERE addr >= 0x401000 AND addr < 0x401100;

-- 3) Function-scoped lifecycle
SELECT COUNT(*) FROM instructions WHERE func_addr = 0x401000;
DELETE FROM instructions WHERE func_addr = 0x401000;
-- recreate every chunk (end_addr would cover the entry chunk only)
SELECT SUM(make_code_range(chunk_start, chunk_end)) AS created FROM function_chunks WHERE func_addr = 0x401000;
SELECT COUNT(*) FROM instructions WHERE func_addr = 0x401000;
```

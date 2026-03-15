# Disassembly Examples Reference

## Advanced Disassembly Patterns (CTEs)

CTE notes for predictable performance:
- Seed CTEs with constrained function sets (for example: `funcs ORDER BY size DESC LIMIT N`).
- Keep `func_addr`/`func_ea` constraints inside inner CTEs when touching `instructions`/`blocks`.
- For mutation workflows, run candidate CTEs first, then execute bounded `DELETE`/`make_code*` using those results.
- Avoid recursive/unbounded CTEs over unconstrained `instructions` on large IDBs.

### Instruction mnemonic frequency across functions (complexity fingerprinting)

Fingerprint functions by their instruction mix -- useful for finding similar functions or detecting obfuscation:

```sql
-- Top 10 most "complex" functions by unique mnemonic count
WITH mnemonic_profile AS (
    SELECT func_addr,
           func_at(func_addr) AS func_name,
           COUNT(DISTINCT mnemonic) AS unique_mnemonics,
           COUNT(*) AS total_insns
    FROM instructions
    WHERE func_addr IN (SELECT address FROM funcs ORDER BY size DESC LIMIT 50)
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
           func_at(func_addr) AS func_name,
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
    SELECT func_ea AS addr, COUNT(*) AS n_blocks
    FROM blocks GROUP BY func_ea
),
insn_counts AS (
    SELECT func_addr AS addr, COUNT(*) AS n_insns
    FROM instructions
    WHERE func_addr IN (SELECT address FROM funcs ORDER BY size DESC LIMIT 100)
    GROUP BY func_addr
),
call_counts AS (
    SELECT func_addr AS addr, COUNT(*) AS n_calls
    FROM disasm_calls GROUP BY func_addr
)
SELECT func_at(i.addr) AS name,
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
    SELECT segment_at(f.address) AS seg,
           f.name,
           f.size,
           ROW_NUMBER() OVER (PARTITION BY segment_at(f.address) ORDER BY f.size DESC) AS rank
    FROM funcs f
)
SELECT seg, name, size
FROM ranked
WHERE rank <= 3
ORDER BY seg, rank;
```

## In-Context Learning Playbooks

Use these prompt-to-SQL templates in agent sessions:

```sql
-- 1) Safe instruction lifecycle at one EA
SELECT address, disasm FROM instructions WHERE address = 0x401000;
DELETE FROM instructions WHERE address = 0x401000;
SELECT make_code(0x401000);
SELECT address, disasm FROM instructions WHERE address = 0x401000;

-- 2) Range lifecycle with verification
SELECT COUNT(*) FROM instructions WHERE address >= 0x401000 AND address < 0x401100;
DELETE FROM instructions WHERE address >= 0x401000 AND address < 0x401100;
SELECT make_code_range(0x401000, 0x401100);
SELECT COUNT(*) FROM instructions WHERE address >= 0x401000 AND address < 0x401100;

-- 3) Function-scoped lifecycle
SELECT COUNT(*) FROM instructions WHERE func_addr = 0x401000;
DELETE FROM instructions WHERE func_addr = 0x401000;
SELECT make_code_range(address, end_ea) FROM funcs WHERE address = 0x401000;
SELECT COUNT(*) FROM instructions WHERE func_addr = 0x401000;
```

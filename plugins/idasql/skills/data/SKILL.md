---
name: data
description: "Query IDA strings, bytes, and binary data. Use when asked to search strings, find byte patterns, rebuild string tables, or analyze binary content."
allowed-tools:
  - Bash
  - Read
  - Glob
  - Grep
---

---

## Trigger Intents

Use this skill when user asks to:
- search strings/bytes/patterns quickly
- map string evidence to code usage
- investigate raw data-level indicators (IOCs, constants, signatures)

Route to:
- `xrefs` for relationship expansion from matched addresses
- `analysis` for triage synthesis from data signals
- `debugger` when findings should drive patch/breakpoint actions

---

## Do This First (Warm-Start Sequence)

```sql
-- 1) Validate string availability
SELECT string_count();

-- 2) Sample high-value strings
SELECT content, printf('0x%X', address) AS addr
FROM strings
WHERE length >= 8
ORDER BY length DESC
LIMIT 40;

-- 3) If expected strings are missing, rebuild once
SELECT rebuild_strings();
```

Interpretation guidance:
- Strings are often quickest behavioral clues; pivot to `xrefs` immediately for execution context.
- For opcode/pattern hunts, prefer `search_bytes()` over full instruction scans.

---

## Failure and Recovery

- No strings or unexpectedly low count:
  - Run `rebuild_strings()` and validate with `string_count()`.
- Too many false positives:
  - Increase specificity (`LIKE`, regex-like pattern narrowing, module/function join filters).
- Byte pattern search too broad:
  - Restrict by range or post-filter via `func_start(...)`.
- Need named functions, labels, structs, or members instead of string contents:
  - Use `grep`, not `strings` or `search_bytes()`.

---

## Handoff Patterns

1. `data` -> `xrefs` to convert data hits into code paths/functions.
2. `data` -> `analysis` for risk scoring and campaign-level insight.
3. `data` -> `debugger` for actionable patch/watchpoint setup.

---

## strings
String literals found in the binary. IDA maintains a cached string list that can be configured.

| Column | Type | Description |
|--------|------|-------------|
| `address` | INT | String address |
| `length` | INT | String length |
| `type` | INT | String type (raw encoding bits) |
| `type_name` | TEXT | Type name: ascii, utf16, utf32 |
| `width` | INT | Char width (0=1-byte, 1=2-byte, 2=4-byte) |
| `width_name` | TEXT | Width name: 1-byte, 2-byte, 4-byte |
| `layout` | INT | String layout (0=null-terminated, 1-3=pascal) |
| `layout_name` | TEXT | Layout name: termchr, pascal1, pascal2, pascal4 |
| `encoding` | INT | Encoding index (0=default) |
| `content` | TEXT | String content (the actual text — not `value` or `text`) |

**String Type Encoding:**
IDA stores string type as a 32-bit value:
- Bits 0-1: Width (0=1B/ASCII, 1=2B/UTF-16, 2=4B/UTF-32)
- Bits 2-7: Layout (0=TERMCHR, 1=PASCAL1, 2=PASCAL2, 3=PASCAL4)
- Bits 8-15: term1 (first termination character)
- Bits 16-23: term2 (second termination character)
- Bits 24-31: encoding index

```sql
-- Find error messages
SELECT content, printf('0x%X', address) as addr FROM strings WHERE content LIKE '%error%';

-- ASCII strings only
SELECT * FROM strings WHERE type_name = 'ascii';

-- UTF-16 strings (common in Windows)
SELECT * FROM strings WHERE type_name = 'utf16';

-- Count strings by type
SELECT type_name, layout_name, COUNT(*) as count
FROM strings GROUP BY type_name, layout_name ORDER BY count DESC;
```

**Important:** For new analysis (exe/dll), strings are auto-built. For existing databases (i64/idb), strings are already saved. If you see 0 strings unexpectedly, run `SELECT rebuild_strings()` once to rebuild the list. See String List Functions section below.

---

## String References (explicit join pattern)

Use `strings + xrefs + funcs` directly. This is the canonical pattern.

```sql
-- Find call sites/functions referencing error-like strings
SELECT
    s.content as string_value,
    printf('0x%X', x.from_ea) as ref_addr,
    func_at(x.from_ea) as func_name
FROM strings s
JOIN xrefs x ON x.to_ea = s.address
WHERE s.content LIKE '%error%' OR s.content LIKE '%fail%'
ORDER BY func_name, ref_addr;

-- Functions with most string references
SELECT
    func_at(x.from_ea) as func_name,
    COUNT(*) as string_refs
FROM strings s
JOIN xrefs x ON x.to_ea = s.address
GROUP BY func_name
ORDER BY string_refs DESC
LIMIT 10;
```

---

## SQL Functions — Byte Access (Read-Only)

| Function | Description |
|----------|-------------|
| `bytes(addr, n)` | Read `n` bytes as hex string |
| `bytes_raw(addr, n)` | Read `n` bytes as BLOB |

---

## SQL Functions — Binary Search

| Function | Description |
|----------|-------------|
| `search_bytes(pattern)` | Find all matches, returns JSON array |
| `search_bytes(pattern, start, end)` | Search within address range |
| `search_first(pattern)` | First match address (or NULL) |
| `search_first(pattern, start, end)` | First match in range |

**Pattern syntax (IDA native):**
- `"48 8B 05"` - Exact bytes (hex, space-separated)
- `"48 ? 05"` or `"48 ?? 05"` - `?` = any byte wildcard (whole byte only)
- `"(01 02 03)"` - Alternatives (match any of these bytes)

**Note:** Nibble wildcards and regex are not supported in byte patterns.

**Example:**
```sql
-- Find all matches for a pattern
SELECT search_bytes('48 8B ? 00');

-- Parse JSON results
SELECT json_extract(value, '$.address') as addr
FROM json_each(search_bytes('48 89 ?'))
LIMIT 10;

-- First match only
SELECT printf('0x%llX', search_first('CC CC CC'));

-- Search with alternatives
SELECT search_bytes('E8 (01 02 03 04)');
```

**Optimization Pattern: Find functions using specific instruction**

To answer "How many functions use RDTSC instruction?" efficiently:
```sql
-- Count unique functions containing RDTSC (opcode: 0F 31)
SELECT COUNT(DISTINCT func_start(json_extract(value, '$.address'))) as count
FROM json_each(search_bytes('0F 31'))
WHERE func_start(json_extract(value, '$.address')) IS NOT NULL;

-- List those functions with names
SELECT DISTINCT
    func_start(json_extract(value, '$.address')) as func_ea,
    name_at(func_start(json_extract(value, '$.address'))) as func_name
FROM json_each(search_bytes('0F 31'))
WHERE func_start(json_extract(value, '$.address')) IS NOT NULL;
```

This is **much faster** than scanning all disassembly lines because:
- `search_bytes()` uses native binary search
- `func_start()` is O(1) lookup in IDA's function index

---

## Choose the Right Search Surface

- Use `grep` for named entities such as functions, labels, structs, enums, and members.
- Use `strings` when the user is searching literal string contents inside the binary.
- Use `search_bytes()` when the target is a raw byte or opcode pattern.

---

## SQL Functions — String List Functions

IDA maintains a cached list of strings. Use `rebuild_strings()` to detect and cache strings.

| Function | Description |
|----------|-------------|
| `rebuild_strings()` | Rebuild with ASCII + UTF-16, minlen 5 (default) |
| `rebuild_strings(minlen)` | Rebuild with custom minimum length |
| `rebuild_strings(minlen, types)` | Rebuild with custom length and type mask |
| `string_count()` | Get current string count (no rebuild) |

**Type mask values:**
- `1` = ASCII only (STRTYPE_C)
- `2` = UTF-16 only (STRTYPE_C_16)
- `4` = UTF-32 only (STRTYPE_C_32)
- `3` = ASCII + UTF-16 (default)
- `7` = All types

```sql
-- Check current string count
SELECT string_count();

-- Rebuild with defaults (ASCII + UTF-16, minlen 5)
SELECT rebuild_strings();

-- Rebuild with shorter minimum length
SELECT rebuild_strings(4);

-- Rebuild with specific types
SELECT rebuild_strings(5, 1);   -- ASCII only
SELECT rebuild_strings(5, 7);   -- All types (ASCII + UTF-16 + UTF-32)

-- Typical workflow: rebuild then query
SELECT rebuild_strings();
SELECT * FROM strings WHERE content LIKE '%error%';
```

**IMPORTANT - Agent Behavior for String Queries:**
When the user asks about strings (e.g., "show me the strings", "what strings are in this binary"):
1. First run `SELECT rebuild_strings()` to ensure strings are detected
2. Then query the `strings` table

The `rebuild_strings()` function configures IDA's string detection with sensible defaults (ASCII + UTF-16, minimum length 5) and rebuilds the string list. This ensures the user gets results even if the database had no prior string analysis.

---

## Performance Rules

| Table/Function | Architecture | Notes |
|----------------|-------------|-------|
| `strings` | Cached | Rebuilt on demand via `rebuild_strings()`; fast once cached |
| `search_bytes()` | Native binary search | Much faster than iterating instructions table |
| `bytes()` | Direct read | O(1) per address, no table overhead |

**Key rules:**
- Always call `rebuild_strings()` before the first string query on a new database or after making code/data changes that may create new strings.
- `search_bytes()` uses IDA's native binary search engine — it scans raw bytes directly, bypassing the instruction decoder. For "find functions containing opcode X", `search_bytes()` + `func_start()` is orders of magnitude faster than scanning the `instructions` table.
- `strings` table is a snapshot of the cached string list. If IDA's analysis creates new strings after your initial query, call `rebuild_strings()` again.
- For cross-referencing strings with functions, the `strings + xrefs + funcs` JOIN pattern is canonical — IDA's xref index makes the JOIN fast.

---

## Advanced Data Patterns (CTEs)

### Security-relevant string triage

Categorize strings by security relevance for rapid threat assessment:

```sql
-- Categorize strings by security relevance
SELECT rebuild_strings();

WITH categorized AS (
    SELECT address, content,
        CASE
            WHEN content LIKE '%password%' OR content LIKE '%passwd%' OR content LIKE '%secret%'
                THEN 'credential'
            WHEN content LIKE '%http://%' OR content LIKE '%https://%' OR content LIKE '%ftp://%'
                THEN 'url'
            WHEN content LIKE '%error%' OR content LIKE '%fail%' OR content LIKE '%exception%'
                THEN 'error'
            WHEN content LIKE '%debug%' OR content LIKE '%trace%' OR content LIKE '%assert%'
                THEN 'debug'
            WHEN content LIKE '%.exe%' OR content LIKE '%.dll%' OR content LIKE '%.sys%'
                THEN 'file_path'
            WHEN content LIKE '%HKEY_%' OR content LIKE '%SOFTWARE\\%'
                THEN 'registry'
            ELSE 'other'
        END AS category
    FROM strings
    WHERE length >= 5
)
SELECT category, COUNT(*) AS count,
       GROUP_CONCAT(SUBSTR(content, 1, 60), ' | ') AS samples
FROM categorized
WHERE category != 'other'
GROUP BY category
ORDER BY count DESC;
```

### Combine string references with function size for suspicion scoring

Functions referencing security-relevant strings AND having significant size are high-priority targets:

```sql
-- Suspicious functions: reference interesting strings AND are non-trivial
WITH interesting_strings AS (
    SELECT address, content FROM strings
    WHERE content LIKE '%password%' OR content LIKE '%encrypt%'
       OR content LIKE '%decrypt%' OR content LIKE '%http%'
       OR content LIKE '%socket%' OR content LIKE '%connect%'
),
string_funcs AS (
    SELECT DISTINCT func_start(x.from_ea) AS func_addr,
           s.content AS matched_string
    FROM interesting_strings s
    JOIN xrefs x ON x.to_ea = s.address
    WHERE func_start(x.from_ea) IS NOT NULL
)
SELECT func_at(sf.func_addr) AS func_name,
       printf('0x%X', sf.func_addr) AS addr,
       f.size AS func_size,
       GROUP_CONCAT(sf.matched_string, ' | ') AS strings_referenced
FROM string_funcs sf
JOIN funcs f ON f.address = sf.func_addr
GROUP BY sf.func_addr
ORDER BY f.size DESC
LIMIT 20;
```

### Find functions referencing both crypto-related and network-related strings

Cross-category correlation for identifying data exfiltration or C2 communication:

```sql
-- Functions touching both crypto and network strings
WITH crypto_refs AS (
    SELECT DISTINCT func_start(x.from_ea) AS func_addr
    FROM strings s JOIN xrefs x ON x.to_ea = s.address
    WHERE s.content LIKE '%crypt%' OR s.content LIKE '%aes%'
       OR s.content LIKE '%cipher%' OR s.content LIKE '%hash%'
),
network_refs AS (
    SELECT DISTINCT func_start(x.from_ea) AS func_addr
    FROM strings s JOIN xrefs x ON x.to_ea = s.address
    WHERE s.content LIKE '%socket%' OR s.content LIKE '%connect%'
       OR s.content LIKE '%send%' OR s.content LIKE '%recv%'
       OR s.content LIKE '%http%'
)
SELECT func_at(c.func_addr) AS func_name,
       printf('0x%X', c.func_addr) AS addr
FROM crypto_refs c
JOIN network_refs n ON n.func_addr = c.func_addr;

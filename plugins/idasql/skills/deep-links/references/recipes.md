# Deep-link recipes

Each recipe feeds one address per row into `deep_links` through a JOIN, so it scales
to thousands of rows. Without a `view`, a link opens code: pseudocode for a function
(disassembly without a decompiler), disassembly for everything else with an address.

## Functions

```sql
-- the ten biggest functions, pseudocode links
SELECT f.name, printf('0x%X', f.addr) AS addr, f.size, dl.uri
FROM funcs f
JOIN deep_links dl ON dl.resource = 'functions' AND dl.addr = f.addr AND dl.view = 'pseudocode'
ORDER BY f.size DESC LIMIT 10;

-- all four views of one function (disasm, graph, pseudocode, the Functions list);
-- CROSS JOIN keeps the view list outer, so deep_links always receives a view
WITH v(view) AS (VALUES ('disasm'), ('graph'), ('pseudocode'), ('functions'))
SELECT v.view, dl.uri
FROM v CROSS JOIN deep_links dl
WHERE dl.resource = 'functions' AND dl.view = v.view
  AND dl.addr = (SELECT addr FROM funcs WHERE name = 'main');
```

## Callers of a function

```sql
SELECT c.caller_name, printf('0x%X', c.caller_addr) AS site, dl.uri
FROM callers c
JOIN deep_links dl ON dl.resource = 'functions' AND dl.addr = c.caller_addr AND dl.view = 'disasm'
WHERE c.func_addr = (SELECT addr FROM funcs WHERE name = 'CreateFileW_wrapper');
```

`view = 'disasm'` with the call-site address opens IDA on the calling instruction,
not at the start of the function.

## Strings and where they are used

```sql
SELECT s.content, printf('0x%X', s.addr) AS addr, dl.uri
FROM strings s
JOIN deep_links dl ON dl.resource = 'strings' AND dl.addr = s.addr
WHERE s.content LIKE '%cmd.exe%';
```

The string list can include text IDA has not defined as a string item. For those,
`deep_links` returns `valid = 0` with "No string at address", and IDA would refuse the
link. Open them as addresses instead:

```sql
SELECT s.content,
       COALESCE(st.uri, ad.uri) AS link
FROM strings s
JOIN deep_links st ON st.resource = 'strings'   AND st.addr = s.addr
JOIN deep_links ad ON ad.resource = 'addresses' AND ad.addr = s.addr
WHERE s.content LIKE '%cmd.exe%';
```

## Imports, names, segments, bookmarks

```sql
SELECT i.name, dl.uri FROM imports i
JOIN deep_links dl ON dl.resource = 'imports' AND dl.addr = i.addr LIMIT 20;

SELECT n.name, dl.uri FROM names n
JOIN deep_links dl ON dl.resource = 'names' AND dl.addr = n.addr LIMIT 20;

SELECT g.name, dl.uri FROM segments g
JOIN deep_links dl ON dl.resource = 'segments' AND dl.addr = g.start_addr;

SELECT b.description, dl.uri FROM bookmarks b
JOIN deep_links dl ON dl.resource = 'bookmarks' AND dl.addr = b.addr AND dl.view = 'disasm';
```

Check column names with `PRAGMA table_info(<table>)` if a table differs on your build.

## Local types

```sql
SELECT t.name, dl.uri
FROM types t
JOIN deep_links dl ON dl.resource = 'types' AND dl.name = t.name
WHERE t.name LIKE '%CONTEXT%';
```

## A given list of addresses

`WHERE addr IN (...)` does not reach `deep_links`. JOIN against the list:

```sql
WITH picks(a) AS (VALUES (0x401130), (0x401330), (0x4016E4))
SELECT printf('0x%X', p.a) AS addr, dl.uri
FROM picks p
JOIN deep_links dl ON dl.resource = 'functions' AND dl.addr = p.a AND dl.view = 'disasm';
```

## Identity beside the links

When two databases may share a name, report which one the links are for:

```sql
SELECT key, value FROM binary WHERE key IN ('filename', 'idb_path', 'sha256');
```

## Render

Take each row's label and `uri`, and write them as a markdown link
(`[sub_401130](ida:///...)`) in a table or list, outside any code block. A link
inside a code block or in backticks is not clickable.

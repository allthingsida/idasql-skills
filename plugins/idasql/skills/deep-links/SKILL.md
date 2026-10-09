---
name: deep-links
description: "Make IDA answers clickable with ida:// deep links. Use whenever an answer names functions, addresses, strings, types or imports the user may want to open in IDA; whenever query results carry a deep_links uri or an ida:// link, including rows the user pasted and wants turned into a table or list to click through; when asked for links, to 'show me' or 'open it in IDA'; or to jump the user's IDA to a result. Each link is written [exact_name](uri), outside code."
allowed-tools:
  - Bash
  - Read
  - Glob
  - Grep
---

## The Contract (read first, apply every time)

1. **Generate links only with SQL** — from `deep_links`, alone or joined to the
   table you are listing. Never assemble an `ida://` string by hand: the table
   validates the target and produces exactly IDA's own format. If `deep_links` is
   not in `pragma_table_list`, this idasql build has no deep links (they need
   IDA 9.4): emit none.
2. **Write each link as `[label](uri)`** in prose, a list or a table cell. The label is
   the exact symbol from the same row (`sub_401130`, `aCmdExe`), never a paraphrase and
   never "click here". Escape `[`, `]` and `|` in a label with a backslash. **Never**
   put a link inside a code block or backticks — it will not be clickable there. Keep
   the address beside it as plain text (`0x401130`).
3. **Links open code.** Function links use `view = 'pseudocode'` (`'disasm'` when there
   is no decompiler); addresses, call sites, strings, imports and data use `'disasm'`.
   Open a list window (`'functions'`, `'strings'`, `'imports'`) only when the user asks
   for that window. Left out, `view` defaults to exactly this.
4. **Link what the answer is about** — the functions, strings or types you name. Do not
   link every row of a large dump.
5. **Navigate only when asked** ("open it", "jump there", "show me in IDA"):
   `SELECT ida_open_link(...)`, or `idasql link open -- '<uri>'` from a shell. When
   you cannot run it yourself, hand the user that exact command with the uri filled in;
   a link to click is a fine extra, not the answer.
6. When two databases may share a basename, say which one: add `sha256` or `idb_path`
   from the `binary` table.

---

## Answer Template

| Function | Address | Why it matters |
|---|---|---|
| [sub_401130](ida:///sample.exe.i64/functions?rva=0x1130&view=pseudocode&idb_path=C%3A%5Cwork%5Csample.exe.i64) | 0x401130 | opens the mixer device |
| [_main](ida:///sample.exe.i64/functions?rva=0x1330&view=pseudocode&idb_path=C%3A%5Cwork%5Csample.exe.i64) | 0x401330 | entry point |

Click a name to open it in IDA.

When no handler is registered, add one line: "Run `idasql link register` once to make
these links open IDA."

---

## Generate

One link: give the resource and its target in the WHERE clause.

```sql
SELECT uri FROM deep_links
WHERE resource = 'functions' AND addr = 0x401130 AND view = 'pseudocode';
```

Many links: JOIN, so each row feeds its own address in.

```sql
SELECT f.name, f.addr, dl.uri
FROM funcs f
JOIN deep_links dl ON dl.resource = 'functions' AND dl.addr = f.addr AND dl.view = 'pseudocode'
ORDER BY f.size DESC LIMIT 10;
```

Every view of one function (`CROSS JOIN` keeps the list of views outer, so each row
hands `deep_links` its view), or local types by name:

```sql
WITH v(view) AS (VALUES ('disasm'), ('graph'), ('pseudocode'), ('functions'))
SELECT v.view, dl.uri
FROM v CROSS JOIN deep_links dl
WHERE dl.resource = 'functions' AND dl.view = v.view
  AND dl.addr = (SELECT addr FROM funcs WHERE name = 'main');

SELECT t.name, dl.uri
FROM types t
JOIN deep_links dl ON dl.resource = 'types' AND dl.name = t.name
WHERE t.name LIKE 'tag%';
```

More recipes (strings, imports, names, segments, bookmarks, a given list of addresses):
[references/recipes.md](references/recipes.md).

`deep_links` rows:

| Column | Meaning |
|---|---|
| `uri` | the `ida://` link: IDA's Copy Link format, plus the database's full path last (`&idb_path=`; IDA ignores it, a click uses it to launch IDA on the right file) |
| `resource` | `functions` `addresses` `strings` `segments` `names` `imports` `exports` `types` `bookmarks` |
| `addr` / `rva` | the target (give one); the other is computed from `image_base` |
| `name` | the type name, for `resource = 'types'` |
| `view` | `disasm` `graph` `pseudocode` `hexdump` or a list view; omitted = `pseudocode` for functions (`disasm` without a decompiler), `disasm` for other addresses, `types` for types |
| `idb_name` | defaults to this database; `''` makes a link for "whatever IDA has open" |
| `source` | optional named source (leave it out unless the user uses sources) |
| `addr_mode` | `auto` (default: `rva=`), `rva`, or `ea` (absolute `ea=`) |
| `valid` / `diagnostic` | `0` + IDA's reason when the target does not resolve (then `uri` is NULL) |

An unconstrained `SELECT * FROM deep_links` is refused: always give the resource and
its target. `IN (...)` lists do not reach the table; JOIN against a list instead
(see recipes).

---

## Navigate (only when asked)

```sql
-- inside IDA (plugin HTTP/MCP): opens right there. The idasql CLI returns an error
-- until the gate below is on and an IDA 9.4 has the database open.
SELECT ida_open_link(dl.uri) FROM deep_links dl
WHERE dl.resource = 'functions' AND dl.addr = 0x401130 AND dl.view = 'pseudocode';
```

- In the IDA plugin the gate `enable_deep_link_navigation` is on. Under the `idasql`
  CLI it is off; turn it on with
  `UPDATE runtime_settings SET value='1' WHERE key='enable_deep_link_navigation'`.
  The CLI then steers the running IDA 9.4 that has the database open.
- From a shell: `idasql link open -- 'ida:///...'` (quote it: `&` separates commands
  in every shell; in `cmd.exe` use double quotes). If no IDA has the database open,
  `link open` starts IDA on it, waits for analysis, then navigates.
- `idasql link list` shows the running IDA 9.4 instances and their databases.

---

## Failure and recovery

| Symptom | Cause | Do |
|---|---|---|
| `deep_links` missing from `pragma_table_list` | idasql built for IDA before 9.4 | emit no links; say deep links need IDA 9.4 |
| `valid = 0`, "No function at address" | the address is not in a function | use `resource = 'addresses'` |
| "is not compatible with entity type" | view not allowed for that resource | use the resource's `default_view` / `allowed_views` |
| `ida_open_link`: "navigation is disabled" | CLI gate off | run the `UPDATE` above, if the user wants navigation |
| "no running IDA 9.4 instance has X open" | nothing to steer | `idasql link open` (launches), or tell the user |
| "several IDA instances have a matching database open" | same basename twice, neither the link's exact file | `--pid`, or close one |
| "IDA PID N does not answer and may have this database open" | an IDA is busy (modal dialog, long script) | retry, `--pid`, or `--launch-anyway` |
| "... looks open in another IDA (... .id0 exists)" | the database's unpacked `.id0` is next to it | close that IDA, or `--launch-anyway` |
| "not an IDA database (.i64/.idb)" | the link names some other file | fix the link; only `.i64` / `.idb` are launched |
| "link contains control characters" | a decoded part holds `%00`, `%0A`, ... | the link is malformed; emit it from `deep_links` |
| "database path contains Unicode direction controls" | the path could display as another file | the link is not trustworthy; do not open it |
| "... cannot be verified (elevated?)" | that IDA runs elevated or as another user | open it from an idasql running as the same user |
| clicking does nothing | no handler for the scheme | [references/handler-setup.md](references/handler-setup.md) |

---

## See also

- [references/uri-grammar.md](references/uri-grammar.md) — the link format, resources and views
- [references/handler-setup.md](references/handler-setup.md) — `idasql link register`, coexisting with hcli, links without a handler
- `connect` — the Output Contract these links belong to
- `ui-context` — what the user is looking at now (the other direction)

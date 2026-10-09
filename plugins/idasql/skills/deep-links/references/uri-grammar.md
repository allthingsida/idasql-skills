# Deep-link URI grammar (IDA 9.4)

```
ida://<source>/<idb-name>/<resource>?<target>&view=<view>[&idb_path=<path>]
```

- This is IDA's own format: IDA's **Jump to link**, `open_ida_link()` and hcli all read
  it. `deep_links` adds one parameter last, `idb_path=`, the database's full path. IDA
  ignores it; idasql's click handler uses it to find the file and launch IDA on it.
  Everything before it is byte-identical to IDA's Copy Link.
- `<source>` is optional (`ida:///...` has an empty one). IDA ignores it; it names a
  folder of databases for tools that launch IDA.
- `<idb-name>` is the database file name, extension included (`sample.exe.i64`). Leave
  it out (`ida:///functions?...`) to mean "whatever database IDA has open". IDA warns
  on a mismatch and navigates anyway, so a link for the wrong database can land
  somewhere wrong: include it.
- `<target>` is `rva=` (offset from the image base), `ea=` (absolute address) or, for
  types, `name=`. Give exactly one. Numbers are hex with `0x`, decimal, or octal with a
  leading `0`, the way IDA reads them.
- `view=` picks the window. `deep_links` always writes one: when you give none, it picks
  code (`pseudocode` for functions, `disasm` without a decompiler and for every other
  resource with an address, `types` for types) rather than IDA's own defaults, which are
  mostly list windows.

Encoding:

- **The database name** is percent-encoded: only `A-Z a-z 0-9 - . _ ~` stay literal,
  and every other byte becomes `%XX` with upper-case hex.
- **A type name** keeps the URL delimiters `: / ? [ ] @ ! $ ' ( ) * + , ; =` literal,
  because IDA does not decode their escapes there. `tagX::$1A2B` has to travel as
  written, or IDA reports "Type not found". Every other byte becomes `%XX`, so
  `std::vector<int>` becomes `std::vector%3Cint%3E`.
- **A type name that contains `&`, `#` or `%`** cannot be linked at all. `deep_links`
  returns `valid = 0` for it.

A link never contains a space, `<`, `>` or `|`. Function and address links never
contain parentheses or brackets either. A type link can, when the name does (they
are balanced in real names). Copy the `uri` column as it is; never re-encode it.

Numbers are formatted the way IDA's Copy Link formats them: lower-case `0x`, upper-case
digits, no padding (`rva=0x16E4`).

## Resources and views

IDA's own defaults (used when a link has no `view=`) are in the third column;
`deep_links` fills in the code view instead, as above.

| Resource | Target must be | IDA's default view | Allowed views |
|---|---|---|---|
| `functions` | inside a function (the exact address is kept) | `functions` | `disasm` `graph` `hexdump` `pseudocode` `functions` |
| `addresses` | a mapped address | `disasm` | `disasm` `hexdump` |
| `strings` | the head of a string | `strings` | `disasm` `hexdump` `strings` |
| `segments` | inside a segment | `segments` | `disasm` `hexdump` `segments` |
| `names` | a named address | `names` | `disasm` `hexdump` `names` |
| `imports` | an import entry | `imports` | `disasm` `hexdump` `imports` |
| `exports` | an entry point | `exports` | `disasm` `hexdump` `exports` |
| `types` | a local type, by `name=` | `types` | `types` |
| `bookmarks` | a mapped address | `disasm` | `disasm` `graph` `hexdump` `pseudocode` `bookmarks` |

`deep_links` checks the functions, addresses, strings, segments, names and types
targets before it emits a link, with IDA's own reason in `diagnostic`. IDA checks
imports, exports and bookmarks when the link is opened.

## Examples

```
ida:///sample.exe.i64/functions?rva=0x1130&view=pseudocode
ida:///sample.exe.i64/functions?ea=0x401130&view=graph
ida:///sample.exe.i64/strings?rva=0x3010&view=strings
ida:///sample.exe.i64/types?name=tagMIXERCAPSA&view=types
ida:///functions?rva=0x1130&view=disasm
ida:///sample.exe.i64/functions?rva=0x1130&view=pseudocode&idb_path=C%3A%5Cwork%5Csample.exe.i64
```

Parse any of these back with
`SELECT * FROM deep_link_parse WHERE uri = '...'`; the `ida_uri` column is the exact
string that would be handed to IDA (the link without `idb_path`). A link whose decoded
parts hold a control character (`%00`, `%0A`, ...) or a
types name IDA cannot receive (`&`, `#`, `%`), is invalid.

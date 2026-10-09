# Making deep links open IDA

A deep link needs something to open it. There are three ways, and none of them needs
hcli.

## 1. Register idasql as the click handler (recommended)

```bash
idasql link register            # idasql handles ida:// links
idasql link status              # who handles ida:// here
```

- Clicking an `ida://` link (in a terminal that supports hyperlinks, a browser, a chat
  window) runs `idasql link open` with it.
- If an IDA 9.4 has the database open, IDA jumps there. Otherwise idasql starts IDA on
  the database (`.i64` or `.idb` only), waits for auto-analysis (`--timeout <seconds>`,
  1 to 3600), then jumps.
- It does not start a second IDA when a running instance does not answer (a modal
  dialog, a long script) or the database's unpacked `.id0` exists next to it; either
  means an IDA may already have it open. `idasql link open --launch-anyway` overrides.
- Only an IDA running as the same user, in the same logon session, is steered.
- Launching a database that is not under a configured source asks for confirmation
  first.
- To stop: `idasql link unregister`.

Registration is per user:
- Windows: `HKCU\Software\Classes\ida`.
- Linux: a `.desktop` entry plus `xdg-mime`.
- macOS: a small app bundle in `~/Applications`.

### If hcli (or another program) handled `ida://` before

The OS keeps one handler per scheme. `idasql link register` takes `ida://` over and
saves the handler it replaced; `idasql link status` shows it as the previous handler.
`idasql link unregister` puts that handler back exactly as it was. Unregistering never
removes another program's handler.

### Where launched databases are looked up

- A link from `deep_links` carries the database's full path (`&idb_path=`), so it
  needs no setup. IDA ignores that parameter.
- A link without it (one copied from IDA, say) names only the file. idasql looks for
  it under configured sources:

  ```bash
  idasql link source add malware-samples D:\idbs\malware
  idasql link source list
  idasql link config show                   # links.json in the user config dir
  idasql link --config D:\links.json open -- '...'   # another links.json: before the verb
  idasql link config ida "C:\IDA 9.4\ida.exe"   # only if ida is not next to idasql
  ```

- The link's exact `idb_path` wins. Only when that file is not on this machine does a
  running IDA with a database of the same name (a copy) take the link. A same-named
  database found more than once under the sources is refused with every match listed.

## 2. No handler: open links on request

```bash
idasql link open -- 'ida:///sample.exe.i64/functions?rva=0x1130&view=pseudocode'
```

Or, over a connection to the IDA plugin: `SELECT ida_open_link('...')`.

Quote the link: `&` separates commands in every shell. In `cmd.exe`, put it in double
quotes.

## 3. Inside IDA

Paste the link into **Jump → Jump to link**. The `uri` column works as it is.

## Making an agent use them by default

Two independent settings decide whether a link is clickable:
- Links render only as markdown `[label](uri)` written in the reply, never as a bare
  URL or inside code.
- Clicking needs a registered handler for `ida://`.

A line like this in a project's `CLAUDE.md` (or `AGENTS.md`) makes an agent use them
without being asked: "When idasql results name functions, strings or types, render
them as `[name](uri)` links from the `deep_links` table."

## Terminals decide whether a click goes through

A registered handler is not the whole story: the terminal (or the agent's own
renderer) chooses which link schemes it passes to the OS.

- **Windows Terminal** opens `ida://` links only after asking: "This link may lead to
  an unsafe location", with **Open anyway**. To skip the question, add the scheme to
  its settings (`settings.json`, top level):

  ```json
  "safeUriSchemes": ["ida"]
  ```

- **Claude Code's fullscreen renderer** handles link clicks itself and opens only
  web and a few app schemes, so a click on a deep link there does nothing. Its
  classic renderer hands the click to the terminal, which works as above.
- Where a click cannot go through, ask the agent to open the link
  (`idasql link open` or `ida_open_link`), or ask for the URI in a code block and
  paste it into IDA's **Jump to link**.

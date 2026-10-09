# Per-Turn Checkpoints for Agent Sessions

An agent that misreads a function during one turn writes wrong names, comments and types. The
harness can rewind the conversation; this rewinds the database with it. The `checkpoints` table is
described in the `annotations` skill; this page is the workflow around it.

## The hook script

[`../scripts/idasql_turn_checkpoint.py`](../scripts/idasql_turn_checkpoint.py) talks to a running
idasql HTTP server (`idasql -s db.i64 --http 8080`, or the plugin's `.http start`) through the
`checkpoints` table and the `undo_state` view. It needs only Python's standard library.

| Command | Effect |
|---------|--------|
| `checkpoint [--label L] [--hook]` | Create a checkpoint. Without a label: `turn N <time>`, plus `s=<session>` from the hook input |
| `rollback [--to LABEL \| --steps N]` | Undo back through a checkpoint (default: the newest live one). An unknown label undoes nothing |
| `redo [--steps N]` | Redo the next rolled-back checkpoint(s); refused once anything was written since the rollback |
| `list` | The session's checkpoints, newest first |
| `status` | Server status, live checkpoint count, IDA's next undo/redo labels, whether a redo is safe |
| `auto on\|off` | `auto_checkpoint`: a checkpoint per writing statement |

Configuration: `IDASQL_URL` (default `http://127.0.0.1:8080`) or `--url`; `IDASQL_TOKEN` or `--token`
when the server was started with a token.

With `--hook` the script reads the harness's hook JSON on stdin and uses only its session id; the
prompt text never reaches IDA. In hook mode it always exits 0, so a stopped server never blocks a
prompt (errors go to stderr).

## Install it as a prompt-submit hook

Copy the script somewhere stable, for example `~/.idasql/idasql_turn_checkpoint.py`.

Claude Code (`.claude/settings.json`):

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python \"$HOME/.idasql/idasql_turn_checkpoint.py\" checkpoint --hook",
            "timeout": 15
          }
        ]
      }
    ]
  }
}
```

GitHub Copilot CLI (`hooks.json`):

```json
{
  "version": 1,
  "hooks": {
    "userPromptSubmitted": [
      {
        "type": "command",
        "bash": "python3 \"$HOME/.idasql/idasql_turn_checkpoint.py\" checkpoint --hook",
        "powershell": "python \"$env:USERPROFILE\\.idasql\\idasql_turn_checkpoint.py\" checkpoint --hook",
        "env": { "IDASQL_URL": "http://127.0.0.1:8080" },
        "timeoutSec": 15
      }
    ]
  }
}
```

## Rewinding a turn

1. Rewind the conversation in the harness.
2. Roll the database back to the same turn:

   ```bash
   python idasql_turn_checkpoint.py list                 # find the turn
   python idasql_turn_checkpoint.py rollback --steps 2   # or --to "turn 7 2026-10-05T14:02:11"
   ```

3. Check what the rollback took: it reports how many IDA undo steps it performed and how many were
   not idasql's (edits made in the GUI or with IDAPython after that checkpoint are undone too).
4. Changed your mind before writing anything else: `redo`. Once anything was written, a redo is
   refused; IDA would re-apply the old step and drop the newer work.

The same in SQL:

```sql
SELECT seq, label, writes_since, state FROM checkpoints ORDER BY seq DESC;
UPDATE checkpoints SET state = 'undone' WHERE label = 'turn 7';
SELECT last_rollback_steps, last_rollback_foreign, redo_safe FROM undo_state;
UPDATE checkpoints SET state = 'live'
WHERE seq = (SELECT MIN(seq) FROM checkpoints WHERE state = 'undone');
```

## Undoing a FLIRT signature

IDA cannot unapply a signature, and `DELETE FROM signatures` refuses an applied one. A
checkpoint taken before the `INSERT` rolls the whole application back: the names, the
library flags and the list entry.

```sql
INSERT INTO checkpoints(label) VALUES ('before vc32rtf');
INSERT INTO signatures(name) VALUES ('vc32rtf');
SELECT COUNT(*) FROM funcs WHERE flags & 4;           -- what it named
UPDATE checkpoints SET state = 'undone' WHERE label = 'before vc32rtf';
```

## Limits

- Checkpoints are IDA undo points: they last for the database session (they survive
  `save_database()`, not closing the database). A one-shot `idasql -q` per turn has nothing to return
  to; keep one server for the conversation.
- IDA keeps a bounded undo history (`UNDO_MAXSIZE`, `UNDO_DEPTH` in `ida.cfg`; the oldest steps are
  dropped first). A rollback to a checkpoint IDA has dropped fails and changes nothing.
- Undo also reverts auto-analysis results produced after the checkpoint.
- `runtime_settings` and session-only `ida_config` keys (`persisted = 0`) are not rolled back.

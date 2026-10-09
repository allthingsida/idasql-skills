#!/usr/bin/env python3
"""idasql_turn_checkpoint.py: per-turn undo checkpoints for an idasql HTTP server.

An agent that hallucinates during a turn writes bad names, comments and types. A
conversation can be rewound; this rewinds the database with it. Run it as the
harness's prompt-submit hook so every turn starts with a checkpoint, then roll back
to any turn.

Talks to a running idasql HTTP server (`idasql -s db.i64 --http PORT`, or the IDA
plugin's `.http start`) through the `checkpoints` table and the `undo_state` view.
It needs nothing else: no IDAPython.

Commands:
    checkpoint   create a checkpoint (run it before each agent turn)
    rollback     undo everything back to (and including) a checkpoint
    redo         redo the next rolled-back checkpoint
    list         show the session's checkpoints
    status       show the server status and IDA's next undo/redo labels
    auto         auto_checkpoint on|off: a checkpoint per writing statement

Hook use (the harness's hook JSON arrives on stdin; only sessionId/session_id is
read, the prompt text never reaches IDA):
    Claude Code      UserPromptSubmit      python idasql_turn_checkpoint.py checkpoint --hook
    GitHub Copilot   userPromptSubmitted   (same command)
In hook mode the exit code is always 0, so a stopped idasql server never blocks
the prompt; errors go to stderr.

Configuration (environment or flags):
    IDASQL_URL     default http://127.0.0.1:8080
    IDASQL_TOKEN   optional bearer token (`.http start <port> <host> <token>`)

Checkpoints are IDA undo points: they survive save_database() but not closing the
database, so they need a long-lived session (the plugin, --http, --mcp).
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sys
import urllib.error
import urllib.request

DEFAULT_URL = "http://127.0.0.1:8080"
LABEL_PREFIX = "turn"


def sql_literal(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


class AuthError(RuntimeError):
    """The server refused the request's token (HTTP 401)."""


class Server:
    def __init__(self, url: str, token: str | None, timeout: float):
        self.url, self.token, self.timeout = url.rstrip("/"), token, timeout

    def _request(self, method: str, path: str, body: bytes | None = None) -> dict:
        req = urllib.request.Request(self.url + path, data=body, method=method)
        req.add_header("Content-Type", "text/plain; charset=utf-8")
        if self.token:
            req.add_header("Authorization", "Bearer " + self.token)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:  # a SQL error comes back as JSON too
            if exc.code == 401:
                raise AuthError(
                    f"{self.url} refused the request (HTTP 401 Unauthorized): "
                    + ("the token in IDASQL_TOKEN / --token is not the server's token"
                       if self.token else
                       "the server requires a token; set IDASQL_TOKEN or pass --token")) from None
            body = exc.read().decode("utf-8")
            try:
                return json.loads(body or "{}")
            except ValueError:
                raise RuntimeError(f"{self.url} answered HTTP {exc.code}: {body[:200]}") from None

    def status(self) -> dict:
        return self._request("GET", "/status")

    def rows(self, sql: str) -> list:
        """Rows of the last statement; RuntimeError carrying the SQL error otherwise."""
        env = self._request("POST", "/query", sql.encode("utf-8"))
        for result in env.get("results") or []:
            if not result.get("success", True):
                raise RuntimeError(result.get("error") or "query failed")
        if not env.get("success", False):
            raise RuntimeError(env.get("error") or json.dumps(env)[:300])
        return (env.get("results") or [{}])[-1].get("rows") or []

    def scalar(self, sql: str):
        rows = self.rows(sql)
        return rows[0][0] if rows else None

    def require_checkpoints(self) -> None:
        try:
            self.rows("SELECT 1 FROM checkpoints LIMIT 0")
        except AuthError:
            raise
        except RuntimeError as exc:
            raise RuntimeError("this idasql server has no checkpoints table "
                               f"(it needs idasql 0.0.19 or later): {exc}") from None


def cmd_checkpoint(srv: Server, args) -> int:
    session = ""
    if args.hook:
        try:
            payload = json.load(sys.stdin)
            session = str(payload.get("sessionId") or payload.get("session_id") or "")
        except Exception:  # noqa: BLE001 - never block the prompt
            pass
    srv.require_checkpoints()
    label = args.label
    if not label:
        turn = int(srv.scalar("SELECT COUNT(*) FROM checkpoints WHERE kind = 'user'") or 0) + 1
        stamp = _dt.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        label = f"{LABEL_PREFIX} {turn} {stamp}" + (f" s={session[:8]}" if session else "")
    srv.rows(f"INSERT INTO checkpoints(label) VALUES ({sql_literal(label)})")
    print(f"checkpoint: {label}")
    return 0


def cmd_rollback(srv: Server, args) -> int:
    srv.require_checkpoints()
    if args.to:
        label = args.to
        live = srv.scalar("SELECT COUNT(*) FROM checkpoints WHERE state = 'live' "
                          f"AND label = {sql_literal(label)}")
        if not int(live or 0):
            print(f"rollback refused: '{label}' is not a live checkpoint (see `list`); "
                  "nothing was undone", file=sys.stderr)
            return 1
    else:
        steps = args.steps or 1
        label = srv.scalar("SELECT label FROM checkpoints WHERE state = 'live' "
                           f"ORDER BY seq DESC LIMIT 1 OFFSET {steps - 1}")
        if label is None:
            print(f"rollback refused: fewer than {steps} live checkpoint(s)", file=sys.stderr)
            return 1
    try:
        srv.rows(f"UPDATE checkpoints SET state = 'undone' WHERE label = {sql_literal(label)}")
    except RuntimeError as exc:
        print(f"rollback refused: {exc}", file=sys.stderr)
        return 1
    steps, foreign = (int(v) for v in
                      srv.rows("SELECT last_rollback_steps, last_rollback_foreign FROM undo_state")[0])
    note = f", {foreign} of them not made by idasql (GUI or IDAPython edits)" if foreign else ""
    print(f"rolled back {steps} undo step(s){note}, through checkpoint: {label}")
    return 0


def cmd_redo(srv: Server, args) -> int:
    srv.require_checkpoints()
    for _ in range(args.steps or 1):
        label = srv.scalar("SELECT label FROM checkpoints WHERE state = 'undone' ORDER BY seq LIMIT 1")
        if label is None:
            print("nothing to redo", file=sys.stderr)
            return 1
        try:
            srv.rows(f"UPDATE checkpoints SET state = 'live' WHERE label = {sql_literal(label)}")
        except RuntimeError as exc:
            print(f"redo refused: {exc}", file=sys.stderr)
            return 1
        print(f"redone: {label}")
    return 0


def cmd_list(srv: Server, args) -> int:
    srv.require_checkpoints()
    for seq, label, kind, writes, state in srv.rows(
            "SELECT seq, label, kind, writes_since, state FROM checkpoints ORDER BY seq DESC"):
        print(f"{seq:>4}  {state:<6}  {kind:<4}  writes_since={writes:<5}  {label}")
    return 0


def cmd_status(srv: Server, args) -> int:
    print(json.dumps(srv.status(), indent=2))
    srv.require_checkpoints()
    undo, redo, safe, steps, foreign = srv.rows(
        "SELECT next_undo_label, next_redo_label, redo_safe, last_rollback_steps, "
        "last_rollback_foreign FROM undo_state")[0]
    live = srv.scalar("SELECT COUNT(*) FROM checkpoints WHERE state = 'live'")
    print(json.dumps({"live_checkpoints": int(live or 0), "next_undo": undo, "next_redo": redo,
                      "redo_safe": str(safe) == "1"}, indent=2))
    return 0


def cmd_auto(srv: Server, args) -> int:
    value = "statement" if args.state == "on" else "off"
    srv.rows(f"UPDATE runtime_settings SET value = '{value}' WHERE key = 'auto_checkpoint'")
    print(f"auto_checkpoint: {value}")
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Per-turn IDA undo checkpoints over idasql HTTP.")
    ap.add_argument("--url", default=os.environ.get("IDASQL_URL", DEFAULT_URL))
    ap.add_argument("--token", default=os.environ.get("IDASQL_TOKEN"))
    ap.add_argument("--timeout", type=float, default=float(os.environ.get("IDASQL_TIMEOUT", "10")))
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("checkpoint")
    p.add_argument("--label")
    p.add_argument("--hook", action="store_true",
                   help="hook mode: read the harness JSON on stdin; never fail the prompt")
    p = sub.add_parser("rollback")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--to", help="exact checkpoint label")
    g.add_argument("--steps", type=int, help="N-th most recent live checkpoint (default 1)")
    p = sub.add_parser("redo")
    p.add_argument("--steps", type=int, default=1)
    sub.add_parser("list")
    sub.add_parser("status")
    p = sub.add_parser("auto")
    p.add_argument("state", choices=("on", "off"))
    args = ap.parse_args(argv)

    srv = Server(args.url, args.token, args.timeout)
    handler = {"checkpoint": cmd_checkpoint, "rollback": cmd_rollback, "redo": cmd_redo,
               "list": cmd_list, "status": cmd_status, "auto": cmd_auto}[args.cmd]
    try:
        return handler(srv, args)
    except (urllib.error.URLError, OSError, RuntimeError, ValueError) as exc:
        print(f"idasql checkpoint: {exc}", file=sys.stderr)
        return 0 if getattr(args, "hook", False) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

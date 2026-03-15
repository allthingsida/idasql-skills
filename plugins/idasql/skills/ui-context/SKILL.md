---
name: ui-context
description: "Capture live IDA UI context. Use when the user references what's on screen, what's selected, or asks about the current view in IDA's GUI."
allowed-tools:
  - Bash
  - Read
  - Glob
  - Grep
---

---

## Primary Query

Use this function to capture active UI state:

```sql
SELECT get_ui_context_json();
```

Capture once per user question, then reuse that snapshot while answering.
Capture again only when the user asks to refresh/re-check, or when a new UI-referential question starts.

---

## Trigger Patterns

Use this skill for prompts like:
- "what am I looking at?"
- "what is on the screen?"
- "what's selected?"
- "look at what I'm doing"
- references such as "this", "here", "current", "selected", "that", "previous"

---

## Capture Policy

1. Call `get_ui_context_json()` before answering UI-referential prompts.
2. Extract view info: widget type/title and custom-view state.
3. Extract selection info when present: begin/end and preview text lines.
4. Extract code anchor info when present: address, function, segment.
5. If `has_address: false`, explain limits and do not invent code context.

---

## Temporal Reference Rules

- `this` / `here` / `current` / `selected`: capture a fresh snapshot for this question.
- `that` / `previous` / `earlier`: reuse the most recent snapshot in the same working flow.
- If the user says "refresh", capture a new snapshot immediately.

---

## Runtime Availability and Fallback

- `get_ui_context_json()` is plugin GUI runtime only.
- It is unavailable in idalib/CLI mode.
- When unavailable, state this clearly and continue with non-UI queries (explicit addresses/symbols, or DB-orientation queries).

`welcome` is database metadata only; it is not a UI context replacement.

---

## Response Template

Use this fixed shape after reading UI context:

- `What You Are Viewing`: widget/view summary.
- `What Is Selected`: selection range and preview (or "no active selection").
- `Code Context`: address/function/segment if available; otherwise mention non-address view.
- `Limits`: runtime constraints or missing fields affecting certainty.
- `Suggested Next Query`: one concrete follow-up command/query.

---

## Examples

### 1) "What am I looking at?"

```sql
SELECT get_ui_context_json();
```

Answer with the template fields above. Include focused widget title/type and current anchor address if present.

### 2) "Look at what I'm doing"

```sql
SELECT get_ui_context_json();
```

Summarize active view and selection first, then propose the next action tied to that context (for example, decompile current function).

### 3) "What's selected right now?"

```sql
SELECT get_ui_context_json();
```

Prioritize selection begin/end and preview text. Explicitly state when there is no active selection.

### 4) "Explain this function"

1. Capture UI context.
2. If function/address context exists, pivot to decompiler.

```sql
SELECT get_ui_context_json();
SELECT decompile(0x401000);
```

Replace `0x401000` with the captured function/address anchor.

### 5) Follow-up: "What about that function?"

Reuse the most recent snapshot from the same flow (do not auto-refresh unless asked), then continue analysis from that stored anchor.

### 6) Non-address view (for example Local Types chooser)

```sql
SELECT get_ui_context_json();
```

If `has_address: false`, report chooser selection details and state there is no code address anchor in this view.

### 7) Plugin API unavailable (CLI/idalib)

If `get_ui_context_json()` cannot run:

- state that UI context is unavailable in this runtime
- ask for explicit symbol/address or continue with non-UI alternatives (for example `SELECT * FROM welcome` for DB orientation)

---

## Guardrails

- Do not treat `welcome` output as UI context.
- Do not fabricate selection/address fields when absent.
- Do not recapture repeatedly in one answer unless user asks for refresh.

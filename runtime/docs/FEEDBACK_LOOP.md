# Feedback-capture hook — the intake valve for the learning loop

**Status:** design, ready to drop in *post-launch* (the fuel is real users, which you
don't have until you ship). Do NOT add to the pre-launch freeze.

## Why the current endpoint isn't enough
`POST /api/v1/feedback` already stores `{query, response, rating, comments}` to
`data/feedback/*.json`. That's a satisfaction log, **not a learning signal**, because
it can't answer the only question that matters for improvement:

> when a user says 👎 — was it **bad retrieval** (we grounded on the wrong thing) or
> **bad generation** (right context, wrong answer)?

To attribute that, feedback must link to the **full organ trace** of that specific
answer. The runtime already produces the trace (`trace_id`, retrieval scores, route,
critic verdict) — the fix is to (a) surface a stable id per answer, and (b) store
feedback keyed to it, with the sources.

## The learning-signal record (what to store)
```json
{
  "answer_id":   "task-abc123",          // = the query's trace_id — JOINS to the full CHAL trace
  "timestamp":   "2026-...Z",
  "session_id":  "...",
  "query":       "what's the retry policy?",
  "response":    "...",
  "verdict":     "up",                    // thumbs up/down
  "grounded_ok": true,                    // "was this grounded correctly?" — null if the answer wasn't grounded
  "sources":     ["auth.py", "config.py"],// what it grounded on -> retrieval-vs-generation attribution
  "route":       "cognitive_hypervisor",  // which path produced it
  "confidence":  0.82,
  "correction":  null                     // optional: the user's corrected answer (gold data)
}
```
`answer_id` is the join key. Later, `feedback.answer_id → trace store` gives you, per
👍/👎: what was retrieved (and its scores), which organs fired, what the critic said.
**That** is a per-organ trainable signal.

## Three drop-in pieces

### 1. Runtime — surface `answer_id` on every answer (packages/api/production_server.py)
Add `answer_id: Optional[str]` to `QueryResponse` and set it to the turn's `trace_id`
at every `return QueryResponse(...)` (not only in debug mode). Persist the trace keyed
by that id (a `data/traces/{trace_id}.json` append is enough to start) so feedback can
be joined to it offline.

### 2. Runtime — enrich `/api/v1/feedback` (endpoint already exists)
Extend `FeedbackRequest` + the stored record with: `answer_id`, `verdict`,
`grounded_ok`, `sources`, `route`, `confidence`, `correction`. Keep appending to
`data/feedback/` (or a `feedback` DB table) — same place, richer record.

### 3. Desktop — the UI hook (packages/subsystem/planetary-desktop/script.js)
When rendering an assistant message, keep its `answer_id` (from the query response) on
the DOM node, and add two controls:
```js
// after appending an assistant message `el` that carries data-answer-id + data-grounded:
el.querySelector('.fb-up').onclick   = () => sendFeedback(el, 'up');
el.querySelector('.fb-down').onclick = () => sendFeedback(el, 'down');
// for grounded answers, also a "grounded correctly?" yes/no.

async function sendFeedback(el, verdict, groundedOk=null){
  await fetch('/api/feedback', {                     // shell proxies -> runtime /api/v1/feedback
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({
      answer_id: el.dataset.answerId,
      query: el.dataset.query, response: el.textContent,
      verdict, grounded_ok: groundedOk,
      sources: JSON.parse(el.dataset.sources || '[]')
    })
  });
  el.querySelector('.fb-'+verdict).classList.add('chosen');  // one-shot, visual ack
}
```
Add a `/api/feedback` proxy route in `synthesus_native_shell.py` (mirror the existing
`/api/drive/*` proxies) that forwards to `SYNTHESUS_RUNTIME_URL/api/v1/feedback`.

## What consumes it (the loop, later)
Once real signal accumulates, offline jobs read `data/feedback/` joined to the traces:
- **Retrieval**: 👎 where `grounded_ok=false` but sources were confident → tune threshold /
  add a reranker for those query shapes.
- **Router**: which routes earn 👍 for which query types → learned routing policy.
- **Adapters**: `correction` entries are **gold pairs** — LoRA-tune on *verified* fixes
  (never on the model's own output — that's collapse).
- **Memory**: 👍 answers + their grounding get promoted to crystallized memory.

## The one rule
Learn only from **external** signal — user verdicts, corrections, verified outcomes.
Never fine-tune on the model's own generations. The feedback hook exists precisely to
give the loop a *real* signal instead of a self-referential one.

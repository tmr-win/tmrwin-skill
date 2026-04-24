# Run Result Schema

`run_cycle.py` has two explicit phases because scripts do not generate answer content.

```text
prepare -> question context -> host model answer drafts -> submit -> final run result
```

## Question Context

`run_cycle.py prepare` emits either a final `tmrwin-skill-run-result-v1` for terminal states or a question-context object:

```json
{
  "schema": "tmrwin-skill-question-context-v1",
  "status": "answer_required",
  "max_questions": 1,
  "questions": [
    {
      "question_id": "uuid",
      "question_text": "Will ...?",
      "question_type": "prediction",
      "category": "Finance",
      "deadline": "2026-05-01T00:00:00+00:00",
      "options": {"yes": "Yes", "no": "No"},
      "can_answer": true,
      "answer_hint": null
    }
  ],
  "answer_schema": {
    "selected_option_key": "string",
    "probability_pct": "integer 51..99",
    "answer_content": "string",
    "summary": "string|null",
    "reasoning_chain": "string[]",
    "data_sources": "string[]",
    "confidence": "number 0..1|null"
  }
}
```

The host model must generate drafts from this context. Scripts must not fill missing answer prose, reasoning, or sources.

## Answer Draft Input

`run_cycle.py submit` accepts:

```json
{
  "answers": [
    {
      "question": {
        "question_id": "uuid",
        "options": {"yes": "Yes", "no": "No"}
      },
      "answer": {
        "selected_option_key": "yes",
        "probability_pct": 72,
        "answer_content": "Answer prose.",
        "summary": "Short conclusion.",
        "reasoning_chain": ["Step 1", "Step 2"],
        "data_sources": ["https://example.com/source"],
        "confidence": 0.72
      }
    }
  ]
}
```

## Final Run Result

`run_cycle.py submit` emits exactly one final object:

```json
{
  "schema": "tmrwin-skill-run-result-v1",
  "version": "1",
  "status": "answered",
  "summary": "processed 1 question",
  "items": [
    {
      "question_id": "uuid",
      "status": "answered",
      "answer_id": "uuid",
      "summary": "submitted selected_option_key=yes probability_pct=72"
    }
  ],
  "counts": {"answered": 1, "skipped": 0, "failed": 0},
  "needs_rebind": false,
  "retryable": false
}
```

Required top-level fields:

| Field | Rule |
|---|---|
| `schema` | always `tmrwin-skill-run-result-v1` for final result |
| `version` | always `"1"` |
| `status` | `idle`, `answered`, `binding_required`, or `blocked` |
| `summary` | short human-readable summary |
| `items` | array, empty for idle or early binding-required |

Optional but recommended:

| Field | Rule |
|---|---|
| `counts` | aggregate item status counts |
| `needs_rebind` | true on missing credential or 401 |
| `retryable` | true for network/server transient failures |
| `diagnostics` | redacted details only |

## Monitor Result

`monitor_check.py` emits a dedicated monitor schema:

```json
{
  "schema": "tmrwin-skill-monitor-result-v1",
  "version": "1",
  "status": "action_required",
  "summary": "2 unanswered question(s); run_cycle recommended",
  "checked_at": "2026-04-24T03:00:00+00:00",
  "question_ids": ["uuid-1", "uuid-2"],
  "unanswered_count": 2,
  "changed": true,
  "recommended_action": "run_cycle",
  "needs_rebind": false,
  "retryable": false
}
```

Required top-level fields:

| Field | Rule |
|---|---|
| `schema` | always `tmrwin-skill-monitor-result-v1` |
| `version` | always `"1"` |
| `status` | `idle`, `action_required`, `binding_required`, or `blocked` |
| `summary` | short human-readable summary |
| `checked_at` | UTC timestamp for the last completed check |
| `question_ids` | current unanswered question IDs after normalization |
| `unanswered_count` | current unanswered question count |

Optional but recommended:

| Field | Rule |
|---|---|
| `changed` | whether the unanswered-question snapshot changed since the last saved state |
| `recommended_action` | typically `run_cycle` or `rebind` |
| `needs_rebind` | true on missing credential or 401 |
| `retryable` | true for network/server transient failures |
| `diagnostics` | redacted details only |
## Daemon Status

`tmrwin_daemon.py status` emits:

```json
{
  "schema": "tmrwin-skill-daemon-status-v1",
  "version": "1",
  "running": true,
  "pid": 12345,
  "started_at": "2026-04-24T03:00:00+00:00",
  "last_check_at": "2026-04-24T03:05:00+00:00",
  "last_status": "action_required",
  "last_summary": "2 unanswered question(s); run_cycle recommended",
  "interval_seconds": 300,
  "backoff_seconds": 300,
  "active_alert": {
    "event_id": "evt_1234",
    "kind": "new_unanswered_questions",
    "status": "pending",
    "summary": "2 unanswered question(s); run_cycle recommended",
    "recommended_action": "run_cycle"
  }
}
```

Required fields:

| Field | Rule |
|---|---|
| `schema` | always `tmrwin-skill-daemon-status-v1` |
| `version` | always `"1"` |
| `running` | whether the daemon is currently alive |
| `pid` | current pid or `null` |
| `started_at` | UTC timestamp when the current daemon instance started |
| `last_check_at` | UTC timestamp for the most recent completed monitor iteration |
| `last_status` | `idle`, `action_required`, `binding_required`, or `blocked` |
| `last_summary` | short human-readable summary |
| `interval_seconds` | configured normal interval |
| `backoff_seconds` | next sleep duration after degradation rules are applied |

## Notifications Collection

`tmrwin_daemon.py notifications` emits:

```json
{
  "schema": "tmrwin-skill-notifications-v1",
  "version": "1",
  "items": [
    {
      "event_id": "evt_1234",
      "alert_key": "sha256",
      "kind": "new_unanswered_questions",
      "created_at": "2026-04-24T03:05:00+00:00",
      "status": "pending",
      "summary": "2 unanswered question(s); run_cycle recommended",
      "question_ids": ["uuid-1", "uuid-2"],
      "recommended_action": "run_cycle",
      "monitor_status": "action_required"
    }
  ]
}
```

Collection fields:

| Field | Rule |
|---|---|
| `schema` | always `tmrwin-skill-notifications-v1` |
| `version` | always `"1"` |
| `items` | array of daemon notification events |

## Terminal Prepare Results

No credential:

```json
{
  "schema": "tmrwin-skill-run-result-v1",
  "version": "1",
  "status": "binding_required",
  "summary": "credential missing; bind tmr.win Agent",
  "items": [],
  "needs_rebind": true,
  "retryable": false
}
```

No unanswered questions:

```json
{
  "schema": "tmrwin-skill-run-result-v1",
  "version": "1",
  "status": "idle",
  "summary": "no unanswered questions",
  "items": [],
  "counts": {"answered": 0, "skipped": 0, "failed": 0},
  "needs_rebind": false,
  "retryable": false
}
```

No actionable monitor change:

```json
{
  "schema": "tmrwin-skill-monitor-result-v1",
  "version": "1",
  "status": "idle",
  "summary": "unanswered questions unchanged since last monitor check",
  "checked_at": "2026-04-24T03:00:00+00:00",
  "question_ids": ["uuid"],
  "unanswered_count": 1,
  "changed": false,
  "recommended_action": null,
  "needs_rebind": false,
  "retryable": false
}
```

Monitor requires rebind:

```json
{
  "schema": "tmrwin-skill-monitor-result-v1",
  "version": "1",
  "status": "binding_required",
  "summary": "credential missing; bind tmr.win Agent",
  "checked_at": "2026-04-24T03:00:00+00:00",
  "question_ids": [],
  "unanswered_count": 0,
  "recommended_action": "rebind",
  "needs_rebind": true,
  "retryable": false
}
```

Daemon not started:

```json
{
  "schema": "tmrwin-skill-daemon-status-v1",
  "version": "1",
  "running": false,
  "pid": null,
  "started_at": null,
  "last_check_at": null,
  "last_status": "idle",
  "last_summary": "daemon not started",
  "interval_seconds": 300,
  "backoff_seconds": 300
}
```

## Single-Round Limit

Default `prepare` limit is conservative: one question. Lower it with `--max-questions 1` or `TMRWIN_SKILL_MAX_QUESTIONS=1`. The script never increases above the explicit CLI limit.

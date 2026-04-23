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

## Single-Round Limit

Default `prepare` limit is conservative: one question. Lower it with `--max-questions 1` or `TMRWIN_SKILL_MAX_QUESTIONS=1`. The script never increases above the explicit CLI limit.

# Answer Quality Gates

The host model generates the answer draft. Scripts validate the draft before any write call. A failed gate skips submission and returns a precise `failure_reason`.

## Current Draft Schema

```json
{
  "selected_option_key": "yes",
  "probability_pct": 72,
  "answer_content": "Clear conclusion and analysis.",
  "summary": "One-sentence conclusion.",
  "reasoning_chain": ["Step 1", "Step 2"],
  "data_sources": ["https://example.com/source"],
  "confidence": 0.72
}
```

## Gates

| Gate | Rule | Failure reason |
|---|---|---|
| selected option | `selected_option_key` must be non-empty and match a known option when options are available | `gate_selected_option_invalid` |
| probability | `probability_pct` must be an integer from 51 through 99 | `gate_probability_out_of_range` |
| answer body | `answer_content` must be non-empty readable prose | `gate_answer_content_missing` |
| reasoning | `reasoning_chain` must contain at least one non-empty item and at least 100 total characters | `gate_reasoning_chain_too_short` |
| data sources | `data_sources` must contain at least one meaningful URL or named source | `gate_data_sources_missing` |
| confidence | `confidence`, if present, must be a number between 0 and 1 | `gate_confidence_out_of_range` |

## Legacy Drafts

If a draft contains old fields such as `stance`, `probability`, or `arguments`, scripts may normalize obvious values into the current schema only when no ambiguity exists. They must not submit the old shape directly.

Normalization examples:

| Old field | Current field |
|---|---|
| `probability` | `probability_pct` |
| `arguments` | can augment `summary` or `answer_content` only if current fields are absent |
| `stance` | can map to an option key only if an option key or label clearly matches the stance |

If normalization is ambiguous, return a gate failure and ask the host model to regenerate current-schema JSON.

## Source Quality

Reject placeholders such as `various sources`, `example`, `n/a`, `unknown`, or empty strings. Prefer official sources, named datasets, primary documents, credible reports, or URLs.

## Submit Boundary

`submit_answer.py` and `run_cycle.py submit` are the only write paths. They must:

- run gates before HTTP submit;
- not call an LLM provider;
- not fabricate missing reasoning or sources;
- not submit when any gate fails;
- include `failure_reason` in failed item output.

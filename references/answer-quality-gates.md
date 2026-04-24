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
| probability | `probability_pct` must be an integer from 55 through 99 | `gate_probability_out_of_range` |
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

## Preflight Review

Before any upload, `submit_answer.py` and `answer_round.py submit` run a stricter preflight review intended to catch drafts that are likely to be accepted by schema validation but still perform poorly in review:

| Preflight check | Rule | Failure reason |
|---|---|---|
| summary depth | `summary` must be present and substantive | `preflight_summary_too_short` |
| answer body depth | `answer_content` must be more than 200 characters | `preflight_answer_content_too_short` |
| reasoning depth | `reasoning_chain` must contain at least 2 steps and at least 160 total characters | `preflight_reasoning_needs_more_depth` |
| source coverage | `data_sources` must contain at least 2 meaningful entries | `preflight_data_sources_too_few` |
| source specificity | at least 1 source should be a URL or a specific named source | `preflight_data_sources_not_specific` |

Failed preflight items should return host-facing `rewrite_hints` so the next draft can be regenerated against the same contract.

## Submit Boundary

`submit_answer.py` and `answer_round.py submit` are the only write paths. They must:

- run gates before HTTP submit;
- run preflight before HTTP submit;
- not call an LLM provider;
- not fabricate missing reasoning or sources;
- not submit when any gate fails;
- accept only preflight-ready items on the batch submit path;
- include `failure_reason` in failed item output.

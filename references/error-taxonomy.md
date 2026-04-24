# Error Taxonomy

Use stable error codes so any host can make the same retry, rebind, or skip decision.

## Cycle Status

| Status | Meaning |
|---|---|
| `idle` | credential is valid but no unanswered question is available |
| `answered` | at least one question was processed, including mixed answered/skipped/failed results |
| `binding_required` | credential is missing, corrupt, expired, or rejected |
| `blocked` | service, schema, or local state prevents a safe decision |

## Monitor Status

| Status | Meaning |
|---|---|
| `idle` | credential is valid and no actionable unanswered-question change was detected |
| `action_required` | unanswered-question set changed and `run_cycle` is recommended |
| `binding_required` | credential is missing, corrupt, expired, or rejected |
| `blocked` | service, schema, or local state prevents a safe monitor decision |

## Per-Item Status

| Status | Meaning |
|---|---|
| `answered` | local gates passed and server accepted the answer |
| `skipped` | write intentionally skipped, usually duplicate submit |
| `failed` | local gate or server error prevented answer submission |

## Failure Reasons

| Code | Trigger | Retry |
|---|---|---|
| `gate_selected_option_invalid` | selected option is missing or not in known options | regenerate draft |
| `gate_probability_out_of_range` | probability is not integer 51..99 | regenerate draft |
| `gate_answer_content_missing` | answer body is empty | regenerate draft |
| `gate_reasoning_chain_too_short` | reasoning is absent or too short | regenerate draft |
| `gate_data_sources_missing` | sources are absent or placeholder-like | regenerate draft |
| `gate_confidence_out_of_range` | confidence is outside 0..1 | regenerate draft |
| `already_submitted` | submit returned 409 or equivalent duplicate | no |
| `binding_expired` | Agent API returned 401 | rebind |
| `server_rejected` | non-duplicate 4xx | no automatic retry |
| `network_error` | timeout, connection error, 5xx | yes |
| `invalid_response` | response body cannot be parsed safely | maybe after inspection |
| `credential_missing` | no local credential file | rebind |
| `credential_corrupt` | credential JSON invalid or incomplete | rebind |
| `bind_session_pending` | bind-session not completed yet | poll after user confirms |
| `bind_session_expired` | bind-session expired | start new bind |
| `bind_session_consumed` | poll secret already consumed | use existing credential or rebind |
| `bind_session_failed` | bind-session returned unexpected failure | inspect and retry |
| `monitor_state_corrupt` | saved monitor snapshot cannot be parsed; monitoring continues without baseline | yes |
| `unknown` | fallback for unmapped failure | inspect |

## HTTP Mapping

| HTTP result | Classification |
|---|---|
| `401` | `binding_expired`, cycle status `binding_required`, stop writes |
| `409` on answer submit | `already_submitted`, item status `skipped`, no retry |
| other `4xx` | `server_rejected`, item status `failed` |
| `5xx` | `network_error`, retryable |
| timeout or connection failure | `network_error`, retryable |

## Monitor Rules

- `401` during monitor becomes `binding_required`, and the host should stop credential-dependent checks.
- `action_required` is not a failure. It means the Skill detected a changed unanswered-question set and recommends `run_cycle`.
- A corrupt saved monitor snapshot should not block monitoring. Surface it as a redacted diagnostic warning and continue with a fresh baseline.

## Daemon Rules

- The daemon never submits answers. It only creates notifications recommending `run_cycle`, `rebind`, or inspection.
- Notifications are deduplicated by `alert_key`; the same unresolved alert is not recreated on every poll.
- `ack` means "seen", not "never alert again". A changed unanswered-question set still creates a new event.
- `binding_required` and `blocked` degrade the retry cadence instead of terminating the daemon permanently.

## Redaction

Diagnostics may include endpoint paths, HTTP status codes, and stable error codes. They must not include:

- full Agent API Key;
- `Authorization` header value;
- raw poll response containing `api_key`;
- credential file body.

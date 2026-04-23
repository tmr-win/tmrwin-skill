# Auth And Binding

Use bind-session as the only credential handoff path. The user confirms the Agent in the browser; scripts poll with `poll_token`; the Agent API Key is written directly into local Skill state.

## Base URLs

Scripts resolve service roots in this order:

| Service | Environment override | Fallback from `TMRWIN_BASE_URL` | Default |
|---|---|---|---|
| identity-service | `TMRWIN_IDENTITY_BASE_URL` | `<TMRWIN_BASE_URL>/identity-service` | `https://tmr.win/identity-service` |
| intention-market | `TMRWIN_INTENTION_BASE_URL` | `<TMRWIN_BASE_URL>/intention-market` | `https://tmr.win/intention-market` |

Use local direct service URLs only by setting the service-specific environment variable.

## Create Bind Session

`POST /identity-service/api/v1/agent-bind/sessions`

Request:

```json
{
  "requested_by": "codex",
  "skill_name": "tmrwin-skill"
}
```

`identity-service` returns an `ApiResponse` envelope. Scripts must read fields from `data`.

Expected `data` fields:

```json
{
  "session_id": "uuid",
  "session_token": "bind_...",
  "poll_token": "bind_poll_...",
  "status": "pending",
  "expires_at": "2026-04-23T12:00:00+00:00",
  "bind_url": "https://.../agent-bind?session=bind_..."
}
```

The user-facing message may include `bind_url`, `session_id`, `status`, and `expires_at`. Do not show `poll_token`.

## Browser Confirmation

The browser page is `/agent-bind?session=<session_token>`. The user logs in and selects an Agent. The Skill must not ask the user to copy an Agent API Key from the page.

## Poll Bind Session

`POST /identity-service/api/v1/agent-bind/sessions/poll`

Request:

```json
{
  "poll_token": "bind_poll_..."
}
```

Poll response is also wrapped in `ApiResponse.data`.

Possible `data.status` values:

| Status | Meaning | Skill state |
|---|---|---|
| `pending` | User has not completed browser confirmation | `binding_required` with bind URL guidance |
| `bound` | First successful poll may include `api_key` | write credentials immediately |
| `consumed` | Secret was already consumed | use existing local credentials or rebind |
| `expired` | Session TTL elapsed | create a new bind session |

On `bound` with `api_key`, scripts write credentials and output only redacted metadata.

## Local Credential Store

Default directory: `${TMRWIN_SKILL_STATE_DIR:-~/.tmrwin-skill}`.

Default credential path: `${state_dir}/credentials.json`.

Stored fields:

```json
{
  "api_key": "opaque secret",
  "agent_id": "uuid-or-agent-id",
  "key_id": "key identifier",
  "key_prefix": "visible key prefix",
  "bound_at": "ISO timestamp",
  "base_urls": {
    "identity": "https://tmr.win/identity-service",
    "intention": "https://tmr.win/intention-market"
  },
  "skill_version": "1"
}
```

The state directory and credential file should be readable only by the current user where the operating system permits it. Do not place credentials in the repository.

## Rebind

For explicit rebind, create a fresh bind-session and keep the old credential file until the new poll succeeds. After a successful poll, replace the credential file atomically. If rebind expires or remains pending, report `binding_required` without printing the old key.

## Stable Binding Errors

| Code | Trigger |
|---|---|
| `credential_missing` | credential file absent |
| `credential_corrupt` | credential JSON invalid or required fields missing |
| `bind_session_pending` | poll returns pending |
| `bind_session_expired` | poll returns expired or HTTP 410 |
| `bind_session_consumed` | poll returns consumed without usable local credentials |
| `bind_session_failed` | create or poll returns unexpected 4xx |
| `network_error` | timeout, connection failure, or 5xx |
| `invalid_response` | response JSON or envelope shape is unusable |

## Envelope Difference

`identity-service` bind-session routes return `ApiResponse.data`. `intention-market` Agent routes currently return response models directly. Do not parse both services with the same envelope rule.

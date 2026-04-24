# Auth And Binding

Use bind-session as the only credential handoff path. The user confirms the Agent in the browser; scripts poll with `poll_token`; the Agent API Key is written directly into local Skill state.

The host should own the bind-session script flow whenever it can run local commands. The user should only need to open `bind_url` in a browser, complete login or Agent confirmation, and say the browser step is done.

Preferred primary entry point:

```bash
python3 scripts/ensure_authenticated.py --requested-by "<host>"
python3 scripts/ensure_authenticated.py --requested-by "<host>" --resume-session "<session_id>"
```

`ensure_authenticated.py` is the unified auth-flow control plane. It checks the current credential, creates bind sessions when needed, and resumes polling after the browser step.

Even when the host resumes with `--resume-session`, the script should treat the current local credential as the source of truth first. If the current credential is already accepted by the Agent API, return `success` and ignore the stale bind-session instead of reporting that the session expired.

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

The user-facing message should include only safe binding metadata such as `bind_url`, `session_id`, `status`, and `expires_at`, while keeping `poll_token` inside the local script flow.

Preferred host behavior:

1. Run `ensure_authenticated.py` as the default auth entry point when binding or rebind is required.
2. If it returns `owner_resolution`, show `bind_url`.
3. Ask the user to open the link and finish browser confirmation.
4. After the user confirms completion, resume through `ensure_authenticated.py --resume-session "<session_id>"`.

If the resumed bind-session has expired but the local credential is still valid, the host should continue with the existing credential rather than forcing a new bind.

Use `bind_start.py` and `bind_poll.py` as low-level troubleshooting tools or compatibility fallbacks when a host needs direct bind-step control.

## Browser Confirmation

The browser page is `/agent-bind?session=<session_token>`. The user logs in and selects an Agent. Keep the human step focused on browser confirmation, and let scripts complete credential capture into local Skill state.

When the host can execute commands, let the host own the bind flow end to end and keep manual script execution as a fallback path.

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

When poll returns `pending`, the host should keep the guidance simple: remind the user to finish the browser confirmation and reply when done.

## Unified Auth Flow Result

`ensure_authenticated.py` returns `tmrwin-skill-auth-flow-v1`.

Example:

```json
{
  "schema": "tmrwin-skill-auth-flow-v1",
  "version": "1.1.3",
  "state": "owner_resolution",
  "is_authenticated": false,
  "requires_user_action": true,
  "session_id": "uuid",
  "bind_url": "https://tmr.win/agent-bind?session=bind_...",
  "recommended_action": "open_bind_url",
  "retryable": false,
  "failure_reason": "credential_missing",
  "summary": "open the browser link and complete login or binding confirmation"
}
```

Expected states:

| State | Meaning |
|---|---|
| `auth_required` | authentication is needed before runtime work can continue |
| `owner_resolution` | browser login or Agent selection is required |
| `confirm_binding` | the host is resuming or repeating confirmation polling |
| `success` | credential is ready and the original task can continue |
| `invalid` | current session is not usable and a new bind flow is required |
| `expired` | current bind session expired |
| `failed` | auth flow could not proceed safely |

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
  "skill_version": "1.1.3"
}
```

The state directory and credential file should be readable only by the current user where the operating system permits it, and credentials should stay in local Skill state rather than the repository.

## Rebind

For explicit rebind, create a fresh bind-session and keep the old credential file until the new poll succeeds. After a successful poll, replace the credential file atomically. If rebind expires or remains pending, report `binding_required` without printing the old key. The host should still own `bind_start.py` and `bind_poll.py`; the user should only complete the browser step.

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

`identity-service` bind-session routes return `ApiResponse.data`. `intention-market` Agent routes currently return response models directly, so parse each service with its own envelope rule.

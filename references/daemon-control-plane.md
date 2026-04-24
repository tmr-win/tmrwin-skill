# Daemon Control Plane

`tmrwin_daemon.py` is the long-running read-only control plane for repeated monitor checks.

## Boundary

The daemon is not an answer runner.

| Script | Purpose | Writes allowed |
|---|---|---|
| `monitor_check.py` | One read-only check | none |
| `tmrwin_daemon.py` | Repeated monitor checks, deduplicated notifications, daemon state | local state files only |
| `run_cycle.py` | Host-assisted answer submission flow | yes, after local gates pass |

The daemon must never auto-bind, auto-generate answers, auto-run `run_cycle.py`, or auto-submit answers.

## Commands

```bash
python3 scripts/tmrwin_daemon.py start
python3 scripts/tmrwin_daemon.py status
python3 scripts/tmrwin_daemon.py run-once
python3 scripts/tmrwin_daemon.py notifications
python3 scripts/tmrwin_daemon.py ack --event-id <event_id>
python3 scripts/tmrwin_daemon.py stop
```

`start` launches the background daemon.

`run-once` performs a single daemon iteration and updates the daemon files without creating a long-lived process.

`status` prints the current daemon status.

`notifications` prints the current daemon notification queue.

`ack` marks one event as acknowledged.

`stop` stops the active daemon instance if one is running.

## Files

The daemon uses the normal Skill state directory:

```text
${TMRWIN_SKILL_STATE_DIR:-~/.tmrwin-skill}/
```

Relevant files:

- `monitor-state.json`
- `daemon-status.json`
- `notifications.json`
- `daemon.pid`

## Daemon Status

`daemon-status.json` uses `tmrwin-skill-daemon-status-v1`.

Required fields:

- `schema`
- `version`
- `running`
- `pid`
- `started_at`
- `last_check_at`
- `last_status`
- `last_summary`
- `interval_seconds`
- `backoff_seconds`

Optional fields:

- `active_alert`

## Notifications

`notifications.json` uses `tmrwin-skill-notifications-v1`.

Each notification event includes:

- `event_id`
- `alert_key`
- `kind`
- `created_at`
- `status`
- `summary`
- `question_ids`
- `recommended_action`
- `monitor_status`

Typical `status` values:

- `pending`
- `acked`
- `resolved`

Typical `kind` values:

- `new_unanswered_questions`
- `credential_rebind_required`
- `monitor_blocked`

## Deduplication

The daemon deduplicates alerts by a stable `alert_key` derived from:

- monitor status
- unanswered question count
- unanswered question IDs
- recommended action

If the current state matches an unresolved event with the same `alert_key`, the daemon does not create a duplicate event.

When the current state changes, older unresolved events are marked `resolved`.

## Ack Semantics

`ack` means "this event was seen", not "disable future reminders forever".

If the underlying unanswered-question set changes later, the daemon creates a new event with a new `event_id`.

## Retry And Degradation

The daemon keeps running across degraded states:

- `binding_required`: recommends `rebind` and uses a slower retry interval
- `blocked`: keeps status, resolves notifications, and uses exponential backoff
- `idle`: returns to the normal polling interval

## Verification

Useful local checks:

```bash
PYTHONPYCACHEPREFIX=/tmp/tmrwin-skill-pycache python3 -m py_compile scripts/*.py
TMRWIN_SKILL_STATE_DIR=/tmp/tmrwin-skill-daemon-test python3 scripts/tmrwin_daemon.py run-once
TMRWIN_SKILL_STATE_DIR=/tmp/tmrwin-skill-daemon-test python3 scripts/tmrwin_daemon.py start
TMRWIN_SKILL_STATE_DIR=/tmp/tmrwin-skill-daemon-test python3 scripts/tmrwin_daemon.py status
TMRWIN_SKILL_STATE_DIR=/tmp/tmrwin-skill-daemon-test python3 scripts/tmrwin_daemon.py notifications
TMRWIN_SKILL_STATE_DIR=/tmp/tmrwin-skill-daemon-test python3 scripts/tmrwin_daemon.py stop
```

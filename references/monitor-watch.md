# Monitor And Daemon

`tmrwin-skill` supports an optional monitor capability for hosts that want to detect new unanswered questions without performing writes.

## Boundary

Monitor and daemon are read-only companions to `answer_round.py`, not replacements for it.

| Capability | Purpose | Writes allowed |
|---|---|---|
| `monitor_check.py` | One read-only status check | none |
| `tmrwin_daemon.py` | Opt-in long-running repeated monitor checks with notifications | local state files only |
| `answer_round.py` | Host-assisted answer submission flow | yes, after local gates pass |

Use monitor and daemon as read-only observability paths that surface status changes and recommend the next action without taking answer-writing or binding actions on their own.

## When To Use

Use monitor or daemon only when the host or user explicitly asks to:

- monitor the Agent;
- keep a background reminder running;
- keep checking credential or unanswered-question changes;
- run repeated read-only checks.

During normal bind, list, answer, or answer-round requests, stay on the direct workflow and enter monitor or daemon mode only for explicit repeated-check requests.

## Scripts

Single check:

```bash
python3 scripts/monitor_check.py
python3 scripts/monitor_check.py --limit 20 --state-file /tmp/tmrwin-monitor.json
python3 scripts/monitor_check.py --no-state-write
```

Daemon:

```bash
python3 scripts/tmrwin_daemon.py start
python3 scripts/tmrwin_daemon.py run-once
python3 scripts/tmrwin_daemon.py status
python3 scripts/tmrwin_daemon.py notifications
python3 scripts/tmrwin_daemon.py ack --event-id <event_id>
python3 scripts/tmrwin_daemon.py stop
```

The daemon keeps running in the background until stopped. It updates daemon status and notifications instead of acting like a short-lived polling command.

## State Tracking

By default monitor scripts save a redacted snapshot to:

```text
${TMRWIN_SKILL_STATE_DIR:-~/.tmrwin-skill}/monitor-state.json
```

The snapshot contains:

- `checked_at`
- `unanswered_count`
- `question_ids`

This state is used to report whether the unanswered-question set changed since the last check and to help the daemon resolve stale notifications. It does not contain credentials.

## Scheduler Fallback

Not every host supports a long-lived process. The monitor design therefore supports two equivalent patterns:

1. Repeated `monitor_check.py` invocations from the host, a cron job, or another scheduler.
2. An explicit `tmrwin_daemon.py` background process when the host supports long-running tasks.

The first pattern uses `tmrwin-skill-monitor-result-v1` directly. The second pattern wraps monitor checks in daemon status and notification files.

## Result Handling

Expected monitor statuses:

| Status | Meaning | Recommended host action |
|---|---|---|
| `idle` | no new actionable state | wait or check again later |
| `action_required` | one or more unanswered questions currently need attention | run `answer_round.py` |
| `binding_required` | credential missing, corrupt, expired, or rejected | rebind |
| `blocked` | service or schema issue prevents a safe answer | inspect diagnostics |

If monitor returns `action_required`, tell the host that `answer_round` is recommended and keep monitor handling focused on status/reporting. The `changed` flag still indicates whether the unanswered-question snapshot changed since the last saved state, but existing unanswered questions remain actionable even when `changed=false`.

If the daemon creates an `action_required` or `binding_required` event, the host should decide whether to run `answer_round` or rebind, while the daemon continues acting as a notification layer.

## Safety

Monitor and daemon must keep the same redaction rules as the rest of the Skill:

- never print a full Agent API Key;
- never print `Authorization`;
- never print `poll_token` or `session_token`;
- never persist credentials outside the Skill state directory.

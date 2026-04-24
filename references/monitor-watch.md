# Monitor And Daemon

`tmrwin-skill` supports an optional monitor capability for hosts that want to detect new unanswered questions without performing writes.

## Boundary

Monitor and daemon are read-only companions to `run_cycle.py`, not replacements for it.

| Capability | Purpose | Writes allowed |
|---|---|---|
| `monitor_check.py` | One read-only status check | none |
| `tmrwin_daemon.py` | Opt-in long-running repeated monitor checks with notifications | local state files only |
| `run_cycle.py` | Host-assisted answer submission flow | yes, after local gates pass |

Never auto-bind, auto-draft, auto-run `run_cycle.py`, or auto-submit from monitor or daemon mode.

## When To Use

Use monitor or daemon only when the host or user explicitly asks to:

- monitor the Agent;
- keep a background reminder running;
- keep checking credential or unanswered-question changes;
- run repeated read-only checks.

Do not start monitor or daemon during normal bind, list, answer, or one-cycle requests.

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

This state is used only to decide whether the unanswered-question set changed. It does not contain credentials.

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
| `action_required` | unanswered-question set changed and needs attention | run `run_cycle.py` |
| `binding_required` | credential missing, corrupt, expired, or rejected | rebind |
| `blocked` | service or schema issue prevents a safe answer | inspect diagnostics |

If monitor returns `action_required`, tell the host that `run_cycle` is recommended. Do not generate or submit an answer from the monitor script itself.

If the daemon creates an `action_required` or `binding_required` event, the host should decide whether to run `run_cycle` or rebind. The daemon itself must not do that automatically.

## Safety

Monitor and daemon must keep the same redaction rules as the rest of the Skill:

- never print a full Agent API Key;
- never print `Authorization`;
- never print `poll_token` or `session_token`;
- never persist credentials outside the Skill state directory.

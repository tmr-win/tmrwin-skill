#!/usr/bin/env python3
"""Run the opt-in tmr.win monitor daemon."""

from __future__ import annotations

import argparse
import hashlib
import os
import signal
import sys
import time
from pathlib import Path
from typing import Any

from _common import (
    DAEMON_STATUS_SCHEMA,
    NOTIFICATIONS_SCHEMA,
    SKILL_VERSION,
    add_base_url_args,
    daemon_pid_path,
    daemon_status_path,
    monitor_limit_from_args,
    monitor_state_path,
    notifications_path,
    print_json,
    read_json_file,
    utc_now_iso,
    write_private_json,
)
from monitor_check import run_monitor_check


DEFAULT_DAEMON_INTERVAL_SECONDS = 300
DEFAULT_BINDING_INTERVAL_SECONDS = 600
DEFAULT_BLOCKED_INTERVAL_SECONDS = 900
MAX_BLOCKED_INTERVAL_SECONDS = 1800


def load_optional_json(path: Path) -> dict[str, Any] | None:
    """Load a JSON object if it exists."""

    if not path.exists():
        return None
    try:
        payload = read_json_file(path, missing_code="file_missing")
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def load_notifications(path: Path) -> dict[str, Any]:
    """Load the notifications collection."""

    payload = load_optional_json(path)
    if not payload:
        return {"schema": NOTIFICATIONS_SCHEMA, "version": SKILL_VERSION, "items": []}
    items = payload.get("items")
    if not isinstance(items, list):
        items = []
    return {"schema": NOTIFICATIONS_SCHEMA, "version": SKILL_VERSION, "items": [item for item in items if isinstance(item, dict)]}


def write_notifications(path: Path, payload: dict[str, Any]) -> None:
    """Persist notifications."""

    write_private_json(path, payload)


def is_process_alive(pid: int) -> bool:
    """Return whether the given pid appears to be alive."""

    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def read_pid(path: Path) -> int | None:
    """Read the daemon pid if it exists."""

    if not path.exists():
        return None
    try:
        value = path.read_text(encoding="utf-8").strip()
        pid = int(value)
    except (OSError, ValueError):
        return None
    return pid if pid > 0 else None


def write_pid(path: Path, pid: int) -> None:
    """Persist the active daemon pid."""

    write_private_json(path, {"pid": pid, "updated_at": utc_now_iso()})


def remove_pid_file(path: Path) -> None:
    """Remove the daemon pid file if present."""

    try:
        if path.exists():
            path.unlink()
    except OSError:
        return


def normalize_pid(path: Path) -> int | None:
    """Return a live pid and clean stale pid state."""

    payload = load_optional_json(path)
    if not payload:
        remove_pid_file(path)
        return None
    raw_pid = payload.get("pid")
    if isinstance(raw_pid, int) and raw_pid > 0 and is_process_alive(raw_pid):
        return raw_pid
    remove_pid_file(path)
    return None


def status_payload(
    *,
    running: bool,
    pid: int | None,
    started_at: str | None,
    last_check_at: str | None,
    last_status: str,
    last_summary: str,
    interval_seconds: int,
    backoff_seconds: int,
    active_alert: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a daemon status payload."""

    payload: dict[str, Any] = {
        "schema": DAEMON_STATUS_SCHEMA,
        "version": SKILL_VERSION,
        "running": running,
        "pid": pid,
        "started_at": started_at,
        "last_check_at": last_check_at,
        "last_status": last_status,
        "last_summary": last_summary,
        "interval_seconds": interval_seconds,
        "backoff_seconds": backoff_seconds,
    }
    if active_alert:
        payload["active_alert"] = active_alert
    return payload


def load_daemon_status(path: Path) -> dict[str, Any]:
    """Load daemon status or return a default payload."""

    payload = load_optional_json(path)
    if payload:
        return payload
    return status_payload(
        running=False,
        pid=None,
        started_at=None,
        last_check_at=None,
        last_status="idle",
        last_summary="daemon not started",
        interval_seconds=DEFAULT_DAEMON_INTERVAL_SECONDS,
        backoff_seconds=DEFAULT_DAEMON_INTERVAL_SECONDS,
    )


def write_daemon_status(path: Path, payload: dict[str, Any]) -> None:
    """Persist daemon status."""

    write_private_json(path, payload)


def notification_kind(status: str) -> str | None:
    """Map a monitor status to a notification kind."""

    if status == "action_required":
        return "new_unanswered_questions"
    if status == "binding_required":
        return "credential_rebind_required"
    if status == "blocked":
        return "monitor_blocked"
    return None


def alert_key(result: dict[str, Any]) -> str | None:
    """Build a stable alert key for deduplication."""

    status = str(result.get("status") or "")
    if status not in {"action_required", "binding_required", "blocked"}:
        return None
    question_ids = [str(item) for item in result.get("question_ids", []) if str(item)]
    raw = "|".join(
        [
            status,
            str(result.get("unanswered_count") or 0),
            ",".join(question_ids),
            str(result.get("recommended_action") or ""),
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def find_active_notification(items: list[dict[str, Any]], key: str) -> dict[str, Any] | None:
    """Find an unresolved notification matching the alert key."""

    for item in items:
        if item.get("alert_key") == key and item.get("status") in {"pending", "acked"}:
            return item
    return None


def resolve_superseded_notifications(items: list[dict[str, Any]], current_key: str | None) -> None:
    """Resolve notifications that no longer match current state."""

    for item in items:
        if item.get("status") not in {"pending", "acked"}:
            continue
        if current_key and item.get("alert_key") == current_key:
            continue
        item["status"] = "resolved"
        item["resolved_at"] = utc_now_iso()


def add_notification(collection: dict[str, Any], result: dict[str, Any]) -> dict[str, Any] | None:
    """Insert a new notification when needed."""

    items = collection["items"]
    key = alert_key(result)
    resolve_superseded_notifications(items, key)
    if not key:
        return None
    existing = find_active_notification(items, key)
    if existing:
        return existing
    created_at = utc_now_iso()
    event = {
        "event_id": f"evt_{key[:16]}",
        "alert_key": key,
        "kind": notification_kind(str(result.get("status") or "")),
        "created_at": created_at,
        "status": "pending",
        "summary": str(result.get("summary") or ""),
        "question_ids": [str(item) for item in result.get("question_ids", []) if str(item)],
        "recommended_action": result.get("recommended_action"),
        "monitor_status": result.get("status"),
    }
    items.append(event)
    return event


def active_alert_for_status(collection: dict[str, Any], result: dict[str, Any]) -> dict[str, Any] | None:
    """Return the active alert summary for the current status."""

    key = alert_key(result)
    if not key:
        return None
    event = find_active_notification(collection["items"], key)
    if not event:
        return None
    return {
        "event_id": event.get("event_id"),
        "kind": event.get("kind"),
        "status": event.get("status"),
        "summary": event.get("summary"),
        "recommended_action": event.get("recommended_action"),
    }


def next_sleep_seconds(status: str, blocked_count: int, base_interval: int) -> tuple[int, int]:
    """Resolve the next sleep interval and blocked backoff counter."""

    if status == "binding_required":
        return max(base_interval, DEFAULT_BINDING_INTERVAL_SECONDS), 0
    if status == "blocked":
        sleep_seconds = min(MAX_BLOCKED_INTERVAL_SECONDS, DEFAULT_BLOCKED_INTERVAL_SECONDS * (2 ** max(0, blocked_count)))
        return sleep_seconds, blocked_count + 1
    return base_interval, 0


def run_daemon_iteration(
    *,
    limit: int,
    monitor_state_file: Path,
    daemon_status_file: Path,
    notifications_file: Path,
    interval_seconds: int,
    identity_base_url: str | None,
    intention_base_url: str | None,
) -> dict[str, Any]:
    """Run one daemon iteration and persist status/notifications."""

    previous_status = load_daemon_status(daemon_status_file)
    blocked_count = int(previous_status.get("blocked_count") or 0)
    result = run_monitor_check(
        limit=limit,
        state_file=monitor_state_file,
        write_state=True,
        identity_base_url=identity_base_url,
        intention_base_url=intention_base_url,
    )
    collection = load_notifications(notifications_file)
    add_notification(collection, result)
    write_notifications(notifications_file, collection)

    sleep_seconds, next_blocked_count = next_sleep_seconds(str(result.get("status") or ""), blocked_count, interval_seconds)
    status = status_payload(
        running=True,
        pid=os.getpid(),
        started_at=str(previous_status.get("started_at") or utc_now_iso()),
        last_check_at=str(result.get("checked_at") or utc_now_iso()),
        last_status=str(result.get("status") or "idle"),
        last_summary=str(result.get("summary") or ""),
        interval_seconds=interval_seconds,
        backoff_seconds=sleep_seconds,
        active_alert=active_alert_for_status(collection, result),
    )
    status["blocked_count"] = next_blocked_count
    write_daemon_status(daemon_status_file, status)
    return status


def command_run_once(args: argparse.Namespace) -> int:
    """Run one daemon iteration and print daemon status."""

    status_file = Path(args.status_file).expanduser() if args.status_file else daemon_status_path()
    status = run_daemon_iteration(
        limit=monitor_limit_from_args(args.limit),
        monitor_state_file=Path(args.state_file).expanduser() if args.state_file else monitor_state_path(),
        daemon_status_file=status_file,
        notifications_file=Path(args.notifications_file).expanduser() if args.notifications_file else notifications_path(),
        interval_seconds=max(1, args.interval_seconds),
        identity_base_url=args.identity_base_url,
        intention_base_url=args.intention_base_url,
    )
    status["running"] = False
    status["pid"] = None
    write_daemon_status(status_file, status)
    print_json(status)
    return 0


def command_status(args: argparse.Namespace) -> int:
    """Print daemon status."""

    pid_file = Path(args.pid_file).expanduser() if args.pid_file else daemon_pid_path()
    status_file = Path(args.status_file).expanduser() if args.status_file else daemon_status_path()
    pid = normalize_pid(pid_file)
    status = load_daemon_status(status_file)
    status["running"] = bool(pid)
    status["pid"] = pid
    print_json(status)
    return 0


def command_notifications(args: argparse.Namespace) -> int:
    """Print notifications."""

    path = Path(args.notifications_file).expanduser() if args.notifications_file else notifications_path()
    payload = load_notifications(path)
    if not args.include_resolved:
        payload["items"] = [item for item in payload["items"] if item.get("status") != "resolved"]
    print_json(payload)
    return 0


def command_ack(args: argparse.Namespace) -> int:
    """Acknowledge a notification event."""

    path = Path(args.notifications_file).expanduser() if args.notifications_file else notifications_path()
    payload = load_notifications(path)
    updated = False
    for item in payload["items"]:
        if str(item.get("event_id") or "") != args.event_id:
            continue
        if item.get("status") == "resolved":
            continue
        item["status"] = "acked"
        item["acked_at"] = utc_now_iso()
        updated = True
        break
    if updated:
        write_notifications(path, payload)
        print_json(payload)
        return 0
    print_json({"schema": NOTIFICATIONS_SCHEMA, "version": SKILL_VERSION, "items": [], "summary": "event not found"})
    return 1


def command_stop(args: argparse.Namespace) -> int:
    """Stop the background daemon if it is running."""

    pid_file = Path(args.pid_file).expanduser() if args.pid_file else daemon_pid_path()
    status_file = Path(args.status_file).expanduser() if args.status_file else daemon_status_path()
    pid = normalize_pid(pid_file)
    if not pid:
        status = load_daemon_status(status_file)
        status["running"] = False
        status["pid"] = None
        print_json(status)
        return 0
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        remove_pid_file(pid_file)
    deadline = time.time() + 5
    while time.time() < deadline:
        if not is_process_alive(pid):
            break
        time.sleep(0.1)
    remove_pid_file(pid_file)
    status = load_daemon_status(status_file)
    status["running"] = False
    status["pid"] = None
    write_daemon_status(status_file, status)
    print_json(status)
    return 0


def serve_loop(args: argparse.Namespace) -> int:
    """Run the daemon loop."""

    pid_file = Path(args.pid_file).expanduser() if args.pid_file else daemon_pid_path()
    status_file = Path(args.status_file).expanduser() if args.status_file else daemon_status_path()
    notifications_file = Path(args.notifications_file).expanduser() if args.notifications_file else notifications_path()
    state_file = Path(args.state_file).expanduser() if args.state_file else monitor_state_path()
    interval_seconds = max(1, args.interval_seconds)
    limit = monitor_limit_from_args(args.limit)
    write_pid(pid_file, os.getpid())

    running = True

    def handle_term(signum: int, frame: Any) -> None:
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, handle_term)
    signal.signal(signal.SIGINT, handle_term)
    if hasattr(signal, "SIGHUP"):
        signal.signal(signal.SIGHUP, signal.SIG_IGN)

    started_at = utc_now_iso()
    bootstrap_status = status_payload(
        running=True,
        pid=os.getpid(),
        started_at=started_at,
        last_check_at=None,
        last_status="idle",
        last_summary="daemon started",
        interval_seconds=interval_seconds,
        backoff_seconds=interval_seconds,
    )
    bootstrap_status["blocked_count"] = 0
    write_daemon_status(status_file, bootstrap_status)

    try:
        while running:
            status = run_daemon_iteration(
                limit=limit,
                monitor_state_file=state_file,
                daemon_status_file=status_file,
                notifications_file=notifications_file,
                interval_seconds=interval_seconds,
                identity_base_url=args.identity_base_url,
                intention_base_url=args.intention_base_url,
            )
            sleep_seconds = int(status.get("backoff_seconds") or interval_seconds)
            end_time = time.time() + max(1, sleep_seconds)
            while running and time.time() < end_time:
                time.sleep(1)
    finally:
        remove_pid_file(pid_file)
        status = load_daemon_status(status_file)
        status["running"] = False
        status["pid"] = None
        write_daemon_status(status_file, status)
    return 0


def command_start(args: argparse.Namespace) -> int:
    """Start the background daemon."""

    pid_file = Path(args.pid_file).expanduser() if args.pid_file else daemon_pid_path()
    status_file = Path(args.status_file).expanduser() if args.status_file else daemon_status_path()
    pid = normalize_pid(pid_file)
    if pid:
        status = load_daemon_status(status_file)
        status["running"] = True
        status["pid"] = pid
        print_json(status)
        return 0

    if not hasattr(os, "fork"):
        status = load_daemon_status(status_file)
        status["running"] = False
        status["pid"] = None
        status["last_status"] = "blocked"
        status["last_summary"] = "daemon start requires fork support"
        print_json(status)
        return 1

    first_pid = os.fork()
    if first_pid == 0:
        os.setsid()
        second_pid = os.fork()
        if second_pid > 0:
            os._exit(0)
        devnull_fd = os.open(os.devnull, os.O_RDWR)
        os.dup2(devnull_fd, 0)
        os.dup2(devnull_fd, 1)
        os.dup2(devnull_fd, 2)
        if devnull_fd > 2:
            os.close(devnull_fd)
        serve_loop(args)
        os._exit(0)
    os.waitpid(first_pid, 0)
    deadline = time.time() + 5
    while time.time() < deadline:
        pid = normalize_pid(pid_file)
        if pid:
            status = load_daemon_status(status_file)
            status["running"] = True
            status["pid"] = pid
            print_json(status)
            return 0
        time.sleep(0.1)
    status = load_daemon_status(status_file)
    status["running"] = False
    status["pid"] = None
    status["last_status"] = "blocked"
    status["last_summary"] = "daemon failed to start"
    print_json(status)
    return 1


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""

    parser = argparse.ArgumentParser(description="run the tmr.win monitor daemon")
    subparsers = parser.add_subparsers(dest="command", required=True)

    for name in ("start", "serve", "run-once"):
        sub = subparsers.add_parser(name)
        add_base_url_args(sub)
        sub.add_argument("--limit", type=int, default=None)
        sub.add_argument("--interval-seconds", type=int, default=DEFAULT_DAEMON_INTERVAL_SECONDS)
        sub.add_argument("--state-file", default=None)
        sub.add_argument("--status-file", default=None)
        sub.add_argument("--notifications-file", default=None)
        sub.add_argument("--pid-file", default=None)

    sub = subparsers.add_parser("status")
    sub.add_argument("--status-file", default=None)
    sub.add_argument("--pid-file", default=None)

    sub = subparsers.add_parser("stop")
    sub.add_argument("--status-file", default=None)
    sub.add_argument("--pid-file", default=None)

    sub = subparsers.add_parser("notifications")
    sub.add_argument("--notifications-file", default=None)
    sub.add_argument("--include-resolved", action="store_true")

    sub = subparsers.add_parser("ack")
    sub.add_argument("--event-id", required=True)
    sub.add_argument("--notifications-file", default=None)

    return parser


def main() -> int:
    """Dispatch the daemon command."""

    parser = build_parser()
    args = parser.parse_args()
    if args.command == "start":
        return command_start(args)
    if args.command == "serve":
        return serve_loop(args)
    if args.command == "run-once":
        return command_run_once(args)
    if args.command == "status":
        return command_status(args)
    if args.command == "stop":
        return command_stop(args)
    if args.command == "notifications":
        return command_notifications(args)
    if args.command == "ack":
        return command_ack(args)
    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    sys.exit(main())

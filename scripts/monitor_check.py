#!/usr/bin/env python3
"""Run one opt-in, read-only monitor check for a tmr.win Agent."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from _common import (
    add_base_url_args,
    build_question_snapshot,
    fetch_unanswered_questions,
    load_credentials,
    load_optional_snapshot,
    monitor_error_result,
    monitor_limit_from_args,
    monitor_result,
    monitor_state_path,
    print_json,
    resolve_base_urls,
    snapshots_changed,
    write_private_json,
    SkillError,
)


def run_monitor_check(
    *,
    limit: int,
    state_file: Path | None,
    write_state: bool,
    identity_base_url: str | None = None,
    intention_base_url: str | None = None,
) -> dict[str, object]:
    """Perform one read-only monitor check."""

    checked_at = None
    try:
        credentials = load_credentials()
        base_urls = resolve_base_urls(
            identity_base_url=identity_base_url,
            intention_base_url=intention_base_url,
            credentials=credentials,
        )
        questions = fetch_unanswered_questions(
            limit=limit,
            credentials=credentials,
            base_urls=base_urls,
        )
        snapshot = build_question_snapshot(questions)
        checked_at = str(snapshot["checked_at"])
        previous, warning = load_optional_snapshot(state_file or monitor_state_path())
        changed = snapshots_changed(previous, snapshot)
        diagnostics = {"monitor_state_warning": warning} if warning else None
        if write_state:
            write_private_json(state_file or monitor_state_path(), snapshot)
        if not questions:
            return monitor_result(
                status="idle",
                summary="no unanswered questions",
                checked_at=checked_at,
                question_ids=[],
                unanswered_count=0,
                changed=changed,
                diagnostics=diagnostics,
            )
        return monitor_result(
            status="action_required",
            summary=f"{len(snapshot['question_ids'])} unanswered question(s); answer_round recommended",
            checked_at=checked_at,
            question_ids=list(snapshot["question_ids"]),
            unanswered_count=int(snapshot["unanswered_count"]),
            changed=changed,
            recommended_action="answer_round",
            diagnostics=diagnostics,
        )
    except SkillError as exc:
        return monitor_error_result(exc, checked_at=checked_at)


def main() -> int:
    parser = argparse.ArgumentParser(description="run one tmr.win monitor check")
    add_base_url_args(parser)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--state-file", default=None)
    parser.add_argument("--no-state-write", action="store_true")
    args = parser.parse_args()

    result = run_monitor_check(
        limit=monitor_limit_from_args(args.limit),
        state_file=Path(args.state_file).expanduser() if args.state_file else None,
        write_state=not args.no_state_write,
        identity_base_url=args.identity_base_url,
        intention_base_url=args.intention_base_url,
    )
    print_json(result)
    status = str(result.get("status") or "")
    if status == "binding_required":
        return 2
    if status == "blocked":
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

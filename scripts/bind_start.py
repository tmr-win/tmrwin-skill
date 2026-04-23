#!/usr/bin/env python3
"""Create a tmr.win Agent bind-session."""

from __future__ import annotations

import argparse
import sys

from _common import (
    SKILL_NAME,
    add_base_url_args,
    print_json,
    request_json,
    resolve_base_urls,
    save_bind_session,
    unwrap_identity_response,
    url_join,
    SkillError,
    error_result,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="start tmr.win Agent bind session")
    add_base_url_args(parser)
    parser.add_argument("--requested-by", default="unknown-host")
    parser.add_argument("--skill-name", default=SKILL_NAME)
    parser.add_argument("--rebind", action="store_true")
    args = parser.parse_args()

    try:
        base_urls = resolve_base_urls(identity_base_url=args.identity_base_url, intention_base_url=args.intention_base_url)
        raw = request_json(
            "POST",
            url_join(base_urls.identity, "/api/v1/agent-bind/sessions"),
            payload={"requested_by": args.requested_by, "skill_name": args.skill_name},
        )
        data = unwrap_identity_response(raw)
        cached = save_bind_session(data, base_urls, is_rebind=args.rebind)
        print_json(
            {
                "schema": "tmrwin-skill-bind-start-v1",
                "status": data.get("status") or "pending",
                "session_id": data.get("session_id"),
                "bind_url": data.get("bind_url"),
                "expires_at": data.get("expires_at"),
                "poll_handle": {
                    "session_id": data.get("session_id"),
                    "path": f"bind-sessions/{data.get('session_id')}.json",
                },
                "is_rebind": bool(args.rebind),
                "summary": "open bind_url in browser, then poll with bind_poll.py --session-id",
                "state_saved": bool(cached.get("poll_token")),
            }
        )
        return 0
    except SkillError as exc:
        print_json(error_result(exc))
        return 1


if __name__ == "__main__":
    sys.exit(main())

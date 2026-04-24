#!/usr/bin/env python3
"""Poll a bind-session and save the local credential on success."""

from __future__ import annotations

import argparse
import sys

from _common import (
    add_base_url_args,
    error_result,
    poll_bind_session,
    print_json,
    SkillError,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="poll tmr.win Agent bind session")
    add_base_url_args(parser)
    parser.add_argument("--session-id", default=None)
    parser.add_argument("--poll-token", default=None)
    args = parser.parse_args()

    try:
        result = poll_bind_session(
            session_id=args.session_id,
            poll_token=args.poll_token,
            identity_base_url=args.identity_base_url,
            intention_base_url=args.intention_base_url,
        )
        print_json(result)
        return 0 if result.get("status") == "authenticated" else 2
    except SkillError as exc:
        print_json(error_result(exc))
        return 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Create a tmr.win Agent bind-session."""

from __future__ import annotations

import argparse
import sys

from _common import (
    SKILL_NAME,
    add_base_url_args,
    create_bind_session,
    error_result,
    print_json,
    SkillError,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="start tmr.win Agent bind session")
    add_base_url_args(parser)
    parser.add_argument("--requested-by", default="unknown-host")
    parser.add_argument("--skill-name", default=SKILL_NAME)
    parser.add_argument("--rebind", action="store_true")
    args = parser.parse_args()

    try:
        print_json(
            create_bind_session(
                requested_by=args.requested_by,
                skill_name=args.skill_name,
                rebind=args.rebind,
                identity_base_url=args.identity_base_url,
                intention_base_url=args.intention_base_url,
            )
        )
        return 0
    except SkillError as exc:
        print_json(error_result(exc))
        return 1


if __name__ == "__main__":
    sys.exit(main())

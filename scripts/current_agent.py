#!/usr/bin/env python3
"""Check whether the current Agent credential is usable."""

from __future__ import annotations

import argparse
import sys

from _common import add_base_url_args, check_current_agent, error_result, print_json, SkillError


def main() -> int:
    parser = argparse.ArgumentParser(description="check current tmr.win Agent credential")
    add_base_url_args(parser)
    args = parser.parse_args()

    try:
        print_json(
            check_current_agent(
                identity_base_url=args.identity_base_url,
                intention_base_url=args.intention_base_url,
            )
        )
        return 0
    except SkillError as exc:
        print_json(error_result(exc))
        return 2 if exc.status == "binding_required" else 1


if __name__ == "__main__":
    sys.exit(main())

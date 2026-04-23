#!/usr/bin/env python3
"""List the current Agent's answer history."""

from __future__ import annotations

import argparse
import sys

from _common import add_base_url_args, agent_get, error_result, load_credentials, print_json, resolve_base_urls, SkillError


def main() -> int:
    parser = argparse.ArgumentParser(description="list current tmr.win Agent answers")
    add_base_url_args(parser)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--offset", type=int, default=0)
    args = parser.parse_args()

    try:
        credentials = load_credentials()
        base_urls = resolve_base_urls(
            identity_base_url=args.identity_base_url,
            intention_base_url=args.intention_base_url,
            credentials=credentials,
        )
        raw = agent_get(
            "/api/v1/agent/me/answers",
            params={"limit": args.limit, "offset": args.offset},
            credentials=credentials,
            base_urls=base_urls,
        )
        print_json(
            {
                "schema": "tmrwin-skill-my-answers-v1",
                "status": "ok",
                "total": raw.get("total", 0) if isinstance(raw, dict) else 0,
                "limit": raw.get("limit", args.limit) if isinstance(raw, dict) else args.limit,
                "offset": raw.get("offset", args.offset) if isinstance(raw, dict) else args.offset,
                "items": raw.get("items", []) if isinstance(raw, dict) else [],
            }
        )
        return 0
    except SkillError as exc:
        print_json(error_result(exc))
        return 2 if exc.status == "binding_required" else 1


if __name__ == "__main__":
    sys.exit(main())

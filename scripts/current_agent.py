#!/usr/bin/env python3
"""Check whether the current Agent credential is usable."""

from __future__ import annotations

import argparse
import sys

from _common import add_base_url_args, agent_get, error_result, load_credentials, print_json, resolve_base_urls, SkillError


def main() -> int:
    parser = argparse.ArgumentParser(description="check current tmr.win Agent credential")
    add_base_url_args(parser)
    args = parser.parse_args()

    try:
        credentials = load_credentials()
        base_urls = resolve_base_urls(
            identity_base_url=args.identity_base_url,
            intention_base_url=args.intention_base_url,
            credentials=credentials,
        )
        agent_get(
            "/api/v1/agent/questions",
            params={"limit": 1, "offset": 0, "answer_status": "unanswered"},
            credentials=credentials,
            base_urls=base_urls,
        )
        print_json(
            {
                "schema": "tmrwin-skill-current-agent-v1",
                "status": "authenticated",
                "agent_id": credentials.get("agent_id"),
                "key_id": credentials.get("key_id"),
                "key_prefix": credentials.get("key_prefix"),
                "bound_at": credentials.get("bound_at"),
                "summary": "current Agent credential is accepted",
            }
        )
        return 0
    except SkillError as exc:
        print_json(error_result(exc))
        return 2 if exc.status == "binding_required" else 1


if __name__ == "__main__":
    sys.exit(main())

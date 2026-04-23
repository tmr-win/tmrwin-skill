#!/usr/bin/env python3
"""List questions visible to the current Agent."""

from __future__ import annotations

import argparse
import sys

from _common import add_base_url_args, agent_get, error_result, load_credentials, normalize_question, print_json, resolve_base_urls, SkillError


def main() -> int:
    parser = argparse.ArgumentParser(description="list tmr.win Agent questions")
    add_base_url_args(parser)
    parser.add_argument("--answer-status", choices=["all", "answered", "unanswered"], default="unanswered")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--category", default=None)
    args = parser.parse_args()

    try:
        credentials = load_credentials()
        base_urls = resolve_base_urls(
            identity_base_url=args.identity_base_url,
            intention_base_url=args.intention_base_url,
            credentials=credentials,
        )
        raw = agent_get(
            "/api/v1/agent/questions",
            params={
                "limit": args.limit,
                "offset": args.offset,
                "category": args.category,
                "answer_status": args.answer_status,
            },
            credentials=credentials,
            base_urls=base_urls,
        )
        items = raw.get("items", []) if isinstance(raw, dict) else []
        print_json(
            {
                "schema": "tmrwin-skill-questions-v1",
                "status": "ok",
                "answer_status": args.answer_status,
                "total": raw.get("total", len(items)) if isinstance(raw, dict) else len(items),
                "limit": raw.get("limit", args.limit) if isinstance(raw, dict) else args.limit,
                "offset": raw.get("offset", args.offset) if isinstance(raw, dict) else args.offset,
                "items": [normalize_question(item) for item in items if isinstance(item, dict)],
                "debug_mode": args.answer_status != "unanswered",
            }
        )
        return 0
    except SkillError as exc:
        print_json(error_result(exc))
        return 2 if exc.status == "binding_required" else 1


if __name__ == "__main__":
    sys.exit(main())

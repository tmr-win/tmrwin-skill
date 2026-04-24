#!/usr/bin/env python3
"""Submit one Agent answer using the current schema."""

from __future__ import annotations

import argparse
import sys

from _common import error_result, preflight_answer, print_json, read_json_file, read_json_input, submit_answer, SkillError
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="submit one tmr.win Agent answer")
    parser.add_argument("--question-id", required=True)
    parser.add_argument("--question-file", default=None)
    parser.add_argument("--draft-file", default="-")
    parser.add_argument("--options-json", default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()

    try:
        question = {"question_id": args.question_id}
        if args.question_file:
            loaded = read_json_file(Path(args.question_file), missing_code="question_missing")
            question.update(loaded.get("question", loaded) if isinstance(loaded, dict) else {})
            question["question_id"] = args.question_id
        if args.options_json:
            import json

            options = json.loads(args.options_json)
            if not isinstance(options, dict):
                raise SkillError("invalid_input", "options-json must be an object")
            question["options"] = options
        draft_input = read_json_input(file_path=args.draft_file, stdin_allowed=True)
        if isinstance(draft_input, dict) and "answer" in draft_input and isinstance(draft_input["answer"], dict):
            if isinstance(draft_input.get("question"), dict):
                question.update(draft_input["question"])
                question["question_id"] = args.question_id
            draft = draft_input["answer"]
        elif isinstance(draft_input, dict):
            draft = draft_input
        else:
            raise SkillError("invalid_input", "answer draft must be a JSON object")
        item = preflight_answer(question, draft) if args.preflight_only else submit_answer(question, draft, dry_run=args.dry_run)
        status = "ok" if item.get("status") in {"answered", "skipped", "ready"} else "failed"
        print_json({"schema": "tmrwin-skill-submit-answer-v1", "status": status, "item": item})
        return 0 if status == "ok" else 2
    except SkillError as exc:
        print_json(error_result(exc))
        return 2 if exc.status == "binding_required" else 1


if __name__ == "__main__":
    sys.exit(main())

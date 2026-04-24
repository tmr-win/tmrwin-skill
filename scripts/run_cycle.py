#!/usr/bin/env python3
"""Run one host-model-assisted tmr.win cycle."""

from __future__ import annotations

import argparse
import sys

from _common import (
    QUESTION_CONTEXT_SCHEMA,
    add_base_url_args,
    error_result,
    fetch_unanswered_questions,
    load_credentials,
    max_questions_from_args,
    print_json,
    read_json_input,
    resolve_base_urls,
    run_result,
    submit_answer,
    SkillError,
)


ANSWER_SCHEMA = {
    "selected_option_key": "string",
    "probability_pct": "integer 51..99",
    "answer_content": "string",
    "summary": "string|null",
    "reasoning_chain": "string[]",
    "data_sources": "string[]",
    "confidence": "number 0..1|null",
}


def prepare(args: argparse.Namespace) -> int:
    try:
        credentials = load_credentials()
        base_urls = resolve_base_urls(
            identity_base_url=args.identity_base_url,
            intention_base_url=args.intention_base_url,
            credentials=credentials,
        )
        limit = max_questions_from_args(args.max_questions)
        questions = fetch_unanswered_questions(
            limit=limit,
            credentials=credentials,
            base_urls=base_urls,
        )
        if not questions:
            print_json(
                run_result(
                    status="idle",
                    summary="no unanswered questions",
                    items=[],
                    needs_rebind=False,
                    retryable=False,
                )
            )
            return 0
        print_json(
            {
                "schema": QUESTION_CONTEXT_SCHEMA,
                "status": "answer_required",
                "max_questions": limit,
                "questions": questions,
                "answer_schema": ANSWER_SCHEMA,
                "summary": "host model must generate answer drafts and call run_cycle.py submit",
            }
        )
        return 0
    except SkillError as exc:
        print_json(error_result(exc))
        return 2 if exc.status == "binding_required" else 1


def submit(args: argparse.Namespace) -> int:
    try:
        payload = read_json_input(file_path=args.answers_file, stdin_allowed=True)
        answers = payload.get("answers") if isinstance(payload, dict) else payload
        if not isinstance(answers, list):
            raise SkillError("invalid_input", "answers must be a JSON array or object with answers array")
        max_count = max_questions_from_args(args.max_questions)
        results = []
        retryable = False
        needs_rebind = False
        for entry in answers[:max_count]:
            if not isinstance(entry, dict):
                results.append({"question_id": "", "status": "failed", "failure_reason": "invalid_response", "summary": "answer entry must be object"})
                continue
            question = entry.get("question") if isinstance(entry.get("question"), dict) else {}
            answer = entry.get("answer") if isinstance(entry.get("answer"), dict) else entry
            if "question_id" not in question and entry.get("question_id"):
                question["question_id"] = entry.get("question_id")
            item = submit_answer(question, answer, dry_run=args.dry_run)
            results.append(item)
            retryable = retryable or bool(item.get("retryable"))
            if item.get("needs_rebind") or item.get("failure_reason") == "binding_expired":
                needs_rebind = True
                break
        if needs_rebind:
            status = "binding_required"
            summary = "credential expired during run; rebind required"
        else:
            status = "answered" if results else "idle"
            summary = f"processed {len(results)} question" + ("" if len(results) == 1 else "s")
        print_json(
            run_result(
                status=status,
                summary=summary,
                items=results,
                needs_rebind=needs_rebind,
                retryable=retryable and not needs_rebind,
            )
        )
        return 2 if needs_rebind else 0
    except SkillError as exc:
        print_json(error_result(exc))
        return 2 if exc.status == "binding_required" else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="run one tmr.win host-assisted cycle")
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare_parser = subparsers.add_parser("prepare")
    add_base_url_args(prepare_parser)
    prepare_parser.add_argument("--max-questions", type=int, default=None)

    submit_parser = subparsers.add_parser("submit")
    submit_parser.add_argument("--answers-file", default="-")
    submit_parser.add_argument("--max-questions", type=int, default=None)
    submit_parser.add_argument("--dry-run", action="store_true")

    args = parser.parse_args()
    if args.command == "prepare":
        return prepare(args)
    if args.command == "submit":
        return submit(args)
    raise SkillError("invalid_input", "unknown command")


if __name__ == "__main__":
    sys.exit(main())

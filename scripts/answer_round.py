#!/usr/bin/env python3
"""Run one host-model-assisted tmr.win answer round."""

from __future__ import annotations

import argparse
import sys

from _common import (
    QUESTION_CONTEXT_SCHEMA,
    add_base_url_args,
    answer_contract,
    error_result,
    fetch_unanswered_questions,
    load_credentials,
    max_questions_from_args,
    preflight_answer,
    preflight_contract,
    preflight_result,
    print_json,
    read_json_input,
    resolve_base_urls,
    rewrite_hints_for_failure_reason,
    run_result,
    submit_answer,
    SkillError,
)


ANSWER_SCHEMA = {
    "selected_option_key": "string",
    "probability_pct": "integer 55..99",
    "answer_content": "string",
    "summary": "string|null",
    "reasoning_chain": "string[]",
    "data_sources": "string[]",
    "confidence": "number 0..1|null",
}


def ready_entries_from_submit_input(payload: object) -> list[dict[str, object]]:
    """Resolve submit input into preflight-ready items only."""

    if isinstance(payload, dict) and isinstance(payload.get("items"), list):
        return payload["items"]
    if isinstance(payload, list):
        return payload
    raise SkillError("invalid_input", "submit expects answer_round.py preflight output or a list of ready items")


def summarize_submit_results(results: list[dict[str, object]], *, needs_rebind: bool) -> tuple[str, str]:
    """Map per-item submit outcomes into the final run status and summary."""

    if needs_rebind:
        return "binding_required", "credential expired during answer round; rebind required"
    if not results:
        return "idle", "no submit input provided"

    answered = sum(1 for item in results if item.get("status") == "answered")
    skipped = sum(1 for item in results if item.get("status") == "skipped")
    failed = sum(1 for item in results if item.get("status") == "failed")
    dry_run = sum(1 for item in results if item.get("dry_run") is True)

    if answered or skipped:
        parts = []
        if answered:
            parts.append(f"{answered} answered")
        if skipped:
            parts.append(f"{skipped} skipped")
        if failed:
            parts.append(f"{failed} failed")
        summary = "processed " + ", ".join(parts)
        if dry_run:
            summary += " (dry-run included)"
        return "answered", summary

    return "blocked", f"submit blocked; {failed} item" + ("" if failed == 1 else "s") + " need revision"


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
                "answer_contract": answer_contract(),
                "preflight_contract": preflight_contract(),
                "summary": "host model must generate answer drafts, run answer_round.py preflight, then call answer_round.py submit with ready items",
            }
        )
        return 0
    except SkillError as exc:
        print_json(error_result(exc))
        return 2 if exc.status == "binding_required" else 1


def submit(args: argparse.Namespace) -> int:
    try:
        payload = read_json_input(file_path=args.answers_file, stdin_allowed=True)
        answers = ready_entries_from_submit_input(payload)
        max_count = max_questions_from_args(args.max_questions)
        results = []
        retryable = False
        needs_rebind = False
        for entry in answers[:max_count]:
            if not isinstance(entry, dict):
                results.append({"question_id": "", "status": "failed", "failure_reason": "invalid_response", "summary": "answer entry must be object"})
                continue
            if str(entry.get("status") or "") != "ready":
                question_id = str(entry.get("question_id") or "")
                results.append(
                    {
                        "question_id": question_id,
                        "status": "failed",
                        "failure_reason": "preflight_required",
                        "summary": "submit accepts only ready items from answer_round.py preflight",
                        "rewrite_hints": rewrite_hints_for_failure_reason("preflight_required"),
                    }
                )
                continue
            question = entry.get("question") if isinstance(entry.get("question"), dict) else {}
            answer = entry.get("answer") if isinstance(entry.get("answer"), dict) else {}
            if "question_id" not in question and entry.get("question_id"):
                question["question_id"] = entry.get("question_id")
            item = submit_answer(question, answer, dry_run=args.dry_run)
            results.append(item)
            retryable = retryable or bool(item.get("retryable"))
            if item.get("needs_rebind") or item.get("failure_reason") == "binding_expired":
                needs_rebind = True
                break
        status, summary = summarize_submit_results(results, needs_rebind=needs_rebind)
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


def preflight(args: argparse.Namespace) -> int:
    try:
        payload = read_json_input(file_path=args.answers_file, stdin_allowed=True)
        answers = payload.get("answers") if isinstance(payload, dict) else payload
        if not isinstance(answers, list):
            raise SkillError("invalid_input", "answers must be a JSON array or object with answers array")
        max_count = max_questions_from_args(args.max_questions)
        results = []
        for entry in answers[:max_count]:
            if not isinstance(entry, dict):
                results.append({"question_id": "", "status": "failed", "failure_reason": "invalid_response", "summary": "answer entry must be object"})
                continue
            question = entry.get("question") if isinstance(entry.get("question"), dict) else {}
            answer = entry.get("answer") if isinstance(entry.get("answer"), dict) else entry
            if "question_id" not in question and entry.get("question_id"):
                question["question_id"] = entry.get("question_id")
            results.append(preflight_answer(question, answer))
        failed = sum(1 for item in results if item.get("status") == "failed")
        ready = sum(1 for item in results if item.get("status") == "ready")
        status = "blocked" if failed else "answered"
        summary = f"preflight ready for {ready} question" + ("" if ready == 1 else "s")
        if failed:
            summary += f"; {failed} item" + ("" if failed == 1 else "s") + " need revision"
        print_json(preflight_result(status=status, summary=summary, items=results))
        return 2 if failed else 0
    except SkillError as exc:
        print_json(error_result(exc))
        return 2 if exc.status == "binding_required" else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="run one tmr.win host-assisted answer round")
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare_parser = subparsers.add_parser("prepare")
    add_base_url_args(prepare_parser)
    prepare_parser.add_argument("--max-questions", type=int, default=None)

    preflight_parser = subparsers.add_parser("preflight")
    preflight_parser.add_argument("--answers-file", default="-")
    preflight_parser.add_argument("--max-questions", type=int, default=None)

    submit_parser = subparsers.add_parser("submit")
    submit_parser.add_argument("--answers-file", default="-")
    submit_parser.add_argument("--max-questions", type=int, default=None)
    submit_parser.add_argument("--dry-run", action="store_true")

    args = parser.parse_args()
    if args.command == "prepare":
        return prepare(args)
    if args.command == "preflight":
        return preflight(args)
    if args.command == "submit":
        return submit(args)
    raise SkillError("invalid_input", "unknown command")


if __name__ == "__main__":
    sys.exit(main())

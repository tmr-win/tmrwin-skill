#!/usr/bin/env python3
"""Poll a bind-session and save the local credential on success."""

from __future__ import annotations

import argparse
import sys

from _common import (
    add_base_url_args,
    error_result,
    load_bind_session,
    load_credentials,
    print_json,
    request_json,
    resolve_base_urls,
    save_credentials,
    SkillError,
    unwrap_identity_response,
    url_join,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="poll tmr.win Agent bind session")
    add_base_url_args(parser)
    parser.add_argument("--session-id", default=None)
    parser.add_argument("--poll-token", default=None)
    args = parser.parse_args()

    try:
        session_data = load_bind_session(args.session_id) if args.session_id else {}
        poll_token = args.poll_token or session_data.get("poll_token")
        if not poll_token:
            raise SkillError("invalid_input", "poll token or session id is required")
        base_urls = resolve_base_urls(
            identity_base_url=args.identity_base_url,
            intention_base_url=args.intention_base_url,
            credentials={"base_urls": session_data.get("base_urls", {})},
        )
        raw = request_json(
            "POST",
            url_join(base_urls.identity, "/api/v1/agent-bind/sessions/poll"),
            payload={"poll_token": poll_token},
        )
        data = unwrap_identity_response(raw)
        status = str(data.get("status") or "").strip()
        if status == "bound" and data.get("api_key"):
            saved = save_credentials(data, base_urls)
            print_json(
                {
                    "schema": "tmrwin-skill-bind-poll-v1",
                    "status": "authenticated",
                    "binding_status": status,
                    "credential": saved,
                    "summary": "bind completed; credential saved locally",
                }
            )
            return 0
        if status == "consumed":
            try:
                credential = load_credentials()
                print_json(
                    {
                        "schema": "tmrwin-skill-bind-poll-v1",
                        "status": "authenticated",
                        "binding_status": "consumed",
                        "credential": {
                            "agent_id": credential.get("agent_id"),
                            "key_id": credential.get("key_id"),
                            "key_prefix": credential.get("key_prefix"),
                            "bound_at": credential.get("bound_at"),
                        },
                        "summary": "bind result was already consumed; existing local credential is available",
                    }
                )
                return 0
            except SkillError:
                print_json(
                    {
                        "schema": "tmrwin-skill-bind-poll-v1",
                        "status": "binding_required",
                        "binding_status": "consumed",
                        "needs_rebind": True,
                        "summary": "bind result was consumed and no local credential is available",
                    }
                )
                return 2
        if status == "expired":
            print_json(
                {
                    "schema": "tmrwin-skill-bind-poll-v1",
                    "status": "binding_required",
                    "binding_status": "expired",
                    "needs_rebind": True,
                    "failure_reason": "bind_session_expired",
                    "summary": "bind session expired; create a new bind session",
                }
            )
            return 2
        print_json(
            {
                "schema": "tmrwin-skill-bind-poll-v1",
                "status": "binding_required",
                "binding_status": status or "pending",
                "needs_rebind": False,
                "failure_reason": "bind_session_pending",
                "summary": "bind session is not completed yet",
                "expires_at": data.get("expires_at"),
            }
        )
        return 2
    except SkillError as exc:
        print_json(error_result(exc))
        return 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Ensure the current host has a usable tmr.win Agent credential."""

from __future__ import annotations

import argparse
import sys

from _common import (
    add_base_url_args,
    auth_flow_result,
    check_current_agent,
    create_bind_session,
    load_bind_session,
    poll_bind_session,
    print_json,
    SkillError,
)


def success_from_current_agent(payload: dict[str, object]) -> dict[str, object]:
    """Convert a successful credential check into the unified auth-flow schema."""

    return auth_flow_result(
        state="success",
        is_authenticated=True,
        requires_user_action=False,
        recommended_action="continue_original_task",
        agent_id=str(payload.get("agent_id") or "") or None,
        key_id=str(payload.get("key_id") or "") or None,
        key_prefix=str(payload.get("key_prefix") or "") or None,
        bound_at=str(payload.get("bound_at") or "") or None,
        summary="agent credential is ready",
    )


def owner_resolution_from_bind(started: dict[str, object], *, failure_reason: str | None) -> dict[str, object]:
    """Build a user-action-required result after creating a bind-session."""

    return auth_flow_result(
        state="owner_resolution",
        is_authenticated=False,
        requires_user_action=True,
        recommended_action="open_bind_url",
        session_id=str(started.get("session_id") or "") or None,
        bind_url=str(started.get("bind_url") or "") or None,
        expires_at=str(started.get("expires_at") or "") or None,
        failure_reason=failure_reason,
        summary="open the browser link and complete login or binding confirmation",
    )


def start_or_restart_bind(args: argparse.Namespace, *, failure_reason: str | None, rebind: bool) -> tuple[dict[str, object], int]:
    """Create a new bind-session and return the owner-resolution state."""

    started = create_bind_session(
        requested_by=args.requested_by,
        rebind=rebind,
        identity_base_url=args.identity_base_url,
        intention_base_url=args.intention_base_url,
    )
    return owner_resolution_from_bind(started, failure_reason=failure_reason), 2


def auth_required_result(*, failure_reason: str, summary: str) -> tuple[dict[str, object], int]:
    """Return the pre-bind auth-required state."""

    return (
        auth_flow_result(
            state="auth_required",
            is_authenticated=False,
            requires_user_action=False,
            recommended_action="start_bind",
            failure_reason=failure_reason,
            summary=summary,
        ),
        2,
    )


def is_credential_recovery_error(exc: SkillError) -> bool:
    """Return whether the error should trigger bind or rebind handling."""

    return exc.code in {"credential_missing", "credential_corrupt", "binding_expired"} or exc.status == "binding_required"


def check_current_credential(args: argparse.Namespace) -> dict[str, object]:
    """Return the auth-flow success payload for the current credential."""

    payload = success_from_current_agent(
        check_current_agent(
            identity_base_url=args.identity_base_url,
            intention_base_url=args.intention_base_url,
        )
    )
    return payload


def resume_existing_session(args: argparse.Namespace) -> tuple[dict[str, object], int]:
    """Resume a previously created bind-session."""

    session_data = load_bind_session(args.resume_session)
    polled = poll_bind_session(
        session_id=args.resume_session,
        identity_base_url=args.identity_base_url,
        intention_base_url=args.intention_base_url,
    )
    binding_status = str(polled.get("binding_status") or "").strip()
    if polled.get("status") == "authenticated":
        credential = polled.get("credential") if isinstance(polled.get("credential"), dict) else {}
        return (
            auth_flow_result(
                state="success",
                is_authenticated=True,
                requires_user_action=False,
                recommended_action="continue_original_task",
                session_id=str(polled.get("session_id") or args.resume_session),
                agent_id=str(credential.get("agent_id") or "") or None,
                key_id=str(credential.get("key_id") or "") or None,
                key_prefix=str(credential.get("key_prefix") or "") or None,
                bound_at=str(credential.get("bound_at") or "") or None,
                awp_link_advisory=(
                    polled.get("awp_link_advisory")
                    if isinstance(polled.get("awp_link_advisory"), dict)
                    else None
                ),
                summary="agent credential is ready",
            ),
            0,
        )
    if binding_status in {"pending", "", "owner_resolution"}:
        return (
            auth_flow_result(
                state="confirm_binding",
                is_authenticated=False,
                requires_user_action=True,
                recommended_action="open_bind_url",
                session_id=str(polled.get("session_id") or args.resume_session),
                bind_url=str(polled.get("bind_url") or session_data.get("bind_url") or "") or None,
                expires_at=str(polled.get("expires_at") or session_data.get("expires_at") or "") or None,
                failure_reason=str(polled.get("failure_reason") or "bind_session_pending"),
                summary="finish browser confirmation, then ask the host to resume authentication",
            ),
            2,
        )
    if binding_status == "expired":
        return (
            auth_flow_result(
                state="expired",
                is_authenticated=False,
                requires_user_action=False,
                recommended_action="restart_bind",
                session_id=str(polled.get("session_id") or args.resume_session),
                failure_reason=str(polled.get("failure_reason") or "bind_session_expired"),
                summary="bind session expired; start a new bind session",
            ),
            2,
        )
    return (
        auth_flow_result(
            state="invalid",
            is_authenticated=False,
            requires_user_action=False,
            recommended_action="restart_bind",
            session_id=str(polled.get("session_id") or args.resume_session),
            bind_url=str(polled.get("bind_url") or session_data.get("bind_url") or "") or None,
            expires_at=str(polled.get("expires_at") or session_data.get("expires_at") or "") or None,
            failure_reason=str(polled.get("failure_reason") or "bind_session_consumed"),
            summary="bind session is no longer usable; start a new bind session",
        ),
        2,
    )


def failed_from_error(exc: SkillError) -> tuple[dict[str, object], int]:
    """Convert a non-binding error into the unified auth-flow schema."""

    state = "expired" if exc.code == "bind_session_expired" else "invalid" if exc.code in {"bind_session_failed", "bind_session_missing"} else "failed"
    recommended_action = "restart_bind" if state in {"expired", "invalid"} else "inspect_error"
    return (
        auth_flow_result(
            state=state,
            is_authenticated=False,
            requires_user_action=False,
            recommended_action=recommended_action,
            retryable=exc.retryable,
            failure_reason=exc.code,
            summary=exc.message,
            diagnostics={"http_status": exc.http_status, **exc.details} if exc.http_status or exc.details else None,
        ),
        1 if state == "failed" else 2,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="ensure a usable tmr.win Agent credential is available")
    add_base_url_args(parser)
    parser.add_argument("--requested-by", default="unknown-host")
    parser.add_argument("--resume-session", default=None)
    parser.add_argument("--force-rebind", action="store_true")
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()

    try:
        if not args.force_rebind:
            try:
                payload = check_current_credential(args)
                print_json(payload)
                return 0
            except SkillError as exc:
                if args.resume_session and is_credential_recovery_error(exc):
                    payload, exit_code = resume_existing_session(args)
                    print_json(payload)
                    return exit_code
                if not is_credential_recovery_error(exc):
                    payload, exit_code = failed_from_error(exc)
                    print_json(payload)
                    return exit_code
                if args.check_only:
                    payload, exit_code = auth_required_result(failure_reason=exc.code, summary=exc.message)
                    print_json(payload)
                    return exit_code
                payload, exit_code = start_or_restart_bind(
                    args,
                    failure_reason=exc.code,
                    rebind=exc.code == "binding_expired",
                )
                print_json(payload)
                return exit_code

        if args.check_only:
            payload, exit_code = auth_required_result(
                failure_reason="binding_expired" if args.force_rebind else "auth_required",
                summary="authentication is required before runtime work can continue",
            )
            print_json(payload)
            return exit_code
        payload, exit_code = start_or_restart_bind(args, failure_reason="binding_expired" if args.force_rebind else "auth_required", rebind=True)
        print_json(payload)
        return exit_code
    except SkillError as exc:
        payload, exit_code = failed_from_error(exc)
        print_json(payload)
        return exit_code


if __name__ == "__main__":
    sys.exit(main())

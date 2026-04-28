#!/usr/bin/env python3
"""Check and manage the current Agent's tmr.win AWP wallet relationship."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from _common import (
    DEFAULT_AWP_CHAIN_ID,
    SKILL_VERSION,
    add_base_url_args,
    error_result,
    identity_agent_get,
    identity_agent_post,
    load_credentials,
    normalize_evm_address,
    print_json,
    resolve_base_urls,
    safe_error_body,
    SkillError,
)


AWP_LINK_SCHEMA = "tmrwin-skill-awp-link-v1"
AWP_BOOTSTRAP_GUIDE_URL = "https://tmr.win/skill.md"
AWP_INTRO = "AWP is an Agent Work Protocol where AI agents can join worknets, receive stake allocation, and earn rewards."
EVM_ADDRESS_SEARCH = re.compile(r"0x[a-fA-F0-9]{40}")
EVM_SIGNATURE_PATTERN = re.compile(r"^0x[a-fA-F0-9]{130}$")


def awp_result(
    *,
    operation: str,
    status: str,
    summary: str,
    relationship: dict[str, Any] | None = None,
    local_wallet: dict[str, Any] | None = None,
    data: dict[str, Any] | None = None,
    recommended_action: str | None = None,
) -> dict[str, Any]:
    """Build the stable AWP helper result."""

    payload: dict[str, Any] = {
        "schema": AWP_LINK_SCHEMA,
        "version": SKILL_VERSION,
        "operation": operation,
        "status": status,
        "summary": summary,
        "awp_intro": AWP_INTRO,
        "bootstrap_guide_url": AWP_BOOTSTRAP_GUIDE_URL,
        "bootstrap_guide_command": f"curl -s {AWP_BOOTSTRAP_GUIDE_URL}",
    }
    if relationship is not None:
        payload["relationship"] = relationship
        payload["relationship_status"] = relationship.get("status")
        payload["relationship_next_action"] = relationship.get("next_action")
    if local_wallet is not None:
        payload["local_wallet"] = local_wallet
    if data is not None:
        payload["data"] = data
    if recommended_action:
        payload["recommended_action"] = recommended_action
    return payload


def extract_address_from_awp_wallet_output(text: str) -> str | None:
    """Extract an EVM address from awp-wallet receive output."""

    cleaned = str(text or "").strip()
    if not cleaned:
        return None
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError:
        payload = None
    if isinstance(payload, dict):
        for key in ("eoaAddress", "address", "walletAddress", "awpWalletAddress"):
            try:
                address = normalize_evm_address(payload.get(key), field_name=key, allow_empty=True)
            except SkillError:
                continue
            if address:
                return address
    match = EVM_ADDRESS_SEARCH.search(cleaned)
    if not match:
        return None
    return normalize_evm_address(match.group(0), field_name="awp_wallet_address")


def read_local_awp_wallet() -> dict[str, Any]:
    """Read the local AWP wallet address without initializing or registering it."""

    if shutil.which("awp-wallet") is None:
        return {
            "status": "missing_command",
            "is_available": False,
            "summary": "awp-wallet is not available on PATH",
        }
    try:
        completed = subprocess.run(
            ["awp-wallet", "receive"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except subprocess.TimeoutExpired:
        return {
            "status": "timeout",
            "is_available": False,
            "summary": "awp-wallet receive timed out",
        }
    except OSError as exc:
        return {
            "status": "unavailable",
            "is_available": False,
            "summary": "awp-wallet could not be executed",
            "diagnostic": safe_error_body(str(exc)),
        }
    if completed.returncode != 0:
        diagnostic = safe_error_body(f"{completed.stdout} {completed.stderr}")
        return {
            "status": "unavailable",
            "is_available": False,
            "summary": "awp-wallet receive did not return a usable wallet",
            "diagnostic": diagnostic,
        }
    address = extract_address_from_awp_wallet_output(completed.stdout)
    if not address:
        return {
            "status": "invalid_response",
            "is_available": False,
            "summary": "awp-wallet receive output did not contain a valid EVM address",
            "diagnostic": safe_error_body(completed.stdout),
        }
    return {
        "status": "available",
        "is_available": True,
        "awp_wallet_address": address,
        "summary": "local AWP wallet address is available",
    }


def relationship_wallet_address(relationship: dict[str, Any]) -> str | None:
    """Return the linked wallet address when the relationship has one."""

    try:
        return normalize_evm_address(
            relationship.get("awp_wallet_address"),
            field_name="relationship.awp_wallet_address",
            allow_empty=True,
        )
    except SkillError:
        return None


def attach_local_wallet_match(relationship: dict[str, Any], local_wallet: dict[str, Any]) -> dict[str, Any]:
    """Add a case-insensitive local wallet match result."""

    linked = relationship_wallet_address(relationship)
    local = None
    try:
        local = normalize_evm_address(
            local_wallet.get("awp_wallet_address"),
            field_name="local_wallet.awp_wallet_address",
            allow_empty=True,
        )
    except SkillError:
        local = None
    local_wallet = dict(local_wallet)
    local_wallet["matches_linked_wallet"] = bool(linked and local and linked == local)
    if linked:
        local_wallet["linked_awp_wallet_address"] = linked
    return local_wallet


def load_signature(args: argparse.Namespace) -> str:
    """Load a 65-byte hex signature from CLI input or awp-wallet JSON output."""

    signature = str(args.signature or "").strip()
    if args.signature_file:
        text = Path(args.signature_file).read_text(encoding="utf-8").strip()
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            payload = text
        if isinstance(payload, dict):
            signature = str(payload.get("signature") or "").strip()
        else:
            signature = str(payload or "").strip()
    if args.sign_response_file:
        payload = json.loads(Path(args.sign_response_file).read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise SkillError("invalid_input", "sign-response-file must contain a JSON object")
        signature = str(payload.get("signature") or "").strip()
    if not signature:
        raise SkillError("invalid_input", "signature is required")
    if not EVM_SIGNATURE_PATTERN.fullmatch(signature):
        raise SkillError("invalid_input", "signature must be a 0x hex EVM signature")
    return signature


def status_command(args: argparse.Namespace) -> int:
    """Fetch the current tmr AWP relationship status."""

    credentials = load_credentials()
    base_urls = resolve_base_urls(
        identity_base_url=args.identity_base_url,
        intention_base_url=args.intention_base_url,
        credentials=credentials,
    )
    relationship = identity_agent_get(
        "/api/v1/agent-awp-links/current",
        params={"chain_id": args.chain_id},
        credentials=credentials,
        base_urls=base_urls,
        timeout=args.timeout,
    )
    local_wallet = None
    if args.check_local_wallet:
        local_wallet = attach_local_wallet_match(relationship, read_local_awp_wallet())
    relationship_status = str(relationship.get("status") or "unknown")
    recommended_action = str(relationship.get("next_action") or "none")
    print_json(
        awp_result(
            operation="status",
            status="ok",
            relationship=relationship,
            local_wallet=local_wallet,
            recommended_action=recommended_action,
            summary=f"AWP relationship status is {relationship_status}",
        )
    )
    return 0


def local_wallet_command(_: argparse.Namespace) -> int:
    """Read only the local AWP wallet address."""

    local_wallet = read_local_awp_wallet()
    print_json(
        awp_result(
            operation="local-wallet",
            status=str(local_wallet.get("status") or "unknown"),
            local_wallet=local_wallet,
            recommended_action="read_bootstrap_guide_if_wallet_is_missing",
            summary=str(local_wallet.get("summary") or "local AWP wallet checked"),
        )
    )
    return 0


def challenge_command(args: argparse.Namespace) -> int:
    """Create a tmr AWP link challenge."""

    awp_wallet_address = normalize_evm_address(args.wallet_address, field_name="awp_wallet_address")
    credentials = load_credentials()
    base_urls = resolve_base_urls(
        identity_base_url=args.identity_base_url,
        intention_base_url=args.intention_base_url,
        credentials=credentials,
    )
    challenge = identity_agent_post(
        "/api/v1/agent-awp-links/challenges",
        {
            "chain_id": args.chain_id,
            "awp_wallet_address": awp_wallet_address,
            "requested_by": args.requested_by,
            "skill_name": "tmrwin-skill",
        },
        credentials=credentials,
        base_urls=base_urls,
        timeout=args.timeout,
    )
    print_json(
        awp_result(
            operation="challenge",
            status="challenge_created",
            data=challenge,
            recommended_action="sign_typed_data_with_awp_wallet_then_confirm",
            summary="AWP link challenge created; sign data.typed_data with awp-wallet sign-typed-data",
        )
    )
    return 0


def confirm_command(args: argparse.Namespace) -> int:
    """Confirm a tmr AWP link challenge with an AWP wallet signature."""

    signature = load_signature(args)
    credentials = load_credentials()
    base_urls = resolve_base_urls(
        identity_base_url=args.identity_base_url,
        intention_base_url=args.intention_base_url,
        credentials=credentials,
    )
    relationship = identity_agent_post(
        "/api/v1/agent-awp-links/confirm",
        {
            "challenge_id": args.challenge_id,
            "signature": signature,
        },
        credentials=credentials,
        base_urls=base_urls,
        timeout=args.timeout,
    )
    relationship_status = str(relationship.get("status") or "unknown")
    print_json(
        awp_result(
            operation="confirm",
            status="ok",
            relationship=relationship,
            recommended_action=str(relationship.get("next_action") or "none"),
            summary=f"AWP link confirm returned {relationship_status}",
        )
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""

    parser = argparse.ArgumentParser(description="check or link the current tmr.win Agent with an AWP wallet")
    subparsers = parser.add_subparsers(dest="command", required=True)

    status_parser = subparsers.add_parser("status", help="read the current tmr AWP relationship")
    add_base_url_args(status_parser)
    status_parser.add_argument("--chain-id", type=int, default=DEFAULT_AWP_CHAIN_ID)
    status_parser.add_argument("--check-local-wallet", action="store_true")
    status_parser.add_argument("--timeout", type=int, default=30)
    status_parser.set_defaults(func=status_command)

    local_wallet_parser = subparsers.add_parser("local-wallet", help="read local awp-wallet address without mutation")
    local_wallet_parser.set_defaults(func=local_wallet_command)

    challenge_parser = subparsers.add_parser("challenge", help="create a tmr AWP link challenge")
    add_base_url_args(challenge_parser)
    challenge_parser.add_argument("--wallet-address", required=True)
    challenge_parser.add_argument("--chain-id", type=int, default=DEFAULT_AWP_CHAIN_ID)
    challenge_parser.add_argument("--requested-by", default="tmrwin-skill")
    challenge_parser.add_argument("--timeout", type=int, default=30)
    challenge_parser.set_defaults(func=challenge_command)

    confirm_parser = subparsers.add_parser("confirm", help="confirm a tmr AWP link challenge")
    add_base_url_args(confirm_parser)
    confirm_parser.add_argument("--challenge-id", required=True)
    signature_group = confirm_parser.add_mutually_exclusive_group(required=True)
    signature_group.add_argument("--signature")
    signature_group.add_argument("--signature-file")
    signature_group.add_argument("--sign-response-file")
    confirm_parser.add_argument("--timeout", type=int, default=30)
    confirm_parser.set_defaults(func=confirm_command)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return int(args.func(args))
    except SkillError as exc:
        print_json(error_result(exc))
        return 2 if exc.status == "binding_required" else 1


if __name__ == "__main__":
    sys.exit(main())

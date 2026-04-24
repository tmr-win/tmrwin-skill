#!/usr/bin/env python3
"""Shared utilities for tmrwin-skill scripts."""

from __future__ import annotations

import argparse
import json
import os
import stat
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_SKILL_NAME = "tmrwin-skill"
DEFAULT_SKILL_VERSION = "1.1.0"
DEFAULT_REPO_URL = "https://github.com/tmr-win/tmrwin-skill"
DEFAULT_MANIFEST_URL = "https://raw.githubusercontent.com/tmr-win/tmrwin-skill/main/version.json"
DEFAULT_INSTALL_COMMAND = "skill install https://github.com/tmr-win/tmrwin-skill"
DEFAULT_GATEWAY_BASE_URL = "https://tmr.win"
DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_MAX_QUESTIONS = 1
RUN_RESULT_SCHEMA = "tmrwin-skill-run-result-v1"
QUESTION_CONTEXT_SCHEMA = "tmrwin-skill-question-context-v1"
MONITOR_RESULT_SCHEMA = "tmrwin-skill-monitor-result-v1"
DAEMON_STATUS_SCHEMA = "tmrwin-skill-daemon-status-v1"
NOTIFICATIONS_SCHEMA = "tmrwin-skill-notifications-v1"
DEFAULT_MONITOR_LIMIT = 20


def skill_root() -> Path:
    """Return the Skill repository root."""

    return Path(__file__).resolve().parent.parent


def version_manifest_path() -> Path:
    """Return the local version manifest path."""

    return skill_root() / "version.json"


def load_version_manifest() -> dict[str, Any]:
    """Load version metadata with safe defaults when the manifest is unavailable."""

    defaults: dict[str, Any] = {
        "schema": "tmrwin-skill-version-manifest-v1",
        "skill_name": DEFAULT_SKILL_NAME,
        "version": DEFAULT_SKILL_VERSION,
        "repo_url": DEFAULT_REPO_URL,
        "manifest_url": DEFAULT_MANIFEST_URL,
        "install_command": DEFAULT_INSTALL_COMMAND,
    }
    path = version_manifest_path()
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return defaults
    if not isinstance(payload, dict):
        return defaults
    merged = dict(defaults)
    for key in defaults:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            merged[key] = value.strip()
    return merged


SKILL_METADATA = load_version_manifest()
SKILL_NAME = str(SKILL_METADATA["skill_name"])
SKILL_VERSION = str(SKILL_METADATA["version"])
SKILL_REPO_URL = str(SKILL_METADATA["repo_url"])
SKILL_MANIFEST_URL = str(SKILL_METADATA["manifest_url"])
SKILL_INSTALL_COMMAND = str(SKILL_METADATA["install_command"])


class SkillError(Exception):
    """Error that maps cleanly into stable Skill JSON output."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status: str = "blocked",
        retryable: bool = False,
        http_status: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.retryable = retryable
        self.http_status = http_status
        self.details = details or {}


class HttpFailure(SkillError):
    """HTTP request failure."""


@dataclass(frozen=True)
class ServiceBaseUrls:
    """Service base URLs used by the current run."""

    identity: str
    intention: str


def utc_now_iso() -> str:
    """Return the current UTC timestamp in ISO format."""

    return datetime.now(timezone.utc).isoformat()


def parse_json_text(text: str, *, source: str) -> Any:
    """Parse JSON text and raise a stable SkillError on failure."""

    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise SkillError(
            "invalid_json",
            f"{source} is not valid JSON: {exc.msg}",
            status="blocked",
        ) from exc


def print_json(payload: dict[str, Any]) -> None:
    """Write exactly one JSON object to stdout."""

    sys.stdout.write(json.dumps(redact(payload), ensure_ascii=False, separators=(",", ":")) + "\n")


def print_diagnostic(message: str) -> None:
    """Write redacted diagnostics to stderr."""

    sys.stderr.write(str(message) + "\n")


def redact(value: Any) -> Any:
    """Recursively redact user-visible objects."""

    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            lowered = key.lower()
            if lowered in {"api_key", "authorization", "poll_token", "session_token"}:
                redacted[key] = mask_secret(str(item))
            else:
                redacted[key] = redact(item)
        return redacted
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def mask_secret(secret: str | None) -> str | None:
    """Keep minimal diagnostic characters while hiding the full secret."""

    if not secret:
        return None
    if len(secret) <= 8:
        return "***"
    return f"{secret[:4]}...{secret[-4:]}"


def state_dir() -> Path:
    """Return the user-level state directory."""

    return Path(os.environ.get("TMRWIN_SKILL_STATE_DIR", "~/.tmrwin-skill")).expanduser()


def credentials_path() -> Path:
    """Return the credential file path."""

    return state_dir() / "credentials.json"


def bind_sessions_dir() -> Path:
    """Return the bind-session cache directory."""

    return state_dir() / "bind-sessions"


def monitor_state_path() -> Path:
    """Return the local monitor state file path."""

    return state_dir() / "monitor-state.json"


def daemon_pid_path() -> Path:
    """Return the local daemon pid file path."""

    return state_dir() / "daemon.pid"


def daemon_status_path() -> Path:
    """Return the local daemon status file path."""

    return state_dir() / "daemon-status.json"


def notifications_path() -> Path:
    """Return the local daemon notifications file path."""

    return state_dir() / "notifications.json"


def ensure_private_dir(path: Path) -> None:
    """Create a directory intended for the current user only."""

    path.mkdir(parents=True, exist_ok=True)
    try:
        path.chmod(stat.S_IRWXU)
    except OSError:
        return


def write_private_json(path: Path, payload: dict[str, Any]) -> None:
    """Atomically write a private JSON file."""

    ensure_private_dir(path.parent)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent), text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
        try:
            os.chmod(tmp_name, stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            print_diagnostic("warning: could not restrict temporary credential file permissions")
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def read_json_file(path: Path, *, missing_code: str = "file_missing") -> dict[str, Any]:
    """Read a JSON object file."""

    if not path.exists():
        raise SkillError(missing_code, f"{path} does not exist", status="binding_required")
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except json.JSONDecodeError as exc:
        raise SkillError("credential_corrupt", f"{path} is not valid JSON", status="binding_required") from exc
    if not isinstance(payload, dict):
        raise SkillError("credential_corrupt", f"{path} must contain a JSON object", status="binding_required")
    return payload


def resolve_base_urls(
    *,
    identity_base_url: str | None = None,
    intention_base_url: str | None = None,
    credentials: dict[str, Any] | None = None,
) -> ServiceBaseUrls:
    """Resolve service base URLs with CLI and env taking precedence over stored credentials."""

    credential_urls = credentials.get("base_urls", {}) if isinstance(credentials, dict) else {}
    gateway = os.environ.get("TMRWIN_BASE_URL", DEFAULT_GATEWAY_BASE_URL).rstrip("/")
    identity = (
        identity_base_url
        or os.environ.get("TMRWIN_IDENTITY_BASE_URL")
        or credential_urls.get("identity")
        or f"{gateway}/identity-service"
    )
    intention = (
        intention_base_url
        or os.environ.get("TMRWIN_INTENTION_BASE_URL")
        or credential_urls.get("intention")
        or f"{gateway}/intention-market"
    )
    return ServiceBaseUrls(identity=identity.rstrip("/"), intention=intention.rstrip("/"))


def add_base_url_args(parser: argparse.ArgumentParser) -> None:
    """Add common service base URL arguments."""

    parser.add_argument("--identity-base-url", default=None)
    parser.add_argument("--intention-base-url", default=None)


def load_credentials() -> dict[str, Any]:
    """Load and validate the local credential."""

    path = credentials_path()
    if not path.exists():
        raise SkillError("credential_missing", "credential missing; bind tmr.win Agent", status="binding_required")
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except json.JSONDecodeError as exc:
        raise SkillError("credential_corrupt", "credential file is not valid JSON", status="binding_required") from exc
    if not isinstance(payload, dict):
        raise SkillError("credential_corrupt", "credential file must contain a JSON object", status="binding_required")
    required = ["api_key", "agent_id"]
    if any(not str(payload.get(field) or "").strip() for field in required):
        raise SkillError("credential_corrupt", "credential file misses required fields", status="binding_required")
    return payload


def save_credentials(bind_data: dict[str, Any], base_urls: ServiceBaseUrls) -> dict[str, Any]:
    """Persist the minimal credential state after a successful bind."""

    api_key = str(bind_data.get("api_key") or "").strip()
    agent_id = str(bind_data.get("selected_agent_id") or bind_data.get("agent_id") or "").strip()
    if not api_key or not agent_id:
        raise SkillError("invalid_response", "bound poll response misses api_key or selected_agent_id")
    payload = {
        "api_key": api_key,
        "agent_id": agent_id,
        "key_id": bind_data.get("key_id"),
        "key_prefix": bind_data.get("key_prefix"),
        "bound_at": bind_data.get("bound_at") or utc_now_iso(),
        "base_urls": {"identity": base_urls.identity, "intention": base_urls.intention},
        "skill_version": SKILL_VERSION,
    }
    write_private_json(credentials_path(), payload)
    return {
        "agent_id": payload["agent_id"],
        "key_id": payload.get("key_id"),
        "key_prefix": payload.get("key_prefix"),
        "bound_at": payload.get("bound_at"),
        "credential_path": str(credentials_path()),
    }


def load_bind_session(session_id: str) -> dict[str, Any]:
    """Load the poll token cached by bind_start."""

    safe_id = "".join(ch for ch in session_id if ch.isalnum() or ch in {"-", "_"})
    if not safe_id:
        raise SkillError("invalid_input", "session_id is required")
    path = bind_sessions_dir() / f"{safe_id}.json"
    payload = read_json_file(path, missing_code="bind_session_missing")
    if not str(payload.get("poll_token") or "").strip():
        raise SkillError("bind_session_failed", "bind session cache misses poll_token")
    return payload


def save_bind_session(bind_data: dict[str, Any], base_urls: ServiceBaseUrls, *, is_rebind: bool) -> dict[str, Any]:
    """Store the poll token in local state so it never appears in user output."""

    session_id = str(bind_data.get("session_id") or "").strip()
    poll_token = str(bind_data.get("poll_token") or "").strip()
    if not session_id or not poll_token:
        raise SkillError("invalid_response", "bind session response misses session_id or poll_token")
    payload = {
        "session_id": session_id,
        "poll_token": poll_token,
        "bind_url": bind_data.get("bind_url"),
        "status": bind_data.get("status"),
        "expires_at": bind_data.get("expires_at"),
        "base_urls": {"identity": base_urls.identity, "intention": base_urls.intention},
        "is_rebind": is_rebind,
        "created_at": utc_now_iso(),
    }
    write_private_json(bind_sessions_dir() / f"{session_id}.json", payload)
    return payload


def url_join(base_url: str, path: str) -> str:
    """Join a service base URL and a relative path."""

    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def request_json(
    method: str,
    url: str,
    *,
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> Any:
    """Perform a JSON HTTP request."""

    body = None
    request_headers = {"Accept": "application/json"}
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request_headers["Content-Type"] = "application/json"
    if headers:
        request_headers.update(headers)
    req = urllib.request.Request(url, data=body, headers=request_headers, method=method.upper())
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            text = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        error_text = exc.read().decode("utf-8", errors="replace")
        raise classify_http_failure(exc.code, error_text, url=url) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise HttpFailure(
            "network_error",
            "network error while calling tmr.win API",
            retryable=True,
            details={"url": strip_query(url)},
        ) from exc
    if not text.strip():
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise SkillError("invalid_response", "HTTP response is not valid JSON", details={"url": strip_query(url)}) from exc


def classify_http_failure(status_code: int, body: str, *, url: str = "") -> HttpFailure:
    """Map HTTP failures into stable Skill errors."""

    retryable = status_code >= 500
    if status_code == 401:
        return HttpFailure("binding_expired", "Agent credential rejected", status="binding_required", http_status=401)
    if status_code == 409:
        return HttpFailure("already_submitted", "answer already submitted", http_status=409)
    if status_code == 410:
        return HttpFailure("bind_session_expired", "bind session expired", status="binding_required", http_status=410)
    if status_code >= 500:
        return HttpFailure(
            "network_error",
            "server error while calling tmr.win API",
            retryable=True,
            http_status=status_code,
            details={"url": strip_query(url), "body": safe_error_body(body)},
        )
    return HttpFailure(
        "server_rejected",
        "server rejected request",
        http_status=status_code,
        details={"url": strip_query(url), "body": safe_error_body(body)},
    )


def safe_error_body(body: str) -> str:
    """Compress and redact an error body."""

    clean = " ".join(str(body or "").split())
    if len(clean) > 240:
        clean = clean[:237] + "..."
    return clean.replace("Bearer ", "Bearer ***")


def strip_query(url: str) -> str:
    """Strip URL query parameters to reduce leakage risk."""

    parsed = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


def unwrap_identity_response(raw: Any) -> dict[str, Any]:
    """Read ApiResponse.data from identity-service."""

    if not isinstance(raw, dict):
        raise SkillError("invalid_response", "identity response must be JSON object")
    data = raw.get("data")
    if not isinstance(data, dict):
        raise SkillError("invalid_response", "identity response misses data object")
    return data


def bearer_headers(credentials: dict[str, Any]) -> dict[str, str]:
    """Build Agent API authorization headers."""

    api_key = str(credentials.get("api_key") or "").strip()
    if not api_key:
        raise SkillError("credential_corrupt", "credential misses api_key", status="binding_required")
    return {"Authorization": f"Bearer {api_key}"}


def build_query(params: dict[str, Any]) -> str:
    """Build a query string."""

    filtered = {key: value for key, value in params.items() if value is not None}
    return urllib.parse.urlencode(filtered)


def agent_get(
    path: str,
    *,
    params: dict[str, Any] | None = None,
    credentials: dict[str, Any] | None = None,
    base_urls: ServiceBaseUrls | None = None,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> Any:
    """Call a read-only intention-market Agent API route."""

    creds = credentials or load_credentials()
    urls = base_urls or resolve_base_urls(credentials=creds)
    query = build_query(params or {})
    url = url_join(urls.intention, path)
    if query:
        url = f"{url}?{query}"
    return request_json("GET", url, headers=bearer_headers(creds), timeout=timeout)


def agent_post(
    path: str,
    payload: dict[str, Any],
    *,
    credentials: dict[str, Any] | None = None,
    base_urls: ServiceBaseUrls | None = None,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> Any:
    """Call a write intention-market Agent API route."""

    creds = credentials or load_credentials()
    urls = base_urls or resolve_base_urls(credentials=creds)
    return request_json("POST", url_join(urls.intention, path), payload=payload, headers=bearer_headers(creds), timeout=timeout)


def fetch_unanswered_questions(
    *,
    limit: int = DEFAULT_MONITOR_LIMIT,
    credentials: dict[str, Any] | None = None,
    base_urls: ServiceBaseUrls | None = None,
) -> list[dict[str, Any]]:
    """Fetch and normalize unanswered questions for the current Agent."""

    raw = agent_get(
        "/api/v1/agent/questions",
        params={"limit": limit, "offset": 0, "answer_status": "unanswered"},
        credentials=credentials,
        base_urls=base_urls,
    )
    items = raw.get("items", []) if isinstance(raw, dict) else []
    return [normalize_question(item) for item in items if isinstance(item, dict)]


def normalize_question(item: dict[str, Any]) -> dict[str, Any]:
    """Normalize question context fields."""

    return {
        "question_id": str(item.get("question_id") or item.get("id") or ""),
        "question_text": item.get("question_text") or item.get("title") or "",
        "question_type": item.get("question_type"),
        "category": item.get("category"),
        "deadline": item.get("deadline"),
        "options": item.get("options") if isinstance(item.get("options"), dict) else None,
        "can_answer": bool(item.get("can_answer", True)),
        "answer_hint": item.get("answer_hint"),
    }


def run_result(
    *,
    status: str,
    summary: str,
    items: list[dict[str, Any]] | None = None,
    needs_rebind: bool = False,
    retryable: bool = False,
    diagnostics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the final run result payload."""

    safe_items = items or []
    result: dict[str, Any] = {
        "schema": RUN_RESULT_SCHEMA,
        "version": SKILL_VERSION,
        "status": status,
        "summary": summary,
        "items": safe_items,
        "needs_rebind": needs_rebind,
        "retryable": retryable,
    }
    result["counts"] = {
        "answered": sum(1 for item in safe_items if item.get("status") == "answered"),
        "skipped": sum(1 for item in safe_items if item.get("status") == "skipped"),
        "failed": sum(1 for item in safe_items if item.get("status") == "failed"),
    }
    if diagnostics:
        result["diagnostics"] = diagnostics
    return result


def monitor_result(
    *,
    status: str,
    summary: str,
    checked_at: str | None = None,
    question_ids: list[str] | None = None,
    unanswered_count: int | None = None,
    changed: bool | None = None,
    recommended_action: str | None = None,
    needs_rebind: bool = False,
    retryable: bool = False,
    diagnostics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a monitor result payload."""

    result: dict[str, Any] = {
        "schema": MONITOR_RESULT_SCHEMA,
        "version": SKILL_VERSION,
        "status": status,
        "summary": summary,
        "checked_at": checked_at or utc_now_iso(),
        "question_ids": question_ids or [],
        "unanswered_count": unanswered_count if unanswered_count is not None else len(question_ids or []),
        "recommended_action": recommended_action,
        "needs_rebind": needs_rebind,
        "retryable": retryable,
    }
    if changed is not None:
        result["changed"] = changed
    if diagnostics:
        result["diagnostics"] = diagnostics
    return result


def error_result(exc: SkillError) -> dict[str, Any]:
    """Convert SkillError into a final run result."""

    if exc.status == "binding_required" or exc.code in {"credential_missing", "credential_corrupt", "binding_expired"}:
        return run_result(
            status="binding_required",
            summary=exc.message,
            items=[],
            needs_rebind=True,
            retryable=False,
            diagnostics={"failure_reason": exc.code, "http_status": exc.http_status},
        )
    return run_result(
        status="blocked",
        summary=exc.message,
        items=[],
        retryable=exc.retryable,
        diagnostics={"failure_reason": exc.code, "http_status": exc.http_status, **exc.details},
    )


def monitor_error_result(exc: SkillError, *, checked_at: str | None = None) -> dict[str, Any]:
    """Convert SkillError into a monitor result."""

    if exc.status == "binding_required" or exc.code in {"credential_missing", "credential_corrupt", "binding_expired"}:
        return monitor_result(
            status="binding_required",
            summary=exc.message,
            checked_at=checked_at,
            recommended_action="rebind",
            needs_rebind=True,
            retryable=False,
            diagnostics={"failure_reason": exc.code, "http_status": exc.http_status},
        )
    return monitor_result(
        status="blocked",
        summary=exc.message,
        checked_at=checked_at,
        retryable=exc.retryable,
        diagnostics={"failure_reason": exc.code, "http_status": exc.http_status, **exc.details},
    )


PLACEHOLDER_SOURCES = {
    "n/a",
    "na",
    "none",
    "unknown",
    "various sources",
    "example",
    "source",
    "sources",
    "tbd",
}


def read_json_input(*, file_path: str | None, stdin_allowed: bool = True) -> Any:
    """Read JSON from a file path or stdin."""

    if file_path and file_path != "-":
        return read_json_file(Path(file_path), missing_code="input_missing")
    if stdin_allowed and not sys.stdin.isatty():
        text = sys.stdin.read()
        if text.strip():
            return parse_json_text(text, source="stdin")
    raise SkillError("invalid_input", "JSON input is required")


def normalize_answer_draft(question: dict[str, Any], draft: dict[str, Any]) -> dict[str, Any]:
    """Normalize legacy fields into the current submit schema when unambiguous."""

    if not isinstance(draft, dict):
        raise SkillError("invalid_input", "answer draft must be an object")
    normalized = dict(draft)
    if "probability_pct" not in normalized and "probability" in normalized:
        normalized["probability_pct"] = normalized.get("probability")
    if "answer_content" not in normalized and isinstance(normalized.get("arguments"), list):
        normalized["answer_content"] = "\n".join(str(item) for item in normalized["arguments"] if str(item).strip())
    if "summary" not in normalized and isinstance(normalized.get("arguments"), list) and normalized["arguments"]:
        normalized["summary"] = str(normalized["arguments"][0])
    if "selected_option_key" not in normalized and "stance" in normalized:
        mapped = map_stance_to_option(question.get("options"), str(normalized.get("stance") or ""))
        if mapped:
            normalized["selected_option_key"] = mapped
    return normalized


def map_stance_to_option(options: Any, stance: str) -> str | None:
    """Map a yes/no stance to a concrete option key."""

    value = stance.strip().lower()
    if value not in {"yes", "no"} or not isinstance(options, dict):
        return None
    for key, label in options.items():
        key_text = str(key).strip().lower()
        label_text = str(label).strip().lower()
        if value in {key_text, label_text}:
            return str(key)
    return None


def validate_answer_draft(question: dict[str, Any], draft: dict[str, Any]) -> tuple[bool, dict[str, Any] | str]:
    """Run local answer quality gates."""

    normalized = normalize_answer_draft(question, draft)
    selected_option_key = str(normalized.get("selected_option_key") or "").strip()
    options = question.get("options")
    if not selected_option_key or (isinstance(options, dict) and selected_option_key not in options):
        return False, "gate_selected_option_invalid"

    probability = normalized.get("probability_pct")
    if isinstance(probability, bool) or not isinstance(probability, int) or probability <= 50 or probability > 99:
        return False, "gate_probability_out_of_range"

    answer_content = str(normalized.get("answer_content") or "").strip()
    if not answer_content:
        return False, "gate_answer_content_missing"

    reasoning_chain = normalized.get("reasoning_chain")
    if not isinstance(reasoning_chain, list):
        return False, "gate_reasoning_chain_too_short"
    reasoning_items = [str(item).strip() for item in reasoning_chain if str(item).strip()]
    if not reasoning_items or sum(len(item) for item in reasoning_items) < 100:
        return False, "gate_reasoning_chain_too_short"

    data_sources = normalized.get("data_sources")
    if not isinstance(data_sources, list):
        return False, "gate_data_sources_missing"
    source_items = [str(item).strip() for item in data_sources if is_meaningful_source(item)]
    if not source_items:
        return False, "gate_data_sources_missing"

    confidence = normalized.get("confidence")
    if confidence is not None and (isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or confidence < 0 or confidence > 1):
        return False, "gate_confidence_out_of_range"

    payload = {
        "selected_option_key": selected_option_key,
        "probability_pct": probability,
        "answer_content": answer_content,
        "summary": str(normalized.get("summary")).strip() if normalized.get("summary") is not None else None,
        "reasoning_chain": reasoning_items,
        "data_sources": source_items,
        "confidence": float(confidence) if confidence is not None else None,
    }
    return True, payload


def is_meaningful_source(value: Any) -> bool:
    """Return whether a data source is meaningful rather than placeholder text."""

    text = str(value or "").strip()
    return bool(text) and text.lower() not in PLACEHOLDER_SOURCES


def submit_answer(question: dict[str, Any], draft: dict[str, Any], *, dry_run: bool = False) -> dict[str, Any]:
    """Submit a single answer after local gates pass."""

    question_id = str(question.get("question_id") or "").strip()
    if not question_id:
        raise SkillError("invalid_input", "question_id is required")
    is_valid, payload_or_reason = validate_answer_draft(question, draft)
    if not is_valid:
        return {
            "question_id": question_id,
            "status": "failed",
            "failure_reason": payload_or_reason,
            "summary": f"local gate failed: {payload_or_reason}",
        }
    payload = payload_or_reason
    if dry_run:
        return {
            "question_id": question_id,
            "status": "answered",
            "summary": "dry-run gate passed; submit skipped",
            "dry_run": True,
        }
    try:
        response = agent_post(f"/api/v1/agent/questions/{urllib.parse.quote(question_id)}/answers", payload)
    except HttpFailure as exc:
        if exc.code == "already_submitted":
            return {
                "question_id": question_id,
                "status": "skipped",
                "failure_reason": "already_submitted",
                "summary": "already submitted; not retrying",
            }
        if exc.code == "binding_expired":
            return {
                "question_id": question_id,
                "status": "failed",
                "failure_reason": "binding_expired",
                "summary": "credential rejected by Agent API",
                "needs_rebind": True,
            }
        return {
            "question_id": question_id,
            "status": "failed",
            "failure_reason": exc.code if exc.code in {"network_error", "server_rejected", "invalid_response"} else "unknown",
            "summary": exc.message,
            "retryable": exc.retryable,
        }
    answer_id = response.get("answer_id") if isinstance(response, dict) else None
    return {
        "question_id": question_id,
        "status": "answered",
        "answer_id": answer_id,
        "summary": f"submitted selected_option_key={payload['selected_option_key']} probability_pct={payload['probability_pct']}",
    }


def max_questions_from_args(value: int | None) -> int:
    """Resolve the per-run question limit."""

    raw_default = os.environ.get("TMRWIN_SKILL_MAX_QUESTIONS")
    default_limit = DEFAULT_MAX_QUESTIONS
    if raw_default:
        try:
            default_limit = max(1, int(raw_default))
        except ValueError:
            default_limit = DEFAULT_MAX_QUESTIONS
    if value is None:
        return default_limit
    return max(1, min(int(value), default_limit if raw_default else int(value)))


def monitor_limit_from_args(value: int | None) -> int:
    """Resolve the per-check monitor limit."""

    if value is None:
        return DEFAULT_MONITOR_LIMIT
    return max(1, int(value))


def build_question_snapshot(questions: list[dict[str, Any]], *, checked_at: str | None = None) -> dict[str, Any]:
    """Build a redacted snapshot for monitor change detection."""

    question_ids = [str(item.get("question_id") or "").strip() for item in questions if str(item.get("question_id") or "").strip()]
    return {
        "checked_at": checked_at or utc_now_iso(),
        "unanswered_count": len(question_ids),
        "question_ids": question_ids,
    }


def load_optional_snapshot(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    """Load a snapshot file if present; return a warning instead of failing on corruption."""

    if not path.exists():
        return None, None
    try:
        payload = read_json_file(path, missing_code="monitor_state_missing")
    except SkillError:
        return None, "monitor_state_corrupt"
    return payload, None


def snapshots_changed(previous: dict[str, Any] | None, current: dict[str, Any]) -> bool:
    """Return whether the current snapshot differs from the previous snapshot."""

    if previous is None:
        return bool(current.get("question_ids")) or int(current.get("unanswered_count", 0)) > 0
    return (
        int(previous.get("unanswered_count", -1)) != int(current.get("unanswered_count", -2))
        or list(previous.get("question_ids", [])) != list(current.get("question_ids", []))
    )

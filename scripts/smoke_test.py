#!/usr/bin/env python3
"""Run script-level smoke tests without network access."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

import _common


class SkillSmokeTest(unittest.TestCase):
    """Cover credential, bind-state, gating, and redaction paths."""

    def test_missing_credential_maps_to_binding_required(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            old = os.environ.get("TMRWIN_SKILL_STATE_DIR")
            os.environ["TMRWIN_SKILL_STATE_DIR"] = tmp
            try:
                with self.assertRaises(_common.SkillError) as ctx:
                    _common.load_credentials()
                self.assertEqual(ctx.exception.code, "credential_missing")
                self.assertEqual(ctx.exception.status, "binding_required")
            finally:
                if old is None:
                    os.environ.pop("TMRWIN_SKILL_STATE_DIR", None)
                else:
                    os.environ["TMRWIN_SKILL_STATE_DIR"] = old

    def test_corrupt_credential_maps_to_binding_required(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            old = os.environ.get("TMRWIN_SKILL_STATE_DIR")
            os.environ["TMRWIN_SKILL_STATE_DIR"] = tmp
            try:
                Path(tmp, "credentials.json").write_text("{bad json", encoding="utf-8")
                with self.assertRaises(_common.SkillError) as ctx:
                    _common.load_credentials()
                self.assertEqual(ctx.exception.code, "credential_corrupt")
            finally:
                if old is None:
                    os.environ.pop("TMRWIN_SKILL_STATE_DIR", None)
                else:
                    os.environ["TMRWIN_SKILL_STATE_DIR"] = old

    def test_save_credentials_redacts_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            old = os.environ.get("TMRWIN_SKILL_STATE_DIR")
            os.environ["TMRWIN_SKILL_STATE_DIR"] = tmp
            try:
                saved = _common.save_credentials(
                    {
                        "api_key": "tmr_live_secret_1234567890",
                        "selected_agent_id": "agent-1",
                        "key_id": "key-1",
                        "key_prefix": "tmr_live",
                    },
                    _common.ServiceBaseUrls(identity="https://id.example", intention="https://im.example"),
                )
                self.assertEqual(saved["agent_id"], "agent-1")
                redacted = _common.redact({"api_key": "tmr_live_secret_1234567890"})
                self.assertNotIn("1234567890", json.dumps(redacted))
            finally:
                if old is None:
                    os.environ.pop("TMRWIN_SKILL_STATE_DIR", None)
                else:
                    os.environ["TMRWIN_SKILL_STATE_DIR"] = old

    def test_gate_success_and_failures(self) -> None:
        question = {
            "question_id": "q1",
            "options": {"yes": "Yes", "no": "No"},
        }
        valid = {
            "selected_option_key": "yes",
            "probability_pct": 72,
            "answer_content": "The answer is yes because the observable evidence points in that direction.",
            "summary": "Yes is more likely.",
            "reasoning_chain": [
                "The first premise establishes the relevant trend from a named source and connects it to the target event.",
                "The second premise weighs the contrary case and still leaves the selected option more likely than not.",
            ],
            "data_sources": ["https://example.com/report"],
            "confidence": 0.72,
        }
        self.assertTrue(_common.validate_answer_draft(question, valid)[0])
        bad = dict(valid)
        bad["data_sources"] = ["various sources"]
        self.assertEqual(_common.validate_answer_draft(question, bad), (False, "gate_data_sources_missing"))
        bad = dict(valid)
        bad["probability_pct"] = 50
        self.assertEqual(_common.validate_answer_draft(question, bad), (False, "gate_probability_out_of_range"))

    def test_http_mapping(self) -> None:
        self.assertEqual(_common.classify_http_failure(401, "", url="https://x/y").code, "binding_expired")
        self.assertEqual(_common.classify_http_failure(409, "", url="https://x/y").code, "already_submitted")
        self.assertTrue(_common.classify_http_failure(500, "", url="https://x/y").retryable)


def main() -> int:
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(SkillSmokeTest)
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    payload = {
        "schema": "tmrwin-skill-smoke-test-v1",
        "status": "ok" if result.wasSuccessful() else "failed",
        "testsRun": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
    }
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())

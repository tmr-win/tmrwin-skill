#!/usr/bin/env python3
"""Validate the tmrwin-skill directory structure and key contracts."""

from __future__ import annotations

import json
import py_compile
import re
import sys
import tempfile
from pathlib import Path


FORBIDDEN_NAMES = {
    "INSTALLATION_GUIDE.md",
    "QUICK_REFERENCE.md",
    "CHANGELOG.md",
    "agents/openai.yaml",
}

REQUIRED_REFERENCES = {
    "auth-and-binding.md",
    "agent-api-contract.md",
    "answer-quality-gates.md",
    "run-result-schema.md",
    "error-taxonomy.md",
    "cross-host-validation.md",
}

REQUIRED_SCRIPTS = {
    "bind_start.py",
    "bind_poll.py",
    "current_agent.py",
    "list_questions.py",
    "submit_answer.py",
    "list_my_answers.py",
    "run_cycle.py",
    "smoke_test.py",
}


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    errors: list[str] = []
    skill = root / "SKILL.md"
    if not skill.exists():
        errors.append("SKILL.md missing")
    else:
        text = skill.read_text(encoding="utf-8")
        match = re.match(r"^---\n(.*?)\n---\n", text, re.S)
        if not match:
            errors.append("SKILL.md frontmatter missing")
        else:
            frontmatter = match.group(1)
            if "name: tmrwin-skill" not in frontmatter:
                errors.append("frontmatter name must be tmrwin-skill")
            if "description:" not in frontmatter:
                errors.append("frontmatter description missing")
            extra_fields = [line.split(":", 1)[0] for line in frontmatter.splitlines() if ":" in line and not line.startswith("  ")]
            if set(extra_fields) - {"name", "description"}:
                errors.append("frontmatter must only contain name and description")
        for reference in REQUIRED_REFERENCES:
            if f"references/{reference}" not in text:
                errors.append(f"SKILL.md does not mention references/{reference}")

    for forbidden in FORBIDDEN_NAMES:
        if (root / forbidden).exists():
            errors.append(f"forbidden file exists: {forbidden}")

    for reference in REQUIRED_REFERENCES:
        if not (root / "references" / reference).exists():
            errors.append(f"required reference missing: {reference}")
    for script in REQUIRED_SCRIPTS:
        path = root / "scripts" / script
        if not path.exists():
            errors.append(f"required script missing: {script}")
        else:
            try:
                with tempfile.TemporaryDirectory() as tmp:
                    py_compile.compile(str(path), cfile=str(Path(tmp) / f"{script}.pyc"), doraise=True)
            except py_compile.PyCompileError as exc:
                errors.append(f"script does not compile: {script}: {exc.msg}")

    result = {"schema": "tmrwin-skill-quick-validate-v1", "status": "ok" if not errors else "failed", "errors": errors}
    sys.stdout.write(json.dumps(result, ensure_ascii=False, separators=(",", ":")) + "\n")
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())

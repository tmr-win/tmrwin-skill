# Cross-Host Validation

The Skill core is universal. Validate hosts against the same folder, not host-specific forks.

## Target Hosts

- Claude Code
- OpenClaw
- Cursor
- Codex
- Gemini CLI
- Windsurf

## Matrix

| Check | Expected result |
|---|---|
| Load Skill | host sees `SKILL.md` frontmatter `name: tmrwin-skill` and description triggers on bind, answer, history, and rebind requests |
| Progressive disclosure | host can discover all references directly from `SKILL.md` |
| Scripts | host can run Python scripts from `scripts/` without host-specific adapters |
| Credentials | host uses `${TMRWIN_SKILL_STATE_DIR:-~/.tmrwin-skill}` unless explicitly overridden |
| Binding | host can start bind, show `bind_url`, and poll without exposing `api_key` |
| Query | host can list unanswered questions with direct JSON stdout |
| Submit | host can pass answer draft JSON through gates before HTTP write |
| Run result | host can consume one `tmrwin-skill-run-result-v1` final object |
| Distribution | Skill directory has no `agents/openai.yaml`, README, install guide, quick reference, changelog, or host-specific fork |

## Validation Commands

```bash
python3 scripts/quick_validate.py .
python3 scripts/smoke_test.py
```

Run these from `skills/tmrwin-skill`.

## Non-Goals

Do not add host adapters, host-specific protocol forks, or per-host copies of references. If a future host needs optional metadata, add it as a separate distribution concern after validating that the universal core remains unchanged.

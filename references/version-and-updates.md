# Version And Updates

`tmrwin-skill` publishes a machine-readable manifest at the repository root so every supported host can make the same update decision.

## Public Manifest

Path:

```text
version.json
```

Expected fields:

```json
{
  "schema": "tmrwin-skill-version-manifest-v1",
  "skill_name": "tmrwin-skill",
  "version": "1.1.3",
  "repo_url": "https://github.com/tmr-win/tmrwin-skill",
  "manifest_url": "https://raw.githubusercontent.com/tmr-win/tmrwin-skill/main/version.json",
  "update_strategy": "repo_distribution"
}
```

## Check Script

Use:

```bash
python3 scripts/check_version.py
```

Optional override for testing or private mirrors:

```bash
TMRWIN_SKILL_MANIFEST_URL=https://example.com/version.json python3 scripts/check_version.py
```

Result schema:

```json
{
  "schema": "tmrwin-skill-version-check-v1",
  "skill_name": "tmrwin-skill",
  "status": "update_available",
  "local_version": "1.1.3",
  "latest_version": "1.2.0",
  "update_available": true,
  "manifest_url": "https://raw.githubusercontent.com/tmr-win/tmrwin-skill/main/version.json",
  "repo_url": "https://github.com/tmr-win/tmrwin-skill",
  "update_strategy": "repo_distribution",
  "summary": "a newer tmrwin-skill version is available from the public repository: 1.2.0"
}
```

## Status Meanings

| Status | Meaning | Host behavior |
|---|---|---|
| `up_to_date` | installed Skill matches the latest public manifest | continue normally |
| `update_available` | manifest reports a newer version | show the repository URL and tell the user to refresh the Skill through the host's normal update flow, then continue unless the user wants to update first |
| `unknown` | remote manifest could not be checked safely | continue onboarding without blocking |

## First-Run Rule

When the user invokes `/tmrwin-skill` without a clear task, hosts should:

1. Run `check_version.py`.
2. If `status=update_available`, show the latest version, `repo_url`, and tell the user to refresh the Skill through the host's normal update flow.
3. Continue credential checks and browser bind guidance even if the version check fails or an update exists.

Version checks are advisory. They must not auto-upgrade, auto-bind, or block runtime use when GitHub is temporarily unavailable.

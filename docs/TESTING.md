# Beta Testing Skill Sync

This checklist is for people trying Skill Sync during the public beta.

## Beginner Test Flow

Ask Codex:

```text
/skill-sync doctor
```

Then:

```text
/skill-sync check
```

Only after reviewing the output, try:

```text
/skill-sync update
```

## What to Check

- `doctor` makes no changes.
- `check` makes no changes.
- Skills are grouped as Official, Community, or Needs Setup.
- Unknown skills are skipped.
- Local or private skills are not overwritten.
- Updates require confirmation before applying.
- Backups are created before replacement.
- Failed safety checks are understandable.
- Codex plugin warnings are not confusing outside Codex.

## Suggested Beta Scenarios

Try with:

- One known public skill
- One private or local skill
- One skill with no known source
- One valid manifest entry
- One intentionally bad manifest entry, if you are comfortable testing failure output

## Advanced Direct CLI Checks

From the repository root:

```bash
python3 skill-sync/scripts/update_codex_assets.py --doctor
python3 skill-sync/scripts/update_codex_assets.py --doctor --json
python3 skill-sync/scripts/update_codex_assets.py --inventory --no-plugins
python3 skill-sync/scripts/update_codex_assets.py --json --no-plugins
```

Run the built-in checks:

```bash
python3 skill-sync/scripts/update_codex_assets.py --self-test
python3 -m compileall skill-sync/scripts/update_codex_assets.py
git diff --check
```

## What to Report

Please report:

- Installation friction
- Confusing output
- Mapping confusion
- Any behavior that made you hesitate before update
- Restore or backup confusion
- Any failure that looks like a Python traceback
- Any case where Skill Sync seems to guess too much

Use the issue templates in `.github/ISSUE_TEMPLATE/`.

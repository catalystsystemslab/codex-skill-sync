## Summary

What does this change?

## Type of Change

- [ ] Docs
- [ ] Bug fix
- [ ] Safety hardening
- [ ] Tests
- [ ] Feature proposal
- [ ] Other

## Runtime Behavior

Does this change how Skill Sync updates files?

- [ ] No
- [ ] Yes

If yes, explain:

## JSON Output

Does this change JSON output keys, status values, or report structure?

- [ ] No
- [ ] Yes

If yes, explain:

## Safety Checklist

- [ ] Does not weaken dry-run behavior
- [ ] Does not overwrite unknown skills
- [ ] Does not bypass backups
- [ ] Does not weaken path validation
- [ ] Does not weaken remote skill tree validation
- [ ] Keeps JSON output stable, or explains why it changed
- [ ] Adds or updates tests where needed

## Verification

Commands run:

```bash
python3 skill-sync/scripts/update_codex_assets.py --self-test
python3 -m compileall skill-sync/scripts/update_codex_assets.py
python3 skill-sync/scripts/update_codex_assets.py --doctor
python3 skill-sync/scripts/update_codex_assets.py --doctor --json
git diff --check
```

## Notes for Reviewer

Anything specific to review closely?

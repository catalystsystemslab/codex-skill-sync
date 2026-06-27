# Contributing to Skill Sync

Thanks for helping improve Skill Sync.

Skill Sync is designed for users who may not have deep technical background, so changes should be safe, clear, and beginner-friendly.

## Good First Contributions

- Improve documentation
- Add examples
- Improve error messages
- Add self-test coverage
- Fix edge cases
- Improve support notes for Codex, Claude Code, Cursor, and other SKILL.md-style workflows
- Create demo screenshots or GIFs

## Design Principles

- Dry-run first
- Never guess unknown repositories
- Never overwrite local or private skills without explicit mapping
- Back up before replacing a skill folder
- Keep the tool stdlib-only
- Prefer clear beginner output over technical jargon
- Keep JSON output stable for agents
- Refuse unsafe remote skill trees instead of asking users to override safety checks

## Before Opening a Pull Request

Run these commands from the repository root:

```bash
python3 skill-sync/scripts/update_codex_assets.py --self-test
python3 -m compileall skill-sync/scripts/update_codex_assets.py
python3 skill-sync/scripts/update_codex_assets.py --doctor
python3 skill-sync/scripts/update_codex_assets.py --doctor --json
git diff --check
```

If your change touches inventory or non-Codex usage, also run:

```bash
python3 skill-sync/scripts/update_codex_assets.py --inventory --no-plugins
```

## Pull Request Guidelines

Please include:

- What changed
- Why it is needed
- Whether it changes runtime behavior
- How you tested it
- Any safety considerations

For larger features, open an issue first.

## Runtime Behavior Changes

Changes that affect file replacement, source mapping, plugin updates, remote repository handling, symlink handling, backups, or manifest parsing need extra care.

Please explain:

- What user-visible behavior changes
- What safety checks are added or changed
- Whether JSON output changes
- How failures are reported to beginner users

## Features That Need Discussion First

Open an issue before implementing:

- `--map-skill`
- `--restore`
- file-level diff summaries
- automatic scheduled apply
- package registry support
- any behavior that applies updates without explicit confirmation

## Documentation Style

Write for users who may not know Git, JSON, Python tracebacks, branches, manifests, or symlinks.

Prefer:

```text
Needs Setup means Skill Sync does not know where this skill came from, so it will not update it.
```

Avoid:

```text
Unmapped source object has no URL.
```

# Feedback Guide

Skill Sync is in public beta. The most useful feedback is about trust, safety, and beginner clarity.

## Most Useful Feedback

Please tell us:

- Was installation clear?
- Did `/skill-sync doctor` make sense?
- Did `/skill-sync check` make you trust the tool?
- Was Needs Setup confusing?
- Did you understand what would happen before update?
- Did backup and restore guidance feel sufficient?
- Did any output feel too technical?
- Did any failure feel scary or unclear?

## What to Include

When possible, include:

- The command or prompt you ran
- The output you saw
- Your agent/editor: Codex, Claude Code, Cursor, or other
- Your operating system
- Whether Codex CLI is installed
- Whether the skill is public, private, or local-only

Remove private repository URLs, local usernames, tokens, or private paths before posting.

## Current Feature Priorities

The next feature should come from real user friction.

Likely candidates:

- Easier source mapping
- Restore command
- File-level diff summary before apply
- Better scheduled check automation
- Easier install flow

## Not Planned Until Users Ask

These are intentionally deferred:

- `--map-skill`
- `--restore`
- file-level diff summaries
- automatic scheduled apply
- package registry support
- broad marketplace behavior

Skill Sync is currently positioned as a safe maintenance tool, not a universal package manager.

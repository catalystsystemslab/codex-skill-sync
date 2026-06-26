---
name: skill-sync
description: Simple sync flow for installed SKILL.md skills and Codex plugins. Use when the user says /skill-sync, check skills, update skills, run all skill updates, map skill repos, refresh Codex plugins, or create weekly skill maintenance.
---

# Skill Sync

Keep installed skills and Codex plugins current. `check`, `update`, and
`run all` all start the same inventory and mapping flow.

## Start Here

First list what is installed, no matter which command the user chose:

```bash
python3 <skill-dir>/scripts/update_codex_assets.py --inventory --json --report skill-update-report.json
```

Show the result as three groups:

- Official
- Non Official
- Not Mapped

Blank repo means the source is not confirmed. Do not guess.

## Commands

For `check`:

1. Run inventory.
2. If Not Mapped has anything, ask whether to map repos now or skip mapping for
   this run.
3. If the user maps repos, save only confident matches.
4. Run a dry update check. Do not apply.

```bash
python3 <skill-dir>/scripts/update_codex_assets.py --json --report skill-update-report.json
```

For `update` or `run all`:

1. Run inventory.
2. If Not Mapped has anything, ask whether to map repos now or skip mapping for
   this run.
3. If the user maps repos, save only confident matches.
4. Show the repo list with blanks for uncertain repos.
5. Ask for update confirmation.
6. Apply updates.
7. After the first successful update, ask whether to create a weekly automation.

```bash
python3 <skill-dir>/scripts/update_codex_assets.py --apply --json --report skill-update-report.json
```

## Mapping

Use `~/.codex/skill-sources.json` as the default saved mapping so the user does
not need to map the same skills again. If the user supplies another manifest,
use that instead.

Only confirmed repo mappings persist. If the user skips mapping for this run,
do not mark those skills local unless they explicitly say the skill is private
or local-only.

If the user chooses Map, public GitHub/web search is already part of the task.
Proceed with search tools and only ask again if the runtime blocks network
access or a repo match is uncertain.

Read `references/manifest.example.json` before editing a manifest.

For each Not Mapped skill:

- Search public GitHub first. Use the exact skill name plus unique words from
  its frontmatter or heading.
- Prefer the upstream public repo with strong evidence: exact `SKILL.md`
  match, same description/name, active repo, and visible community use such as
  stars.
- Do not map Not Mapped skills to `catalystsystemslab/<skill>`,
  `isaaclim/<skill>`, or another user/org mirror unless the installed skill
  itself names that repo as its source or the user confirms it.
- Trust a repo only when it contains that skill's `SKILL.md` at the repo root or
  a clear subfolder.
- Save confirmed matches with `url`, `branch`, and `subpath`.
- If unsure, leave the repo blank or ask the user for the link.
- Mark private/local skills as local:

```json
{ "name": "my-private-skill", "root": "~/.codex/skills", "kind": "local" }
```

## Status Words

- `current`: already okay.
- `update_available`: update found, not applied yet.
- `updated`: replaced after backup.
- `skipped: unknown source`: needs a repo link or local marking.
- `failed`: inspect network, auth, branch, or subpath.

## Safety

- Default to dry-run unless the user clearly asks to update.
- Back up before replacing a skill folder.
- Never overwrite Not Mapped skills.
- Do not migrate a skill to a similar repo without confirmation.
- The script replaces whole skill folders; it does not merge local edits.
- Codex plugin updates are Codex-only.

## Automation

Offer weekly automation only after a successful update. Weekly is the default;
bi-weekly is fine for stable setups.

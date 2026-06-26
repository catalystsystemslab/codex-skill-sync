# Skill Sync

`skill-sync` keeps installed `SKILL.md` skills and Codex plugins up to date.

## What It Does

- Lists installed skills and plugins as Official, Non Official, or Not Mapped.
- Saves confirmed skill-to-GitHub mappings in `~/.codex/skill-sources.json`.
- Updates mapped GitHub-backed skills.
- Refreshes installed Codex plugins.
- Backs up every skill before replacing it.
- Skips unknown, private, or local skills until you map or mark them.

## Repository Layout

```text
.
|-- README.md
`-- skill-sync/
    |-- SKILL.md
    |-- agents/
    |   `-- openai.yaml
    |-- references/
    |   `-- manifest.example.json
    `-- scripts/
        `-- update_codex_assets.py
```

The installable skill is the `skill-sync/` folder.

## Installation

Clone this repository, then copy the skill folder into your agent skill root.

### Codex

```bash
mkdir -p ~/.codex/skills
cp -R skill-sync ~/.codex/skills/
```

### Claude Code

```bash
mkdir -p ~/.claude/skills
cp -R skill-sync ~/.claude/skills/
```

### Cursor

```bash
mkdir -p ~/.cursor/skills
cp -R skill-sync ~/.cursor/skills/
```

For development, symlink instead of copying:

```bash
ln -s "$PWD/skill-sync" ~/.codex/skills/skill-sync
```

## Use It

In Codex, ask for one of these:

```text
/skill-sync check
/skill-sync update
/skill-sync run all
```

What happens:

1. It lists installed skills and plugins.
2. It groups them into Official, Non Official, and Not Mapped.
3. It asks whether to map missing GitHub repos or skip mapping for this run.
4. `check` stops at dry-run; `update` and `run all` ask for confirmation before applying.
5. After a successful update, it can help create a weekly automation.

Run the inventory directly:

```bash
python3 skill-sync/scripts/update_codex_assets.py --inventory --json
```

Dry-run update check:

```bash
python3 skill-sync/scripts/update_codex_assets.py --json
```

Apply updates:

```bash
python3 skill-sync/scripts/update_codex_assets.py \
  --apply \
  --json
```

Refresh Codex plugins only:

```bash
python3 skill-sync/scripts/update_codex_assets.py \
  --plugins-only \
  --apply \
  --json
```

Run the smoke test:

```bash
python3 skill-sync/scripts/update_codex_assets.py --self-test
```

## Source Manifest

Confirmed mappings are saved in `~/.codex/skill-sources.json` by default. You
can also pass another manifest with `--manifest`.

Only map repos you can confirm. If you cannot find the repo, leave it blank.
Mark a skill local only when the user says it is private or local-only.
When mapping public skills, search for the upstream public repo first. Do not
guess `catalystsystemslab/<skill>` or another user/org mirror unless the skill
itself names that repo or the user confirms it.
Choosing Map means public GitHub/web search is expected; the agent should only
ask again when network access is blocked or the match is uncertain.

Example manifest:

```json
{
  "skill_roots": [
    "~/.codex/skills",
    "~/.claude/skills"
  ],
  "skills": [
    {
      "name": "accessibility",
      "root": "~/.codex/skills",
      "url": "https://github.com/addyosmani/web-quality-skills",
      "branch": "main",
      "subpath": "skills/accessibility"
    },
    {
      "name": "my-private-skill",
      "root": "~/.codex/skills",
      "kind": "local"
    }
  ],
  "plugins": [
    {
      "id": "github",
      "marketplace": "openai-curated"
    }
  ]
}
```

See
[`skill-sync/references/manifest.example.json`](skill-sync/references/manifest.example.json)
for the full template.

## Safety Model

- Default mode is dry-run.
- `--apply` is required for filesystem or plugin changes.
- Every skill replacement gets a timestamped backup in
  `.skill-sync-backups/` under the skill root.
- Unknown skills are reported, not overwritten.
- Local skills marked with `"kind": "local"` are always skipped.
- The script replaces whole skill folders. Do not use it for skills with local
  edits you want merged.

## Codex Plugin Updates

When `--apply` is used and plugins are in scope, the script runs:

```bash
codex plugin marketplace upgrade --json
codex plugin list --json
codex plugin add <plugin>@<marketplace> --json
```

If `codex plugin list --json` is unavailable, it falls back to text parsing for
`plugin@marketplace` patterns.

Plugins are Codex-only. Claude Code and Cursor users can still use the skill
update features.

## Limitations

- GitHub and ordinary Git clone URLs are supported. Package registries are not.
- Local edits are not merged. The script backs up and replaces.
- Plugin updates require the Codex CLI.
- Source discovery is conservative. Copied monorepo folders usually need a
  manifest.

## License

MIT. See [LICENSE.md](LICENSE.md).

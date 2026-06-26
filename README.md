# Skill Sync

Keep your Codex skills updated safely.

## Start Here

Paste this into Codex:

```text
Install Skill Sync from https://github.com/catalystsystemslab/codex-skill-sync
Then run /skill-sync doctor
```

Nothing will be updated until you approve it.

## What Skill Sync Will Never Do

- It will not update unknown skills.
- It will not guess a GitHub repo.
- It will not replace private or local skills unless you explicitly map them.
- It will not apply changes during `check`.
- It will not update symlinked skill folders.
- It creates a backup before replacing a skill.

## What It Does

- Lists installed skills and plugins as Official, Community, or Needs Setup.
- Saves confirmed skill-to-GitHub mappings in `~/.codex/skill-sources.json`.
- Updates mapped GitHub-backed skills.
- Refreshes installed Codex plugins.
- Backs up every skill before replacing it.
- Skips unknown, private, or local skills until you map or mark them.

## The Three Status Groups

- Official: maintained by OpenAI or an official source.
- Community: has a confirmed public source, but is not official.
- Needs Setup: Skill Sync does not know where this came from, so it will not
  update it.

## Safe Update Flow

1. Check what is installed.
2. Map only confirmed public skills.
3. Preview updates.
4. Confirm before applying.
5. Restore from backup if needed.

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

## Use It

In Codex, ask for one of these:

```text
/skill-sync doctor
/skill-sync check
/skill-sync update
/skill-sync run all
```

What happens:

1. `doctor` checks whether your local setup is ready and makes no changes.
2. `check` lists installed skills and plugins.
3. It groups them into Official, Community, and Needs Setup.
4. It asks whether to map missing GitHub repos or skip mapping for this run.
5. `check` stops at dry-run; `update` and `run all` ask for confirmation before applying.
6. After a successful update, it can help create a weekly check automation.

## Advanced: Direct CLI Use

Run the inventory directly:

```bash
python3 skill-sync/scripts/update_codex_assets.py --inventory --json
```

Run read-only diagnostics:

```bash
python3 skill-sync/scripts/update_codex_assets.py --doctor
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

Outside Codex, skip plugin handling:

```bash
python3 skill-sync/scripts/update_codex_assets.py --inventory --no-plugins
python3 skill-sync/scripts/update_codex_assets.py --apply --no-plugins
```

## Source Manifest

Confirmed mappings are saved in `~/.codex/skill-sources.json` by default. You
can also pass another manifest with `--manifest`.

Manifest search order is:

1. `--manifest <path>`
2. `~/.codex/skill-sources.json`
3. `./skill-sources.json`
4. `./skills-sources.json`

Only map repos you can confirm. If you cannot find the repo, leave it blank.
Mark a skill local only when the user says it is private or local-only.
When mapping public skills, search for the upstream public repo first. Do not
guess `catalystsystemslab/<skill>` or another user/org mirror unless the skill
itself names that repo or the user confirms it.
Choosing Map means public GitHub/web search is expected; the agent should only
ask again when network access is blocked or the match is uncertain.

Skill authors can make copied installs self-discoverable by adding a source
line near the top of `SKILL.md`:

```text
Source: https://github.com/<owner>/<repo>/tree/<branch>/<skill-subpath>
```

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
- Apply refuses to replace a path outside configured skill roots.
- Apply refuses to replace symlinked skill installs. Update the symlink source
  repo directly.
- Unknown skills are reported, not overwritten.
- Local skills marked with `"kind": "local"` are always skipped.
- The script replaces whole skill folders. Do not use it for skills with local
  edits you want merged.

## Restore from Backup

If an update causes problems, ask Codex:

```text
/skill-sync help me restore my-skill from the latest backup
```

Skill Sync stores backups in:

```text
~/.codex/skills/.skill-sync-backups/
```

Advanced manual restore:

```bash
mv ~/.codex/skills/my-skill \
  ~/.codex/skills/my-skill.broken-$(date +%Y%m%d-%H%M%S)
cp -R ~/.codex/skills/.skill-sync-backups/<backup-folder> \
  ~/.codex/skills/my-skill
```

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

## Developer Notes

Repository layout:

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

For development, symlink instead of copying:

```bash
ln -s "$PWD/skill-sync" ~/.codex/skills/skill-sync
```

Symlink installs are for developers. Skill Sync will not auto-replace symlinked
skills; update the source repo directly.

## Limitations

- GitHub and ordinary Git clone URLs are supported. Package registries are not.
- Local edits are not merged. The script backs up and replaces.
- Plugin updates require the Codex CLI.
- Source discovery is conservative. Copied monorepo folders usually need a
  manifest.
- GitHub `/tree/<branch>/<subpath>` URLs are ambiguous when branch names contain
  `/`; use explicit `branch` and `subpath` manifest fields for those branches.

## License

MIT. See [LICENSE.md](LICENSE.md).

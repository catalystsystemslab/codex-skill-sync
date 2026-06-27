# Security Policy

Skill Sync updates local skill folders, so safety issues matter.

## Reporting a Security Issue

If you find a security-sensitive issue, please avoid posting exploit details publicly at first.

Preferred options:

1. Use GitHub private vulnerability reporting if it is enabled for this repository.
2. If private reporting is unavailable, open a minimal GitHub issue saying you have a security report, without including exploit details.

A maintainer will coordinate next steps.

## Security-Sensitive Areas

Please treat these areas carefully:

- Path validation
- Backup and replacement behavior
- Remote repository cloning
- Remote skill tree validation
- Symlink handling
- Manifest parsing
- Plugin update commands
- Any command that can modify files on disk

## Security Expectations

Skill Sync should not:

- Guess unknown repositories
- Auto-apply updates without clear user confirmation
- Replace local or private skills unless explicitly mapped
- Follow unsafe symlinks
- Install remote skill trees that escape their folder
- Replace paths outside configured skill roots
- Hide failed safety checks behind friendly-looking success messages

## Supported Versions

The current public beta is the only supported version.

Please use the latest release before reporting a security issue unless the issue is specifically about an older version.

#!/usr/bin/env python3
"""Update SKILL.md folders and Codex plugins.

The script is intentionally stdlib-only so any SKILL.md-capable agent can run it.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


IGNORE_DIRS = {
    ".git",
    ".backup",
    ".skill-sync-backups",
    "__pycache__",
}
IGNORE_FILES = {".DS_Store"}
GITHUB_URL = re.compile(r"https://github\.com/[^\s)>\"]+")
SOURCE_LINE = re.compile(
    r"^\s*(?:[-*]\s*)?(?:source|upstream|repo|repository|github)(?:[-_ ]?url)?\s*[:=-]",
    re.IGNORECASE,
)
PLACEHOLDER_NAMES = {
    "example",
    "my-app",
    "org",
    "owner",
    "repo",
    "repository",
    "user",
    "username",
    "your-org",
    "your-repo",
}
DEFAULT_MANIFESTS = (
    "~/.codex/skill-sources.json",
    "skill-sources.json",
    "skills-sources.json",
)
DEFAULT_SKILL_ROOTS = (
    "~/.codex/skills",
    "~/.agents/skills",
    "~/.claude/skills",
    "~/.cursor/skills",
)
OFFICIAL_GITHUB_OWNERS = {"openai"}
OFFICIAL_MARKETPLACE_PREFIXES = ("openai-",)
MAX_SKILL_FILES = 1000
MAX_SKILL_BYTES = 50 * 1024 * 1024


@dataclasses.dataclass
class SkillSource:
    name: str
    path: Path
    url: str = ""
    branch: str = ""
    subpath: str = ""
    kind: str = "remote"
    source: str = "manifest"


@dataclasses.dataclass
class ManifestResult:
    manifest: Dict[str, Any]
    path: str = ""
    error: str = ""
    present: bool = False


def expand_path(value: str) -> Path:
    return Path(os.path.expandvars(os.path.expanduser(value))).resolve()


def display_path(path: Path) -> str:
    try:
        return "~/" + path.relative_to(Path.home()).as_posix()
    except ValueError:
        return str(path)


def run(cmd: Sequence[str], cwd: Optional[Path] = None, timeout: int = 120) -> Tuple[int, str, str]:
    env = os.environ.copy()
    env.setdefault("GIT_TERMINAL_PROMPT", "0")
    env.setdefault("GIT_ASKPASS", "echo")
    try:
        proc = subprocess.run(
            list(cmd),
            cwd=str(cwd) if cwd else None,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        return 127, "", str(exc)
    except subprocess.TimeoutExpired as exc:
        return 124, (exc.stdout or "").strip(), (exc.stderr or f"timed out after {timeout}s").strip()
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def validate_manifest(manifest: Any) -> str:
    if not isinstance(manifest, dict):
        return "Manifest problem: the top level must be a JSON object."
    for key in ("skill_roots", "skills", "plugins"):
        if key in manifest and not isinstance(manifest[key], list):
            return f"Manifest problem: `{key}` must be a list."
    for index, root in enumerate(manifest.get("skill_roots", []), start=1):
        if not isinstance(root, str) or not root:
            return f"Manifest problem: skill_roots entry #{index} must be a non-empty string."
    for index, item in enumerate(manifest.get("skills", []), start=1):
        if not isinstance(item, dict):
            return f"Manifest problem: skill entry #{index} must be an object."
        path = item.get("path")
        root = item.get("root")
        name = item.get("name")
        if path is not None and not isinstance(path, str):
            return f"Manifest problem: skill entry #{index} has a non-string path."
        for field in ("url", "branch", "subpath", "kind"):
            if field in item and item[field] is not None and not isinstance(item[field], str):
                return f"Manifest problem: skill entry #{index} has a non-string `{field}`."
        if item.get("kind") not in (None, "remote", "local"):
            return f"Manifest problem: skill entry #{index} has unsupported kind `{item.get('kind')}`."
        if path:
            continue
        if not root or not name:
            return f"Manifest problem: skill entry #{index} needs either `path`, or both `root` and `name`."
        if not isinstance(root, str) or not isinstance(name, str):
            return f"Manifest problem: skill entry #{index} needs string values for `root` and `name`."
    plugin_fields = ("id", "plugin", "pluginId", "name", "marketplace", "marketplace_id", "marketplaceName")
    for index, item in enumerate(manifest.get("plugins", []), start=1):
        if isinstance(item, str):
            continue
        if not isinstance(item, dict):
            return f"Manifest problem: plugin entry #{index} must be a string or object."
        for field in plugin_fields:
            if field in item and item[field] is not None and not isinstance(item[field], str):
                return f"Manifest problem: plugin entry #{index} has a non-string `{field}`."
    return ""


def load_manifest(path: Optional[str]) -> ManifestResult:
    if not path:
        for candidate in DEFAULT_MANIFESTS:
            p = expand_path(candidate) if candidate.startswith("~") else Path(candidate)
            if p.exists():
                path = str(p)
                break
    if not path:
        return ManifestResult({})
    manifest_path = expand_path(path)
    if not manifest_path.exists():
        return ManifestResult(
            {},
            str(manifest_path),
            f"Manifest problem: {display_path(manifest_path)} does not exist.",
            True,
        )
    try:
        with open(manifest_path, "r", encoding="utf-8") as fh:
            manifest = json.load(fh)
    except json.JSONDecodeError as exc:
        return ManifestResult(
            {},
            str(manifest_path),
            f"Manifest problem: {display_path(manifest_path)} is not valid JSON at line {exc.lineno}.",
            True,
        )
    except OSError as exc:
        return ManifestResult(
            {},
            str(manifest_path),
            f"Manifest problem: could not read {display_path(manifest_path)}: {exc}.",
            True,
        )
    error = validate_manifest(manifest)
    if error:
        return ManifestResult({}, str(manifest_path), error, True)
    return ManifestResult(manifest, str(manifest_path), "", True)


def existing_unique_paths(paths: Iterable[Path]) -> List[Path]:
    seen: set[str] = set()
    out: List[Path] = []
    for path in paths:
        key = str(path)
        if key not in seen and path.is_dir():
            seen.add(key)
            out.append(path)
    return out


def default_roots(manifest: Dict[str, Any]) -> List[Path]:
    roots = [expand_path(p) for p in manifest.get("skill_roots", [])]
    roots.extend(expand_path(p) for p in DEFAULT_SKILL_ROOTS)
    return existing_unique_paths(roots)


def configured_roots(manifest: Dict[str, Any], extra_roots: Sequence[str] = ()) -> List[Path]:
    roots = [expand_path(p) for p in manifest.get("skill_roots", [])]
    roots.extend(expand_path(p) for p in DEFAULT_SKILL_ROOTS)
    roots.extend(expand_path(p) for p in extra_roots)
    seen: set[str] = set()
    out: List[Path] = []
    for root in roots:
        key = str(root)
        if key not in seen:
            seen.add(key)
            out.append(root)
    return out


def inspect_skill_roots(roots: Sequence[Path], extra_roots: Sequence[str] = ()) -> List[Dict[str, str]]:
    explicit = {str(expand_path(path)) for path in extra_roots}
    checks: List[Dict[str, str]] = []
    for root in roots:
        path = display_path(root)
        is_explicit = str(root) in explicit
        if not root.exists():
            checks.append(
                {
                    "path": path,
                    "status": "warn" if is_explicit else "missing",
                    "detail": "does not exist",
                }
            )
        elif not root.is_dir():
            checks.append({"path": path, "status": "failed", "detail": "not a directory"})
        elif not os.access(root, os.R_OK | os.X_OK):
            checks.append({"path": path, "status": "failed", "detail": "not readable"})
        elif not os.access(root, os.W_OK):
            checks.append({"path": path, "status": "warn", "detail": "not writable; apply may fail"})
        else:
            checks.append({"path": path, "status": "ok", "detail": "ready"})
    return checks


def codex_cli_available() -> bool:
    return shutil.which("codex") is not None


def check_status(checks: List[Dict[str, str]]) -> str:
    statuses = {check["status"] for check in checks}
    if "failed" in statuses:
        return "failed"
    if "warn" in statuses:
        return "warn"
    return "ok"


def doctor_report(manifest_arg: Optional[str], extra_roots: Sequence[str]) -> Dict[str, Any]:
    manifest_result = load_manifest(manifest_arg)
    roots = configured_roots(manifest_result.manifest, extra_roots)
    root_checks = inspect_skill_roots(roots, extra_roots)
    usable_roots = [root for root, check in zip(roots, root_checks) if check["status"] in {"ok", "warn"} and root.is_dir()]
    checks: List[Dict[str, str]] = []

    python_status = "ok" if sys.version_info >= (3, 9) else "failed"
    checks.append(
        {
            "name": "python_version",
            "status": python_status,
            "detail": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro} supported"
            if python_status == "ok"
            else f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}; Python 3.9+ is required",
        }
    )

    git_path = shutil.which("git")
    checks.append(
        {
            "name": "git",
            "status": "ok" if git_path else "failed",
            "detail": "found" if git_path else "not found; install Git before checking remote skills",
        }
    )

    failed_roots = [check for check in root_checks if check["status"] == "failed"]
    warned_roots = [check for check in root_checks if check["status"] == "warn"]
    if usable_roots:
        detail = ", ".join(display_path(root) for root in usable_roots[:3])
        if len(usable_roots) > 3:
            detail += f", and {len(usable_roots) - 3} more"
        status = "failed" if failed_roots else "warn" if warned_roots else "ok"
        if failed_roots:
            detail += "; " + "; ".join(f"{check['path']} is {check['detail']}" for check in failed_roots)
        elif warned_roots:
            detail += "; " + "; ".join(f"{check['path']} is {check['detail']}" for check in warned_roots)
        checks.append({"name": "skill_roots", "status": status, "detail": f"found {detail}"})
        checks.append(
            {
                "name": "installed_skills",
                "status": "ok",
                "detail": f"{len(all_skill_dirs(usable_roots))} skills found",
            }
        )
    else:
        status = "failed" if failed_roots else "warn"
        detail = "no skill roots found yet; install a skill before running updates"
        if failed_roots:
            detail = "; ".join(f"{check['path']} is {check['detail']}" for check in failed_roots)
        checks.append(
            {
                "name": "skill_roots",
                "status": status,
                "detail": detail,
            }
        )

    if manifest_result.error:
        checks.append({"name": "manifest", "status": "failed", "detail": manifest_result.error})
    elif manifest_result.present:
        checks.append(
            {
                "name": "manifest",
                "status": "ok",
                "detail": f"loaded from {display_path(Path(manifest_result.path))}",
            }
        )
    else:
        checks.append(
            {
                "name": "manifest",
                "status": "ok",
                "detail": "no manifest found; unknown skills will stay skipped",
            }
        )

    codex_found = codex_cli_available()
    checks.append(
        {
            "name": "codex_cli",
            "status": "ok" if codex_found else "warn",
            "detail": "found" if codex_found else "not found; plugin updates are unavailable",
        }
    )
    checks.append(
        {
            "name": "plugin_support",
            "status": "ok" if codex_found else "warn",
            "detail": "plugins available" if codex_found else "plugins unavailable; skill updates can still run",
        }
    )
    checks.append({"name": "changes", "status": "ok", "detail": "no changes were made"})
    return {"status": check_status(checks), "checks": checks}


def parse_github_url(url: str) -> Tuple[str, str, str]:
    tree = re.match(r"^(https://github\.com/[^/]+/[^/]+)/(?:tree|blob)/([^/]+)(?:/(.*))?$", url)
    if tree:
        repo, branch, subpath = tree.groups()
        subpath = subpath or ""
        if subpath.endswith("/SKILL.md"):
            subpath = subpath[: -len("/SKILL.md")]
        return repo, branch, subpath
    repo = re.match(r"^(https://github\.com/[^/]+/[^/]+?)(?:\.git)?/?$", url)
    if repo:
        return repo.group(1), "", ""
    return url, "", ""


def github_repo_name(url: str) -> str:
    match = re.match(r"^https://github\.com/[^/]+/([^/?#]+)", url)
    return match.group(1).removesuffix(".git") if match else ""


def github_owner(url: str) -> str:
    https = re.match(r"^https://github\.com/([^/]+)/", url)
    if https:
        return https.group(1).lower()
    ssh = re.match(r"^(?:git@|ssh://git@)github\.com[:/]([^/]+)/", url)
    return ssh.group(1).lower() if ssh else ""


def is_placeholder_github_url(url: str) -> bool:
    match = re.match(r"^https://github\.com/([^/]+)/([^/?#]+)", url)
    if not match:
        return False
    owner, repo = match.groups()
    return owner.lower() in PLACEHOLDER_NAMES or repo.lower().removesuffix(".git") in PLACEHOLDER_NAMES


def looks_like_skill_source_url(url: str, skill_name: str, line: str) -> bool:
    if is_placeholder_github_url(url):
        return False
    repo_url, _branch, subpath = parse_github_url(url)
    if not repo_url.startswith("https://github.com/"):
        return False
    if subpath:
        return SOURCE_LINE.search(line) is not None or Path(subpath).name == skill_name
    return SOURCE_LINE.search(line) is not None and github_repo_name(repo_url) == skill_name


def manifest_sources(manifest: Dict[str, Any]) -> List[SkillSource]:
    out: List[SkillSource] = []
    for item in manifest.get("skills", []):
        kind = item.get("kind", "remote")
        root = expand_path(item["root"]) if item.get("root") else None
        path = expand_path(item["path"]) if item.get("path") else root / item["name"]
        repo_url, branch_from_url, subpath_from_url = parse_github_url(item.get("url", ""))
        out.append(
            SkillSource(
                name=item.get("name") or path.name,
                path=path,
                url=repo_url,
                branch=item.get("branch") or branch_from_url,
                subpath=item.get("subpath", subpath_from_url),
                kind=kind,
                source="manifest",
            )
        )
    return out


def git_config(path: Path, key: str) -> str:
    code, out, _ = run(["git", "-C", str(path), "config", "--get", key])
    return out if code == 0 else ""


def git_branch(path: Path) -> str:
    code, out, _ = run(["git", "-C", str(path), "rev-parse", "--abbrev-ref", "HEAD"])
    if code == 0 and out and out != "HEAD":
        return out
    return ""


def discovered_git_sources(roots: Iterable[Path]) -> List[SkillSource]:
    out: List[SkillSource] = []
    for root in roots:
        if not root.is_dir():
            continue
        try:
            children = sorted(root.iterdir())
        except OSError:
            continue
        for child in children:
            if not child.is_dir():
                continue
            if not (child / "SKILL.md").exists() or not (child / ".git").exists():
                continue
            url = git_config(child, "remote.origin.url")
            if not url:
                continue
            out.append(
                SkillSource(
                    name=child.name,
                    path=child,
                    url=url,
                    branch=git_branch(child),
                    subpath="",
                    source=".git",
                )
            )
    return out


def discovered_skillmd_sources(roots: Iterable[Path]) -> List[SkillSource]:
    out: List[SkillSource] = []
    for root in roots:
        if not root.is_dir():
            continue
        try:
            children = sorted(root.iterdir())
        except OSError:
            continue
        for child in children:
            skill_md = child / "SKILL.md"
            if not child.is_dir() or not skill_md.exists() or (child / ".git").exists():
                continue
            found = False
            for line in skill_md.read_text(encoding="utf-8", errors="ignore").splitlines():
                for match in GITHUB_URL.findall(line):
                    url = match.rstrip(".,;:!?\"'")
                    if not looks_like_skill_source_url(url, child.name, line):
                        continue
                    repo_url, branch, subpath = parse_github_url(url)
                    out.append(
                        SkillSource(
                            name=child.name,
                            path=child,
                            url=repo_url,
                            branch=branch,
                            subpath=subpath,
                            source="SKILL.md",
                        )
                    )
                    found = True
                    break
                if found:
                    break
    return out


def all_skill_dirs(roots: Iterable[Path]) -> List[Path]:
    out: List[Path] = []
    for root in roots:
        if not root.is_dir():
            continue
        try:
            children = sorted(root.iterdir())
        except OSError:
            continue
        for child in children:
            if child.is_dir() and (child / "SKILL.md").exists():
                out.append(child)
    return out


def merge_sources(primary: List[SkillSource], secondary: List[SkillSource]) -> List[SkillSource]:
    merged: Dict[str, SkillSource] = {str(s.path): s for s in secondary}
    for item in primary:
        merged[str(item.path)] = item
    return list(merged.values())


def skill_sources(manifest: Dict[str, Any], roots: Iterable[Path]) -> List[SkillSource]:
    discovered = discovered_git_sources(roots) + discovered_skillmd_sources(roots)
    return merge_sources(manifest_sources(manifest), discovered)


def skill_inventory_group(source: SkillSource) -> str:
    if source.kind == "local" or not source.url or is_placeholder_github_url(source.url):
        return "unmapped"
    if github_owner(source.url) in OFFICIAL_GITHUB_OWNERS:
        return "official"
    return "non_official"


def skill_inventory(manifest: Dict[str, Any], roots: Iterable[Path]) -> List[Dict[str, Any]]:
    sources = skill_sources(manifest, roots)
    known_paths = {str(s.path) for s in sources}
    records: List[Dict[str, Any]] = []
    for source in sorted(sources, key=lambda s: str(s.path)):
        repo = "" if skill_inventory_group(source) == "unmapped" else source.url
        records.append(
            {
                "type": "skill",
                "name": source.name,
                "path": str(source.path),
                "group": skill_inventory_group(source),
                "repo": repo,
                "branch": source.branch,
                "subpath": source.subpath,
                "source": source.source,
            }
        )
    for path in all_skill_dirs(roots):
        if str(path) not in known_paths:
            records.append(
                {
                    "type": "skill",
                    "name": path.name,
                    "path": str(path),
                    "group": "unmapped",
                    "repo": "",
                    "source": "unknown",
                }
            )
    return records


def ignore_walk_dirs(names: List[str]) -> None:
    names[:] = [n for n in names if n not in IGNORE_DIRS]


def dir_digest(path: Path) -> str:
    h = hashlib.sha256()
    for root, dirs, files in os.walk(path):
        ignore_walk_dirs(dirs)
        root_path = Path(root)
        for name in sorted(files):
            if name in IGNORE_FILES:
                continue
            p = root_path / name
            rel = p.relative_to(path).as_posix()
            h.update(rel.encode("utf-8"))
            h.update(b"\0")
            if p.is_symlink():
                h.update(("link:" + os.readlink(p)).encode("utf-8"))
            else:
                with open(p, "rb") as fh:
                    for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                        h.update(chunk)
            h.update(b"\0")
    return h.hexdigest()


def safe_remote_subpath(repo_root: Path, subpath: str) -> Path:
    root = repo_root.resolve()
    if not subpath:
        return root
    raw = Path(subpath)
    if raw.is_absolute():
        raise RuntimeError(f"unsafe remote subpath is absolute: {subpath}")
    if any(part == ".." for part in raw.parts):
        raise RuntimeError(f"unsafe remote subpath escapes repo: {subpath}")
    resolved = (repo_root / raw).resolve()
    if not (resolved == root or resolved.is_relative_to(root)):
        raise RuntimeError(f"unsafe remote subpath escapes repo: {subpath}")
    return resolved


def validate_skill_tree(
    path: Path,
    max_files: int = MAX_SKILL_FILES,
    max_bytes: int = MAX_SKILL_BYTES,
) -> None:
    root = path.resolve()
    file_count = 0
    total_bytes = 0
    for current, dirs, files in os.walk(path):
        ignore_walk_dirs(dirs)
        current_path = Path(current)
        names = [(name, current_path / name) for name in list(dirs) + sorted(files) if name not in IGNORE_FILES]
        for name, item in names:
            rel = item.relative_to(path).as_posix()
            if item.is_symlink():
                target = os.readlink(item)
                if os.path.isabs(target):
                    raise RuntimeError(f"unsafe absolute symlink in remote skill: {rel} -> {target}")
                resolved_target = (item.parent / target).resolve()
                if not (resolved_target == root or resolved_target.is_relative_to(root)):
                    raise RuntimeError(f"unsafe symlink escapes remote skill: {rel} -> {target}")
                if not resolved_target.exists():
                    raise RuntimeError(f"broken symlink in remote skill: {rel} -> {target}")
            file_count += 1
            if file_count > max_files:
                raise RuntimeError(f"remote skill has too many files: {file_count} > {max_files}")
            if item.is_file() and not item.is_symlink():
                total_bytes += item.stat().st_size
                if total_bytes > max_bytes:
                    raise RuntimeError(f"remote skill is too large: {total_bytes} bytes > {max_bytes} bytes")


def clone_source(source: SkillSource, tmp: Path) -> Path:
    target = tmp / "repo"
    cmd = ["git", "clone", "--depth", "1"]
    if source.branch:
        cmd.extend(["--branch", source.branch])
    cmd.extend([source.url, str(target)])
    code, _, err = run(cmd, timeout=300)
    if code != 0:
        raise RuntimeError(err or "git clone failed")
    sub = safe_remote_subpath(target, source.subpath)
    if not sub.exists():
        raise RuntimeError("subpath not found: " + source.subpath)
    if not (sub / "SKILL.md").exists():
        raise RuntimeError("remote subpath has no SKILL.md")
    return sub


def copytree(src: Path, dst: Path) -> None:
    def ignore(_dir: str, names: List[str]) -> List[str]:
        return [n for n in names if n in IGNORE_DIRS or n in IGNORE_FILES]

    shutil.copytree(src, dst, symlinks=True, ignore=ignore)


def validate_local_skill_path(path: Path, roots: Sequence[Path]) -> None:
    if path.is_symlink():
        raise RuntimeError(
            "local skill is a symlink; refusing to replace. "
            "Update the source repo directly."
        )
    resolved = path.resolve()
    if resolved in {Path("/"), Path.home().resolve()}:
        raise RuntimeError(f"refusing to replace unsafe path: {resolved}")
    if not (resolved / "SKILL.md").exists():
        raise RuntimeError(f"local path has no SKILL.md: {resolved}")
    allowed = any(resolved == root.resolve() or resolved.is_relative_to(root.resolve()) for root in roots)
    if not allowed:
        raise RuntimeError(f"local path is outside configured skill roots: {resolved}")


def replace_skill(local: Path, remote: Path, roots: Sequence[Path]) -> Path:
    validate_local_skill_path(local, roots)
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    suffix = f"{timestamp}-{time.time_ns()}"
    backup_root = local.parent / ".skill-sync-backups"
    backup_root.mkdir(exist_ok=True)
    backup = backup_root / f"{local.name}-{suffix}"
    staging = local.parent / f".{local.name}.update-{os.getpid()}-{time.time_ns()}"
    old_path = local.parent / f".{local.name}.old-{os.getpid()}-{time.time_ns()}"
    try:
        copytree(remote, staging)
        shutil.copytree(local, backup, symlinks=True)
        os.replace(local, old_path)
        try:
            os.replace(staging, local)
        except Exception:
            if not local.exists() and old_path.exists():
                os.replace(old_path, local)
            raise
        if old_path.exists():
            shutil.rmtree(old_path)
    finally:
        if old_path.exists() and not local.exists():
            os.replace(old_path, local)
        if staging.exists():
            shutil.rmtree(staging)
    return backup


def check_skill(source: SkillSource, apply: bool, roots: Sequence[Path]) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "type": "skill",
        "name": source.name,
        "path": str(source.path),
        "source": source.source,
        "status": "unknown",
    }
    if source.kind == "local":
        result["status"] = "skipped"
        result["reason"] = "local"
        return result
    if not source.path.exists():
        result["status"] = "failed"
        result["error"] = "local path missing"
        return result
    if not (source.path / "SKILL.md").exists():
        result["status"] = "failed"
        result["error"] = "local path has no SKILL.md"
        return result
    if not source.url:
        result["status"] = "skipped"
        result["reason"] = "no remote url"
        return result
    if is_placeholder_github_url(source.url):
        result["status"] = "skipped"
        result["reason"] = "placeholder GitHub URL; add the real repo or mark local"
        return result
    if apply:
        try:
            validate_local_skill_path(source.path, roots)
        except RuntimeError as exc:
            result["status"] = "failed"
            result["error"] = str(exc)
            return result

    with tempfile.TemporaryDirectory(prefix="skill-update-") as td:
        try:
            remote = clone_source(source, Path(td))
            validate_skill_tree(remote)
            same = dir_digest(source.path) == dir_digest(remote)
            if same:
                result["status"] = "current"
            elif apply:
                backup = replace_skill(source.path, remote, roots)
                result["status"] = "updated"
                result["backup"] = str(backup)
            else:
                result["status"] = "update_available"
        except Exception as exc:  # noqa: BLE001 - report, do not hide update failures
            result["status"] = "failed"
            result["error"] = str(exc)
    return result


def parse_plugin_ref(value: str) -> Optional[Dict[str, str]]:
    match = re.search(r"([A-Za-z0-9_.-]+)@([A-Za-z0-9_.-]+)", value)
    if not match:
        return None
    return {"id": match.group(1), "marketplace": match.group(2)}


def plugins_from_json(value: Any) -> List[Dict[str, str]]:
    if isinstance(value, dict):
        for key in ("plugins", "installed", "items"):
            if key in value:
                return plugins_from_json(value[key])
        return []
    if not isinstance(value, list):
        return []
    out: List[Dict[str, str]] = []
    for item in value:
        if isinstance(item, str):
            parsed = parse_plugin_ref(item)
            if parsed:
                out.append(parsed)
        elif isinstance(item, dict):
            if item.get("installed") is False:
                continue
            plugin_id = item.get("id") or item.get("plugin") or item.get("pluginId") or item.get("name")
            marketplace = item.get("marketplace") or item.get("marketplace_id") or item.get("marketplaceName")
            parsed = parse_plugin_ref(str(plugin_id)) if plugin_id else None
            if parsed:
                out.append(parsed)
                continue
            if plugin_id and marketplace:
                out.append({"id": str(plugin_id), "marketplace": str(marketplace)})
    return out


def installed_plugins() -> Tuple[List[Dict[str, str]], str]:
    code, out, err = run(["codex", "plugin", "list", "--json"])
    if code == 0 and out:
        try:
            plugins = plugins_from_json(json.loads(out))
            if plugins:
                return plugins, ""
        except json.JSONDecodeError:
            pass
    code, out, err = run(["codex", "plugin", "list"])
    if code != 0:
        return [], err or "codex plugin list failed"
    plugins = []
    for line in out.splitlines():
        if "installed" not in line or "not installed" in line:
            continue
        for ref in sorted(set(re.findall(r"[A-Za-z0-9_.-]+@[A-Za-z0-9_.-]+", line))):
            parsed = parse_plugin_ref(ref)
            if parsed:
                plugins.append(parsed)
    return plugins, ""


def plugin_inventory_records(plugins: List[Dict[str, str]], source: str) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for plugin in plugins:
        ref = f"{plugin['id']}@{plugin['marketplace']}"
        if ref in seen:
            continue
        seen.add(ref)
        records.append(
            {
                "type": "plugin",
                "name": ref,
                "id": plugin["id"],
                "marketplace": plugin["marketplace"],
                "group": "official"
                if plugin["marketplace"].startswith(OFFICIAL_MARKETPLACE_PREFIXES)
                else "non_official",
                "repo": "",
                "source": source,
                "status": "installed",
            }
        )
    return records


def codex_missing_record(failed: bool) -> Dict[str, Any]:
    reason = (
        "Codex CLI not found; plugin updates require Codex."
        if failed
        else "Codex CLI not found; plugin updates skipped. Skill updates can still run."
    )
    return {
        "type": "plugin",
        "name": "Codex plugins",
        "group": "unmapped",
        "repo": "",
        "source": "codex",
        "status": "failed" if failed else "skipped",
        "reason": reason,
    }


def plugin_inventory(
    manifest: Dict[str, Any],
    require_codex: bool = False,
    codex_available: Optional[bool] = None,
) -> List[Dict[str, Any]]:
    if codex_available is None:
        codex_available = codex_cli_available()
    if not codex_available:
        return [codex_missing_record(require_codex)]
    plugins, err = installed_plugins()
    source = "codex"
    if err:
        plugins = plugins_from_json(manifest.get("plugins", []))
        source = "manifest"
        if not plugins:
            return [
                {
                    "type": "plugin",
                    "name": "codex plugins",
                    "group": "unmapped",
                    "repo": "",
                    "source": "codex",
                    "status": "failed",
                    "error": err,
                }
            ]
    return plugin_inventory_records(plugins, source)


def update_plugins(
    manifest: Dict[str, Any],
    apply: bool,
    require_codex: bool = False,
    codex_available: Optional[bool] = None,
) -> List[Dict[str, Any]]:
    if codex_available is None:
        codex_available = codex_cli_available()
    if not codex_available:
        return [codex_missing_record(require_codex)]
    if not apply:
        return [{"type": "plugin", "status": "skipped", "reason": "dry-run"}]

    results: List[Dict[str, Any]] = []
    code, out, err = run(["codex", "plugin", "marketplace", "upgrade", "--json"])
    results.append(
        {
            "type": "plugin_marketplace",
            "status": "updated" if code == 0 else "failed",
            "command": "codex plugin marketplace upgrade --json",
            "output": out,
            "error": err,
        }
    )
    if code != 0:
        if code != 127:
            results.append({"type": "plugin", "status": "skipped", "reason": "marketplace upgrade failed"})
        return results

    plugins = plugins_from_json(manifest.get("plugins", []))
    if not plugins:
        plugins, plugin_err = installed_plugins()
        if plugin_err:
            results.append({"type": "plugin", "status": "failed", "error": plugin_err})
            return results

    seen: set[str] = set()
    for plugin in plugins:
        ref = f"{plugin['id']}@{plugin['marketplace']}"
        if ref in seen:
            continue
        seen.add(ref)
        code, out, err = run(["codex", "plugin", "add", ref, "--json"])
        results.append(
            {
                "type": "plugin",
                "name": ref,
                "status": "updated" if code == 0 else "failed",
                "output": out,
                "error": err,
            }
        )
    return results


def summarize(results: List[Dict[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for item in results:
        status = item.get("status", "unknown")
        counts[status] = counts.get(status, 0) + 1
    return counts


def plural(count: int, singular: str, plural_value: Optional[str] = None) -> str:
    return singular if count == 1 else (plural_value or singular + "s")


def render_result_summary(results: List[Dict[str, Any]]) -> List[str]:
    changed = any(item.get("status") == "updated" for item in results)
    skill_current = sum(1 for item in results if item.get("type") == "skill" and item.get("status") == "current")
    skill_updates = sum(
        1 for item in results if item.get("type") == "skill" and item.get("status") == "update_available"
    )
    skill_updated = sum(1 for item in results if item.get("type") == "skill" and item.get("status") == "updated")
    skill_setup = sum(
        1
        for item in results
        if item.get("type") == "skill"
        and item.get("status") == "skipped"
        and any(text in item.get("reason", "") for text in ("unknown source", "no remote url", "placeholder"))
    )
    skill_skipped = sum(
        1
        for item in results
        if item.get("type") == "skill" and item.get("status") == "skipped"
    ) - skill_setup
    failed = sum(1 for item in results if item.get("status") == "failed")
    plugin_skipped = [item for item in results if item.get("type", "").startswith("plugin") and item.get("status") == "skipped"]

    lines = ["Changes were made." if changed else "No changes were made.", "Summary:"]
    if skill_current:
        lines.append(f"- {skill_current} {plural(skill_current, 'skill')} current")
    if skill_updates:
        lines.append(f"- {skill_updates} {plural(skill_updates, 'skill')} with updates available")
    if skill_updated:
        lines.append(f"- {skill_updated} {plural(skill_updated, 'skill')} updated")
    if skill_setup:
        lines.append(f"- {skill_setup} {plural(skill_setup, 'skill')} needs setup")
    if skill_skipped:
        lines.append(f"- {skill_skipped} {plural(skill_skipped, 'skill')} skipped")
    if plugin_skipped:
        reason = plugin_skipped[0].get("reason", "not requested")
        lines.append(f"- Codex plugins skipped: {reason}")
    if failed:
        lines.append(f"- {failed} {plural(failed, 'item')} failed")
    if len(lines) == 2:
        lines.append("- Nothing to report")

    lines.append("Recommended next step:")
    if failed:
        lines.append("Fix the failed items, then run /skill-sync check again.")
    elif skill_updates:
        lines.append("Run /skill-sync update if you want to apply the available skill updates.")
    elif skill_setup:
        lines.append("Map the Needs Setup skills, or leave them skipped.")
    elif changed:
        lines.append("Run /skill-sync check to verify everything is current.")
    else:
        lines.append("No action needed.")
    return lines


def render_text(results: List[Dict[str, Any]]) -> str:
    lines = []
    for item in results:
        label = item.get("name") or item.get("path") or item.get("type")
        detail = item.get("reason") or item.get("error") or item.get("backup") or ""
        suffix = f" - {detail}" if detail else ""
        lines.append(f"{item.get('status', 'unknown')}: {label}{suffix}")
    lines.append("")
    lines.extend(render_result_summary(results))
    return "\n".join(lines)


def inventory_summary(records: List[Dict[str, Any]]) -> Dict[str, int]:
    counts = {"official": 0, "non_official": 0, "unmapped": 0}
    for item in records:
        group = item.get("group", "unmapped")
        counts[group] = counts.get(group, 0) + 1
    return counts


def render_inventory_text(records: List[Dict[str, Any]]) -> str:
    labels = {
        "official": "Official",
        "non_official": "Community",
        "unmapped": "Needs Setup",
    }
    lines: List[str] = []
    skipped_plugins = [
        item for item in records if item.get("type", "").startswith("plugin") and item.get("status") == "skipped"
    ]
    grouped_records = [item for item in records if item not in skipped_plugins]
    for group in ("official", "non_official", "unmapped"):
        lines.append(labels[group] + ":")
        items = [item for item in grouped_records if item.get("group") == group]
        if not items:
            lines.append("- none")
            continue
        for item in items:
            repo = f" - {item['repo']}" if item.get("repo") else ""
            detail = item.get("reason") or item.get("error") or ""
            suffix = f" - {detail}" if detail else ""
            lines.append(f"- {item['type']}: {item['name']}{repo}{suffix}")
    if skipped_plugins:
        lines.append("Plugins:")
        for item in skipped_plugins:
            detail = item.get("reason") or item.get("error") or ""
            lines.append(f"- skipped: {detail}")
    counts = inventory_summary(grouped_records)
    lines.extend(
        [
            "",
            "No changes were made.",
            "Summary:",
            f"- {counts.get('official', 0)} official",
            f"- {counts.get('non_official', 0)} community",
            f"- {counts.get('unmapped', 0)} needs setup",
            "Recommended next step:",
            "Run /skill-sync check to preview updates.",
        ]
    )
    return "\n".join(lines)


def render_doctor_text(report: Dict[str, Any]) -> str:
    lines = ["Skill Sync Doctor"]
    labels = {"ok": "OK", "warn": "WARN", "failed": "FAILED"}
    names = {
        "python_version": "Python",
        "git": "Git",
        "skill_roots": "Skill roots",
        "installed_skills": "Installed skills",
        "manifest": "Manifest",
        "codex_cli": "Codex CLI",
        "plugin_support": "Plugin support",
        "changes": "Changes",
    }
    for check in report["checks"]:
        name = names.get(check["name"], check["name"])
        lines.append(f"{labels.get(check['status'], check['status'].upper())}: {name} - {check['detail']}")
    return "\n".join(lines)


def manifest_failure_record(manifest_result: ManifestResult) -> Dict[str, Any]:
    return {
        "type": "manifest",
        "name": display_path(Path(manifest_result.path)) if manifest_result.path else "manifest",
        "group": "unmapped",
        "repo": "",
        "source": "manifest",
        "status": "failed",
        "error": manifest_result.error + " No skills were updated.",
    }


def render_manifest_failure_text(record: Dict[str, Any]) -> str:
    return "\n".join(
        [
            f"failed: {record['name']} - {record['error']}",
            "",
            "No changes were made.",
            "Summary:",
            "- 1 item failed",
            "Recommended next step:",
            "Fix the manifest, then run /skill-sync doctor again.",
        ]
    )


def self_test() -> None:
    repo, branch, subpath = parse_github_url("https://github.com/a/b/tree/main/skills/x")
    assert repo == "https://github.com/a/b"
    assert branch == "main"
    assert subpath == "skills/x"
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        a = root / "a"
        b = root / "b"
        a.mkdir()
        b.mkdir()
        (a / "SKILL.md").write_text("one\n", encoding="utf-8")
        (b / "SKILL.md").write_text("one\n", encoding="utf-8")
        assert dir_digest(a) == dir_digest(b)
        (b / "SKILL.md").write_text("two\n", encoding="utf-8")
        assert dir_digest(a) != dir_digest(b)

        source_root = root / "skills"
        source_root.mkdir()
        for name, text in {
            "best-practices": "Use [DOMPurify](https://github.com/cure53/DOMPurify).\n",
            "core-web-vitals": "See https://github.com/GoogleChrome/web-vitals.\n",
            "netlify-deploy": "# Format: https://github.com/username/repo\n",
            "demo-skill": "Source: https://github.com/acme/agent-skills/tree/main/skills/demo-skill\n",
            "root-skill": "Repository: https://github.com/acme/root-skill\n",
        }.items():
            p = source_root / name
            p.mkdir()
            (p / "SKILL.md").write_text(text, encoding="utf-8")
        detected = {s.name: s for s in discovered_skillmd_sources([source_root])}
        assert set(detected) == {"demo-skill", "root-skill"}
        assert detected["demo-skill"].subpath == "skills/demo-skill"
        assert github_owner("git@github.com:openai/demo.git") == "openai"
        assert skill_inventory_group(
            SkillSource(name="official", path=source_root, url="https://github.com/openai/demo")
        ) == "official"
        records = {item["name"]: item for item in skill_inventory({}, [source_root])}
        assert records["demo-skill"]["group"] == "non_official"
        assert records["best-practices"]["group"] == "unmapped"
        plugins = plugin_inventory_records([{"id": "github", "marketplace": "openai-curated"}], "manifest")
        assert plugins[0]["group"] == "official"
        parsed_plugins = plugins_from_json(
            {"installed": [{"pluginId": "github@openai-curated", "marketplaceName": "openai-curated"}]}
        )
        assert parsed_plugins == [{"id": "github", "marketplace": "openai-curated"}]
        assert plugins_from_json(
            {"installed": [{"pluginId": "linear@openai-curated", "installed": False}]}
        ) == []
        assert existing_unique_paths([source_root, source_root]) == [source_root]
        assert validate_manifest({"skills": [{"name": "x"}]}).startswith("Manifest problem")
        assert validate_manifest({"skill_roots": "~/.codex/skills"}).startswith("Manifest problem")
        for field in ("url", "branch", "subpath", "kind"):
            assert f"`{field}`" in validate_manifest(
                {"skills": [{"name": "demo", "root": str(source_root), field: 123}]}
            )
        assert "unsupported kind" in validate_manifest(
            {"skills": [{"name": "demo", "root": str(source_root), "kind": "generated"}]}
        )
        assert "plugin entry #1" in validate_manifest({"plugins": [123]})
        assert "`id`" in validate_manifest({"plugins": [{"id": 123}]})
        missing_manifest = load_manifest(str(root / "missing.json"))
        assert missing_manifest.error.startswith("Manifest problem")
        bad_manifest = root / "bad.json"
        bad_manifest.write_text("{bad json", encoding="utf-8")
        assert "not valid JSON" in load_manifest(str(bad_manifest)).error
        good_manifest = root / "good.json"
        good_manifest.write_text(
            json.dumps({"skills": [{"name": "demo", "root": str(source_root), "kind": "local"}]}),
            encoding="utf-8",
        )
        assert load_manifest(str(good_manifest)).manifest["skills"][0]["name"] == "demo"
        doctor = doctor_report(str(good_manifest), [])
        assert doctor["status"] in {"ok", "warn"}
        assert {check["name"] for check in doctor["checks"]} >= {"python_version", "git", "manifest", "changes"}
        assert doctor_report(str(bad_manifest), [])["status"] == "failed"
        root_file = root / "not-a-root"
        root_file.write_text("file\n", encoding="utf-8")
        assert inspect_skill_roots([root_file])[0]["status"] == "failed"
        assert doctor_report(str(good_manifest), [str(root_file)])["status"] == "failed"
        assert plugin_inventory({}, require_codex=False, codex_available=False)[0]["status"] == "skipped"
        assert plugin_inventory({}, require_codex=True, codex_available=False)[0]["status"] == "failed"
        assert update_plugins({}, apply=True, require_codex=False, codex_available=False)[0]["status"] == "skipped"
        assert update_plugins({}, apply=True, require_codex=True, codex_available=False)[0]["status"] == "failed"
        bad_manifest_result = load_manifest(str(bad_manifest))
        failure_text = render_manifest_failure_text(manifest_failure_record(bad_manifest_result))
        assert "run /skill-sync doctor again" in failure_text
        assert "run /skill-sync check" not in failure_text
        plugin_text = render_inventory_text([codex_missing_record(False)])
        assert "Plugins:" in plugin_text
        assert "- 0 needs setup" in plugin_text
        assert "Codex plugins" not in plugin_text.split("Needs Setup:", 1)[1].split("Plugins:", 1)[0]

        repo_root = root / "repo-root"
        repo_root.mkdir()
        nested = repo_root / "skills" / "demo"
        nested.mkdir(parents=True)
        assert safe_remote_subpath(repo_root, "skills/demo") == nested.resolve()
        for bad_subpath in ("/tmp/demo", "../demo", "skills/../../demo"):
            try:
                safe_remote_subpath(repo_root, bad_subpath)
                raise AssertionError("unsafe subpath should fail")
            except RuntimeError as exc:
                assert "unsafe remote subpath" in str(exc)

        tree = root / "tree"
        tree.mkdir()
        (tree / "SKILL.md").write_text("safe\n", encoding="utf-8")
        (tree / "notes.md").write_text("safe\n", encoding="utf-8")
        validate_skill_tree(tree)
        validate_skill_tree(tree, max_files=10, max_bytes=100)
        try:
            validate_skill_tree(tree, max_files=1)
            raise AssertionError("file count limit should fail")
        except RuntimeError as exc:
            assert "too many files" in str(exc)
        try:
            validate_skill_tree(tree, max_bytes=1)
            raise AssertionError("byte limit should fail")
        except RuntimeError as exc:
            assert "too large" in str(exc)
        if hasattr(os, "symlink"):
            inside_target = tree / "target.md"
            inside_target.write_text("target\n", encoding="utf-8")
            (tree / "target-link.md").symlink_to("target.md")
            validate_skill_tree(tree)

            abs_tree = root / "abs-tree"
            abs_tree.mkdir()
            (abs_tree / "SKILL.md").write_text("safe\n", encoding="utf-8")
            (abs_tree / "abs-link").symlink_to("/tmp")
            try:
                validate_skill_tree(abs_tree)
                raise AssertionError("absolute symlink should fail")
            except RuntimeError as exc:
                assert "absolute symlink" in str(exc)

            outside = root / "outside.md"
            outside.write_text("outside\n", encoding="utf-8")
            escape_tree = root / "escape-tree"
            escape_tree.mkdir()
            (escape_tree / "SKILL.md").write_text("safe\n", encoding="utf-8")
            (escape_tree / "escape-link").symlink_to("../outside.md")
            try:
                validate_skill_tree(escape_tree)
                raise AssertionError("escaping symlink should fail")
            except RuntimeError as exc:
                assert "escapes remote skill" in str(exc)

            broken_tree = root / "broken-tree"
            broken_tree.mkdir()
            (broken_tree / "SKILL.md").write_text("safe\n", encoding="utf-8")
            (broken_tree / "broken-link").symlink_to("missing.md")
            try:
                validate_skill_tree(broken_tree)
                raise AssertionError("broken symlink should fail")
            except RuntimeError as exc:
                assert "broken symlink" in str(exc)

        if run(["git", "--version"])[0] == 0:
            remote = root / "remote-skill"
            remote.mkdir()
            (remote / "SKILL.md").write_text("---\nname: demo\n---\nnew\n", encoding="utf-8")
            assert run(["git", "init"], remote)[0] == 0
            assert run(["git", "config", "user.email", "test@example.com"], remote)[0] == 0
            assert run(["git", "config", "user.name", "Test"], remote)[0] == 0
            assert run(["git", "add", "SKILL.md"], remote)[0] == 0
            assert run(["git", "commit", "-m", "init"], remote)[0] == 0

            local = root / "local-skill"
            local.mkdir()
            (local / "SKILL.md").write_text("---\nname: demo\n---\nold\n", encoding="utf-8")
            validate_local_skill_path(local, [root])
            outside_root = root / "outside-root"
            outside_root.mkdir()
            outside = outside_root / "outside-skill"
            outside.mkdir()
            (outside / "SKILL.md").write_text("outside\n", encoding="utf-8")
            try:
                validate_local_skill_path(outside, [source_root])
                raise AssertionError("outside skill path should fail validation")
            except RuntimeError as exc:
                assert "outside configured skill roots" in str(exc)
            if hasattr(os, "symlink"):
                linked = root / "linked-skill"
                linked.symlink_to(local, target_is_directory=True)
                try:
                    validate_local_skill_path(linked, [root])
                    raise AssertionError("symlinked skill path should fail validation")
                except RuntimeError as exc:
                    assert "symlink" in str(exc)
            placeholder = SkillSource(name="x", path=local, url="https://github.com/username/repo")
            assert check_skill(placeholder, apply=False, roots=[root])["status"] == "skipped"
            source = SkillSource(name="local-skill", path=local, url=str(remote))
            assert check_skill(source, apply=False, roots=[root])["status"] == "update_available"
            applied = check_skill(source, apply=True, roots=[root])
            assert applied["status"] == "updated"
            assert Path(applied["backup"]).exists()
            assert "new" in (local / "SKILL.md").read_text(encoding="utf-8")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", help="Path to skill source manifest JSON")
    parser.add_argument("--skill-root", action="append", default=[], help="Extra skill root to scan")
    parser.add_argument("--apply", action="store_true", help="Apply updates. Default is dry-run.")
    parser.add_argument("--inventory", action="store_true", help="List skills/plugins by mapping group")
    parser.add_argument("--doctor", action="store_true", help="Run read-only beginner-safe diagnostics")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    plugin_scope = parser.add_mutually_exclusive_group()
    plugin_scope.add_argument("--no-plugins", action="store_true", help="Do not refresh Codex plugins")
    plugin_scope.add_argument("--plugins-only", action="store_true", help="Only refresh Codex plugins")
    parser.add_argument("--report", help="Write JSON report to this path")
    parser.add_argument("--self-test", action="store_true", help="Run built-in smoke test")
    args = parser.parse_args(argv)

    if args.self_test:
        self_test()
        print("self-test ok")
        return 0

    if args.doctor:
        report = doctor_report(args.manifest, args.skill_root)
        if args.report:
            report_path = expand_path(args.report)
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        if args.json:
            print(json.dumps(report, indent=2, sort_keys=True))
        else:
            print(render_doctor_text(report))
        return 1 if report["status"] == "failed" else 0

    manifest_result = load_manifest(args.manifest)
    if manifest_result.error:
        record = manifest_failure_record(manifest_result)
        if args.inventory:
            report = {"summary": {"failed": 1}, "inventory": [record]}
            if args.report:
                report_path = expand_path(args.report)
                report_path.parent.mkdir(parents=True, exist_ok=True)
                report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            if args.json:
                print(json.dumps(report, indent=2, sort_keys=True))
            else:
                print(render_manifest_failure_text(record))
            return 1
        report = {"summary": {"failed": 1}, "results": [record]}
        if args.report:
            report_path = expand_path(args.report)
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        if args.json:
            print(json.dumps(report, indent=2, sort_keys=True))
        else:
            print(render_manifest_failure_text(record))
        return 1

    manifest = manifest_result.manifest
    roots = default_roots(manifest)
    roots.extend(expand_path(p) for p in args.skill_root)
    roots = existing_unique_paths(roots)

    if args.inventory:
        records: List[Dict[str, Any]] = []
        if not args.plugins_only:
            records.extend(skill_inventory(manifest, roots))
        if not args.no_plugins:
            records.extend(plugin_inventory(manifest, require_codex=args.plugins_only))
        report = {"summary": inventory_summary(records), "inventory": records}
        if args.report:
            report_path = expand_path(args.report)
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        if args.json:
            print(json.dumps(report, indent=2, sort_keys=True))
        else:
            print(render_inventory_text(records))
        return 1 if any(item.get("status") == "failed" for item in records) else 0

    results: List[Dict[str, Any]] = []
    if not args.plugins_only:
        sources = skill_sources(manifest, roots)
        known_paths = {str(s.path) for s in sources}
        for source in sorted(sources, key=lambda s: str(s.path)):
            results.append(check_skill(source, args.apply, roots))
        for path in all_skill_dirs(roots):
            if str(path) not in known_paths:
                results.append(
                    {
                        "type": "skill",
                        "name": path.name,
                        "path": str(path),
                        "status": "skipped",
                        "reason": "unknown source; add to skill-sources.json or mark local",
                    }
                )

    if not args.no_plugins:
        results.extend(update_plugins(manifest, args.apply, require_codex=args.plugins_only))

    report = {"summary": summarize(results), "results": results}
    if args.report:
        report_path = expand_path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(render_text(results))
    return 1 if any(item.get("status") == "failed" for item in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())

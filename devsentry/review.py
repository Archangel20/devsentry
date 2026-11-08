"""Read tracked Git diffs without staging, committing, or editing the worktree.

Git is invoked with an argument list. Repository aliases, external diff
drivers, textconv filters, hooks, and fsmonitor are overridden for this
process so a repository cannot turn the invocation into a shell command.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import tempfile
from pathlib import Path

from .safety import is_sensitive_name

_GIT_TIMEOUT_SECONDS = 20
_MAX_FILES = 40
_hooks_dir: str | None = None


def _empty_hooks_dir() -> str:
    global _hooks_dir
    if _hooks_dir is None:
        _hooks_dir = tempfile.mkdtemp(prefix="devsentry-hooks-")
    return _hooks_dir


def _git_env() -> dict[str, str]:
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_OPTIONAL_LOCKS"] = "0"
    env["GIT_PAGER"] = "cat"
    env["GIT_CONFIG_GLOBAL"] = os.devnull
    env["GIT_CONFIG_SYSTEM"] = os.devnull
    env.pop("GIT_EXTERNAL_DIFF", None)
    return env


def run_git(repo: Path, args: list[str]) -> subprocess.CompletedProcess[bytes]:
    """Run one read-only git command in ``repo``."""
    if not args or not args[0].replace("-", "").isalnum():
        raise ValueError("refusing to build a git command")
    argv = [
        "git",
        "--no-optional-locks",
        "-c", "core.fsmonitor=",
        "-c", "core.untrackedCache=false",
        "-c", "diff.external=",
        "-c", f"core.hooksPath={_empty_hooks_dir()}",
        "-c", f"alias.{args[0]}=",
        "-C", str(repo),
        *args,
    ]
    return subprocess.run(
        argv,
        check=False,
        capture_output=True,
        timeout=_GIT_TIMEOUT_SECONDS,
        env=_git_env(),
        stdin=subprocess.DEVNULL,
        shell=False,
    )


def _decode(data: bytes) -> str:
    return data.decode("utf-8", errors="replace").strip()


def _index_sha256(repo: Path) -> str | None:
    proc = run_git(repo, ["rev-parse", "--absolute-git-dir"])
    if proc.returncode != 0:
        return None
    git_dir = Path(_decode(proc.stdout))
    index = git_dir / "index"
    try:
        data = index.read_bytes()
    except OSError:
        return None
    return hashlib.sha256(data).hexdigest()


def _parse_name_status(blob: bytes) -> list[dict]:
    parts = blob.split(b"\0")
    if parts and parts[-1] == b"":
        parts.pop()
    entries: list[dict] = []
    index = 0
    while index < len(parts):
        status = parts[index].decode("utf-8", errors="replace")
        index += 1
        if not status:
            continue
        code = status[:1]
        if code in {"R", "C"}:
            if index + 1 >= len(parts):
                break
            old = parts[index].decode("utf-8", errors="replace")
            new = parts[index + 1].decode("utf-8", errors="replace")
            index += 2
            entries.append({"status": status, "path": new, "old_path": old})
            continue
        if index >= len(parts):
            break
        path = parts[index].decode("utf-8", errors="replace")
        index += 1
        entries.append({"status": status, "path": path})
    return entries


def _clip(text: str, limit: int) -> tuple[str, bool]:
    if len(text.encode("utf-8")) <= limit:
        return text, False
    clipped = text.encode("utf-8")[:limit].decode("utf-8", errors="ignore")
    return clipped, True


def _patch_for(repo: Path, cached: bool, path: str, context_lines: int, max_patch_bytes: int) -> dict:
    if is_sensitive_name(Path(path).name) or (path and is_sensitive_name(Path(path).name)):
        return {"patch_omitted": True, "reason": "sensitive_path"}
    # A rename's old path can be the sensitive one. Callers pass both.
    args = [
        "diff",
        "--no-ext-diff",
        "--no-textconv",
        "--no-color",
        f"--unified={context_lines}",
    ]
    if cached:
        args.append("--cached")
    args.extend(["--", path])
    proc = run_git(repo, args)
    if proc.returncode != 0:
        message = _decode(proc.stderr) or _decode(proc.stdout) or "git diff failed"
        return {"patch_omitted": True, "reason": "git_error", "message": message[:300]}
    text = proc.stdout.decode("utf-8", errors="replace")
    if "GIT binary patch" in text or text.startswith("Binary files ") or "\nBinary files " in text:
        return {"patch_omitted": True, "reason": "binary"}
    clipped, truncated = _clip(text, max_patch_bytes)
    result = {"patch": clipped}
    if truncated:
        result["patch_truncated"] = True
    return result


def _scope(
    repo: Path,
    *,
    cached: bool,
    pathspec: str | None,
    context_lines: int,
    max_patch_bytes: int,
) -> dict:
    args = ["diff", "--name-status", "--no-ext-diff", "--no-textconv", "--no-color", "-z"]
    if cached:
        args.insert(1, "--cached")
    if pathspec:
        args.extend(["--", pathspec])
    proc = run_git(repo, args)
    if proc.returncode != 0:
        message = _decode(proc.stderr) or "git diff --name-status failed"
        return {"ok": False, "files": [], "error": message[:500]}
    parsed = _parse_name_status(proc.stdout)
    files = []
    hidden = 0
    for item in parsed:
        if len(files) >= _MAX_FILES:
            hidden += 1
            continue
        record = {"path": item["path"], "status": item["status"]}
        if "old_path" in item:
            record["old_path"] = item["old_path"]
        sensitive = is_sensitive_name(Path(item["path"]).name) or (
            "old_path" in item and is_sensitive_name(Path(item["old_path"]).name)
        )
        if sensitive:
            record["patch_omitted"] = True
            record["reason"] = "sensitive_path"
        else:
            record.update(
                _patch_for(repo, cached, item["path"], context_lines, max_patch_bytes)
            )
        files.append(record)
    result = {"ok": True, "files": files, "file_count": len(parsed)}
    if hidden:
        result["files_omitted_for_bound"] = hidden
    return result


def _untracked_count(repo: Path, pathspec: str | None) -> int | None:
    args = ["ls-files", "--others", "--exclude-standard", "-z"]
    if pathspec:
        args.extend(["--", pathspec])
    proc = run_git(repo, args)
    if proc.returncode != 0:
        return None
    parts = [part for part in proc.stdout.split(b"\0") if part]
    return len(parts)


def review_repository(
    root: Path,
    *,
    context_lines: int,
    max_patch_bytes: int,
) -> dict:
    """Review staged and unstaged tracked changes under ``root``."""
    inside = run_git(root, ["rev-parse", "--is-inside-work-tree"])
    if inside.returncode != 0 or _decode(inside.stdout) != "true":
        message = _decode(inside.stderr) or "the directory is not inside a Git work tree"
        return {
            "ok": False,
            "error": {"code": "not_a_git_repository", "message": message[:500]},
        }

    top = run_git(root, ["rev-parse", "--show-toplevel"])
    if top.returncode != 0:
        return {
            "ok": False,
            "error": {"code": "not_a_git_repository", "message": _decode(top.stderr)[:500] or "missing work tree"},
        }
    toplevel = Path(_decode(top.stdout)).resolve()
    try:
        relative = root.resolve().relative_to(toplevel)
    except ValueError:
        return {
            "ok": False,
            "error": {"code": "outside_work_tree", "message": "the directory is outside the Git work tree"},
        }
    pathspec = None if str(relative) == "." else relative.as_posix()

    before = _index_sha256(toplevel)
    head = run_git(toplevel, ["rev-parse", "HEAD"])
    head_sha = _decode(head.stdout) if head.returncode == 0 else None

    staged = _scope(
        toplevel,
        cached=True,
        pathspec=pathspec,
        context_lines=context_lines,
        max_patch_bytes=max_patch_bytes,
    )
    unstaged = _scope(
        toplevel,
        cached=False,
        pathspec=pathspec,
        context_lines=context_lines,
        max_patch_bytes=max_patch_bytes,
    )
    untracked = _untracked_count(toplevel, pathspec)
    after = _index_sha256(toplevel)

    return {
        "ok": bool(staged.get("ok") and unstaged.get("ok")),
        "repository": {
            "resolved": str(root.resolve()),
            "toplevel": str(toplevel),
            "head": head_sha,
            "scope_path": pathspec or ".",
        },
        "scope": {
            "staged": "Tracked changes in the index compared with HEAD. Nothing was staged by this tool.",
            "unstaged": "Tracked working-tree changes compared with the index.",
            "untracked": "Excluded. Untracked names and contents are not part of this review.",
        },
        "staged": staged,
        "unstaged": unstaged,
        "untracked_count": untracked,
        "mutation": {
            "staging": "not performed",
            "worktree_writes": "not performed",
            "index_sha256_unchanged": before == after,
        },
        "notes": [
            "External diff drivers and textconv filters were disabled for these commands.",
            "Git aliases, hooks, and fsmonitor from the repository were overridden for this process.",
            "Patch text for paths that look like secrets was omitted.",
            "Untracked files were counted and were not read.",
        ],
    }

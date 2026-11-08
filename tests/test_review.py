"""Git review tests. Git runs for real; Hermes is not involved."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from devsentry.tools import loads, review_changes


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "-c",
            "user.email=devsentry-test@example.com",
            "-c",
            "user.name=DevSentry Test",
            *args,
        ],
        check=True,
        capture_output=True,
    )


def _init(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init", "-q")
    _git(repo, "add", "--", ".")
    _git(repo, "commit", "-q", "-m", "initial")


def _snapshot(repo: Path) -> dict[str, bytes]:
    files = {}
    for path in repo.rglob("*"):
        if ".git" in path.parts or not path.is_file() or path.is_symlink():
            continue
        files[str(path.relative_to(repo))] = path.read_bytes()
    return files


def _cached_names(repo: Path) -> bytes:
    return subprocess.run(
        ["git", "-C", str(repo), "diff", "--cached", "--name-status", "-z"],
        check=True,
        capture_output=True,
    ).stdout


def test_staged_and_unstaged_are_separate_and_untracked_is_excluded(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "tracked.txt").write_text("base\n", encoding="utf-8")
    (repo / "staged.txt").write_text("base staged\n", encoding="utf-8")
    _init(repo)
    (repo / "tracked.txt").write_text("base\nUNSTAGED_MARKER\n", encoding="utf-8")
    (repo / "staged.txt").write_text("STAGED_MARKER\n", encoding="utf-8")
    _git(repo, "add", "--", "staged.txt")
    (repo / "notes.txt").write_text("UNTRACKED_MARKER\n", encoding="utf-8")

    before_files = _snapshot(repo)
    before_cached = _cached_names(repo)
    result = loads(review_changes({"path": str(repo)}))
    assert _snapshot(repo) == before_files
    assert _cached_names(repo) == before_cached

    assert result["ok"] is True
    assert result["mutation"]["staging"] == "not performed"
    assert result["mutation"]["worktree_writes"] == "not performed"
    assert result["mutation"]["index_sha256_unchanged"] is True
    assert result["untracked_count"] == 1
    assert "Untracked" in result["scope"]["untracked"] or "untracked" in result["scope"]["untracked"].lower()

    unstaged_paths = [item["path"] for item in result["unstaged"]["files"]]
    staged_paths = [item["path"] for item in result["staged"]["files"]]
    assert unstaged_paths == ["tracked.txt"]
    assert staged_paths == ["staged.txt"]
    blob = json.dumps(result)
    assert "UNSTAGED_MARKER" in blob
    assert "STAGED_MARKER" in blob
    assert "UNTRACKED_MARKER" not in blob
    assert "notes.txt" not in blob


def test_sensitive_patch_is_omitted(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.py").write_text("print('ok')\n", encoding="utf-8")
    (repo / ".env").write_text("TOKEN=one\n", encoding="utf-8")
    _init(repo)
    (repo / ".env").write_text("TOKEN=SUPER_SECRET_TOKEN\n", encoding="utf-8")
    result = loads(review_changes({"path": str(repo)}))
    env = next(item for item in result["unstaged"]["files"] if item["path"] == ".env")
    assert env["patch_omitted"] is True
    assert env["reason"] == "sensitive_path"
    assert "patch" not in env
    assert "SUPER_SECRET_TOKEN" not in json.dumps(result)


def test_subdirectory_scope_and_non_repository(tmp_path: Path):
    repo = tmp_path / "repo"
    keep = repo / "keep"
    keep.mkdir(parents=True)
    (keep / "inside.txt").write_text("inside\n", encoding="utf-8")
    (repo / "outside.txt").write_text("outside\n", encoding="utf-8")
    _init(repo)
    (keep / "inside.txt").write_text("inside\nINSIDE_CHANGE\n", encoding="utf-8")
    (repo / "outside.txt").write_text("outside\nOUTSIDE_CHANGE\n", encoding="utf-8")
    result = loads(review_changes({"path": str(keep)}))
    assert result["repository"]["scope_path"] == "keep"
    blob = json.dumps(result)
    assert "INSIDE_CHANGE" in blob
    assert "OUTSIDE_CHANGE" not in blob

    plain = tmp_path / "plain"
    plain.mkdir()
    missing = loads(review_changes({"path": str(plain)}))
    assert missing["ok"] is False
    assert missing["error"]["code"] == "not_a_git_repository"


def test_repository_cannot_run_alias_textconv_or_external_diff(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.py").write_text("print('one')\n", encoding="utf-8")
    _init(repo)
    alias_marker = tmp_path / "alias-ran"
    textconv_marker = tmp_path / "textconv-ran"
    external_marker = tmp_path / "external-ran"
    _git(repo, "config", "alias.diff", f"!touch {alias_marker}")
    _git(repo, "config", "alias.rev-parse", f"!touch {alias_marker}")
    _git(repo, "config", "alias.ls-files", f"!touch {alias_marker}")
    _git(repo, "config", "diff.evil.textconv", f"touch {textconv_marker}")
    _git(repo, "config", "diff.external", f"touch {external_marker}")
    (repo / ".gitattributes").write_text("*.py diff=evil\n", encoding="utf-8")
    (repo / "app.py").write_text("print('two')\n", encoding="utf-8")

    result = loads(review_changes({"path": str(repo)}))
    assert result["ok"] is True
    assert "print('two')" in json.dumps(result)
    assert not alias_marker.exists()
    assert not textconv_marker.exists()
    assert not external_marker.exists()
    assert result["mutation"]["index_sha256_unchanged"] is True


def test_path_metacharacters_do_not_reach_a_shell(tmp_path: Path):
    repo = tmp_path / "odd; touch injected.txt"
    repo.mkdir()
    (repo / "app.py").write_text("print('safe')\n", encoding="utf-8")
    _init(repo)
    (repo / "app.py").write_text("print('changed')\n", encoding="utf-8")
    result = loads(review_changes({"path": str(repo)}))
    assert result["ok"] is True
    assert "changed" in json.dumps(result)
    assert not (tmp_path / "injected.txt").exists()

"""Inventory tests. These call the tool functions directly, without Hermes."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from devsentry.tools import inspect_project, loads

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "sample-project"


def test_sample_project_counts_and_skips():
    result = loads(inspect_project({"path": str(FIXTURE)}))
    assert result["ok"] is True
    assert result["summary"]["approximate"] is True
    languages = {row["language"]: row["files"] for row in result["languages"]}
    assert languages["Python"] == 1
    assert languages["JavaScript"] == 1
    assert languages["Go"] == 2  # main.go and go.mod
    assert languages["Dockerfile"] == 1
    paths = {entry["path"] for entry in result["entries"]}
    assert "src/app.py" in paths
    assert "node_modules/left-pad/index.js" not in paths
    assert "build/artifact.txt" not in paths
    assert "__pycache__/app.cpython-312.pyc" not in paths
    reasons = {item["path"]: item["reason"] for item in result["skipped"]}
    assert reasons["node_modules"] == "dependency"
    assert reasons["build"] == "build"
    assert reasons["__pycache__"] == "cache"
    blob = json.dumps(result)
    assert "generated build output" not in blob
    assert "not-really-bytecode" not in blob


def test_does_not_execute_project_code(tmp_path: Path):
    project = tmp_path / "proj"
    project.mkdir()
    (project / "boom.py").write_text("open('ran.txt', 'w').write('executed')\n", encoding="utf-8")
    result = loads(inspect_project({"path": str(project)}))
    assert result["ok"] is True
    assert not (project / "ran.txt").exists()
    assert "executed" not in json.dumps(result)


def test_sensitive_files_are_named_and_not_read(tmp_path: Path):
    project = tmp_path / "proj"
    project.mkdir()
    (project / ".env").write_text("SUPER_SECRET_TOKEN=abc\n", encoding="utf-8")
    (project / "id_rsa").write_text("PRIVATE_KEY_MATERIAL\n", encoding="utf-8")
    (project / "app.py").write_text("print('hello')\n", encoding="utf-8")
    result = loads(inspect_project({"path": str(project)}))
    blob = json.dumps(result)
    assert "SUPER_SECRET_TOKEN" not in blob
    assert "PRIVATE_KEY_MATERIAL" not in blob
    flagged = {entry["path"]: entry for entry in result["entries"] if entry.get("sensitive")}
    assert flagged[".env"]["content"] == "not_read"
    assert flagged["id_rsa"]["content"] == "not_read"
    assert result["summary"]["sensitive_files"] == 2


def test_symlink_is_not_followed(tmp_path: Path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.py").write_text("SECRET_VIA_LINK = True\n", encoding="utf-8")
    project = tmp_path / "proj"
    project.mkdir()
    (project / "readme.txt").write_text("local\n", encoding="utf-8")
    (project / "escape").symlink_to(outside, target_is_directory=True)
    (project / "file-link.py").symlink_to(outside / "secret.py")
    result = loads(inspect_project({"path": str(project)}))
    blob = json.dumps(result)
    assert "SECRET_VIA_LINK" not in blob
    kinds = {entry["path"]: entry["type"] for entry in result["entries"]}
    assert kinds["escape"] == "symlink"
    assert kinds["file-link.py"] == "symlink"
    assert result["summary"]["symlinks"] == 2
    assert all(entry.get("followed") is False for entry in result["entries"] if entry["type"] == "symlink")


def test_selected_symlink_directory_is_resolved_and_disclosed(tmp_path: Path):
    real = tmp_path / "real"
    real.mkdir()
    (real / "app.py").write_text("x = 1\n", encoding="utf-8")
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    result = loads(inspect_project({"path": str(link)}))
    assert result["ok"] is True
    assert result["path"]["symlink_resolved"] is True
    assert result["path"]["resolved"] == str(real.resolve())
    assert any(entry["path"] == "app.py" for entry in result["entries"])


def test_venv_env_directory_is_skipped_only_with_marker(tmp_path: Path):
    project = tmp_path / "proj"
    source = project / "env"
    source.mkdir(parents=True)
    (source / "keep.py").write_text("value = 1\n", encoding="utf-8")
    kept = loads(inspect_project({"path": str(project)}))
    assert any(entry["path"] == "env/keep.py" for entry in kept["entries"])

    venv = project / "venv"
    venv.mkdir()
    (venv / "pyvenv.cfg").write_text("home = /usr/bin\n", encoding="utf-8")
    (venv / "hidden.py").write_text("hidden = True\n", encoding="utf-8")
    env_venv = project / "env"
    (env_venv / "pyvenv.cfg").write_text("home = /usr/bin\n", encoding="utf-8")
    skipped = loads(inspect_project({"path": str(project)}))
    reasons = {item["path"]: item["reason"] for item in skipped["skipped"]}
    assert reasons["venv"] == "dependency"
    assert reasons["env"] == "dependency"
    assert not any(entry["path"].startswith("venv/") for entry in skipped["entries"])
    assert "hidden = True" not in json.dumps(skipped)


def test_depth_and_entry_bounds(tmp_path: Path):
    project = tmp_path / "proj"
    nested = project / "a" / "b"
    nested.mkdir(parents=True)
    (project / "top.py").write_text("top = 1\n", encoding="utf-8")
    (nested / "deep.py").write_text("deep = 1\n", encoding="utf-8")
    shallow = loads(inspect_project({"path": str(project), "max_depth": 1}))
    paths = {entry["path"] for entry in shallow["entries"]}
    assert "top.py" in paths
    assert "a" in paths
    assert "a/b/deep.py" not in paths
    assert shallow["summary"]["depth_limited"] is True

    limited = loads(inspect_project({"path": str(project), "max_entries": 1}))
    assert limited["summary"]["truncated"] is True
    assert len(limited["entries"]) == 1

    clamped = loads(inspect_project({"path": str(project), "max_entries": 9_999_999}))
    assert clamped["limits"]["max_entries"] == 2000
    assert clamped["limits"]["clamped"] is True


def test_rejects_unsafe_paths(tmp_path: Path):
    missing = loads(inspect_project({"path": str(tmp_path / "nope")}))
    assert missing["ok"] is False
    assert missing["error"]["code"] == "not_found"
    file_path = tmp_path / "file.txt"
    file_path.write_text("x", encoding="utf-8")
    not_dir = loads(inspect_project({"path": str(file_path)}))
    assert not_dir["error"]["code"] == "not_a_directory"
    control = loads(inspect_project({"path": "bad\x00path"}))
    assert control["error"]["code"] == "invalid_path"
    assert loads(inspect_project({"path": ""}))["error"]["code"] == "invalid_path"


def test_shell_metacharacters_in_the_path_are_not_executed(tmp_path: Path):
    weird = tmp_path / "odd; touch injected.txt"
    weird.mkdir()
    (weird / "app.py").write_text("x = 1\n", encoding="utf-8")
    result = loads(inspect_project({"path": str(weird)}))
    assert result["ok"] is True
    assert not (tmp_path / "injected.txt").exists()
    assert any(entry["path"] == "app.py" for entry in result["entries"])


def test_copy_of_fixture_matches_direct_inventory(tmp_path: Path):
    copied = tmp_path / "copy"
    shutil.copytree(FIXTURE, copied, symlinks=True)
    direct = loads(inspect_project({"path": str(FIXTURE)}))
    clone = loads(inspect_project({"path": str(copied)}))
    assert clone["summary"]["files"] == direct["summary"]["files"]
    assert os.path.isdir(copied)

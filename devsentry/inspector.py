"""Read-only directory inventory and approximate language counts."""

from __future__ import annotations

import os
from pathlib import Path

from .safety import exclusion_reason, is_sensitive_name

# Programming and markup languages counted from the file extension.
# Counts are approximate: the file is not opened and the contents are not parsed.
_CODE_EXTENSIONS = {
    ".py": "Python",
    ".pyi": "Python",
    ".js": "JavaScript",
    ".mjs": "JavaScript",
    ".cjs": "JavaScript",
    ".jsx": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".go": "Go",
    ".rs": "Rust",
    ".java": "Java",
    ".kt": "Kotlin",
    ".kts": "Kotlin",
    ".c": "C",
    ".h": "C",
    ".cpp": "C++",
    ".cc": "C++",
    ".cxx": "C++",
    ".hpp": "C++",
    ".hh": "C++",
    ".cs": "C#",
    ".rb": "Ruby",
    ".php": "PHP",
    ".swift": "Swift",
    ".scala": "Scala",
    ".sh": "Shell",
    ".bash": "Shell",
    ".zsh": "Shell",
    ".ps1": "PowerShell",
    ".psm1": "PowerShell",
    ".sql": "SQL",
    ".html": "HTML",
    ".htm": "HTML",
    ".css": "CSS",
    ".scss": "SCSS",
    ".vue": "Vue",
    ".svelte": "Svelte",
    ".lua": "Lua",
    ".dart": "Dart",
    ".ex": "Elixir",
    ".exs": "Elixir",
    ".erl": "Erlang",
    ".hs": "Haskell",
    ".ml": "OCaml",
    ".fs": "F#",
    ".clj": "Clojure",
    ".zig": "Zig",
    ".nim": "Nim",
    ".pl": "Perl",
    ".pm": "Perl",
    ".proto": "Protobuf",
    ".graphql": "GraphQL",
    ".gql": "GraphQL",
    ".tf": "Terraform",
}

_OTHER_EXTENSIONS = {
    ".md": "Markdown",
    ".json": "JSON",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".toml": "TOML",
    ".xml": "XML",
    ".txt": "Text",
    ".rst": "reStructuredText",
    ".lock": "Lockfile",
    ".ini": "INI",
    ".cfg": "Config",
    ".csv": "CSV",
}

_SPECIAL_FILES = {
    "dockerfile": "Dockerfile",
    "makefile": "Makefile",
    "cmakelists.txt": "CMake",
    "gemfile": "Ruby",
    "rakefile": "Ruby",
    "go.mod": "Go",
    "cargo.toml": "TOML",
}


def classify_filename(name: str) -> tuple[str | None, str | None]:
    """Return ``(language, other_label)``. At most one of the two is set."""
    special = _SPECIAL_FILES.get(name.lower())
    if special in {"Dockerfile", "Makefile", "CMake", "Ruby", "Go"}:
        return special, None
    if special:
        return None, special
    suffix = Path(name).suffix.lower()
    if suffix in _CODE_EXTENSIONS:
        return _CODE_EXTENSIONS[suffix], None
    if suffix in _OTHER_EXTENSIONS:
        return None, _OTHER_EXTENSIONS[suffix]
    if suffix:
        return None, suffix
    return None, None


def _bump(bucket: dict[str, dict], label: str, size: int | None) -> None:
    row = bucket.setdefault(label, {"files": 0, "bytes": 0})
    row["files"] += 1
    if size:
        row["bytes"] += size


def _rows(bucket: dict[str, dict], key: str) -> list[dict]:
    rows = []
    for label, row in bucket.items():
        item = {key: label, "files": row["files"], "bytes": row["bytes"]}
        rows.append(item)
    rows.sort(key=lambda item: (-item["files"], item[key]))
    return rows


def inspect_directory(root: Path, *, max_depth: int, max_entries: int) -> dict:
    """Inventory ``root``. File contents are not read. Symlinks are not followed."""
    files = 0
    directories = 0
    symlinks = 0
    sensitive = 0
    skipped: list[dict] = []
    entries: list[dict] = []
    languages: dict[str, dict] = {}
    other: dict[str, dict] = {}
    truncated = False
    depth_limited = False
    skipped_truncated = False

    def add(item: dict) -> bool:
        nonlocal truncated
        if len(entries) >= max_entries:
            truncated = True
            return False
        entries.append(item)
        return True

    def walk(directory: Path, depth: int, relative: str) -> None:
        nonlocal files, directories, symlinks, sensitive, truncated, depth_limited, skipped_truncated
        if truncated:
            return
        try:
            children = list(os.scandir(directory))
        except OSError as exc:
            add({"path": relative or ".", "type": "directory", "error": exc.strerror or "unreadable"})
            return
        children.sort(key=lambda entry: entry.name)
        for entry in children:
            if truncated:
                return
            child_rel = f"{relative}/{entry.name}" if relative else entry.name
            try:
                is_link = entry.is_symlink()
            except OSError:
                add({"path": child_rel, "type": "unknown", "error": "stat failed"})
                continue
            if is_link:
                symlinks += 1
                add({"path": child_rel, "type": "symlink", "followed": False})
                continue
            try:
                is_dir = entry.is_dir(follow_symlinks=False)
            except OSError:
                add({"path": child_rel, "type": "unknown", "error": "stat failed"})
                continue
            if is_dir:
                child_path = Path(entry.path)
                reason = exclusion_reason(entry.name, child_path)
                if reason:
                    if len(skipped) < 200:
                        skipped.append({"path": child_rel, "reason": reason})
                    else:
                        skipped_truncated = True
                    continue
                directories += 1
                if not add({"path": child_rel, "type": "directory"}):
                    return
                if depth >= max_depth:
                    depth_limited = True
                    continue
                walk(child_path, depth + 1, child_rel)
                continue
            try:
                is_file = entry.is_file(follow_symlinks=False)
            except OSError:
                add({"path": child_rel, "type": "unknown", "error": "stat failed"})
                continue
            if not is_file:
                add({"path": child_rel, "type": "other"})
                continue
            files += 1
            sensitive_file = is_sensitive_name(entry.name)
            if sensitive_file:
                sensitive += 1
            try:
                size = entry.stat(follow_symlinks=False).st_size
            except OSError:
                size = None
            language, label = classify_filename(entry.name)
            item: dict = {"path": child_rel, "type": "file", "bytes": size}
            if sensitive_file:
                item["sensitive"] = True
                item["content"] = "not_read"
            if language:
                item["language"] = language
                _bump(languages, language, size)
            elif label:
                item["label"] = label
                _bump(other, label, size)
            else:
                _bump(other, "(no extension)", size)
            if not add(item):
                return

    walk(root, 1, "")
    notes = [
        "Inventory is read-only. File contents were not opened.",
        "Symlinks were recorded and were not followed.",
        "Dependency, build, cache, and version-control directories were not descended into.",
        "Language totals are approximate counts by extension and a few well-known filenames.",
    ]
    if truncated:
        notes.append("The entry list hit its bound. Totals describe only the scanned portion.")
    if depth_limited:
        notes.append("Some directories were listed and not entered because max_depth was reached.")
    return {
        "summary": {
            "files": files,
            "directories": directories,
            "symlinks": symlinks,
            "sensitive_files": sensitive,
            "skipped_directories": len(skipped),
            "truncated": truncated,
            "depth_limited": depth_limited,
            "approximate": True,
            "method": "extension_and_filename",
        },
        "languages": _rows(languages, "language"),
        "other": _rows(other, "label"),
        "skipped": skipped,
        "skipped_list_truncated": skipped_truncated,
        "entries": entries,
        "notes": notes,
    }

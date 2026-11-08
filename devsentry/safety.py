"""Path, output, and sensitive-file bounds shared by the DevSentry tools.

The helpers in this module never execute project code and never write to the
selected directory. Symlinks are detected so callers can refuse to follow them.
"""

from __future__ import annotations

import json
import os
from pathlib import Path


class PathSafetyError(Exception):
    """A user-supplied path failed a safety check."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


class ArgumentError(Exception):
    """A tool argument was the wrong type or could not be applied."""

    def __init__(self, message: str) -> None:
        super().__init__(message)


MAX_OUTPUT_CHARS = 60_000
MAX_SOURCE_BYTES = 256 * 1024

# Directory names skipped during inventory. Matching is case-insensitive.
# ``env`` is intentionally absent: it is only skipped when it contains a
# regular ``pyvenv.cfg``, because plenty of projects keep source in ``env``.
EXCLUSION_REASONS: dict[str, str] = {
    ".git": "version_control",
    ".hg": "version_control",
    ".svn": "version_control",
    ".jj": "version_control",
    ".bzr": "version_control",
    "node_modules": "dependency",
    "bower_components": "dependency",
    "jspm_packages": "dependency",
    "vendor": "dependency",
    ".venv": "dependency",
    "venv": "dependency",
    "__pypackages__": "dependency",
    "site-packages": "dependency",
    "pods": "dependency",
    "carthage": "dependency",
    "third_party": "dependency",
    "third-party": "dependency",
    "dist": "build",
    "build": "build",
    "target": "build",
    "out": "build",
    "bin": "build",
    "obj": "build",
    ".next": "build",
    ".nuxt": "build",
    ".output": "build",
    ".turbo": "build",
    "coverage": "build",
    "htmlcov": "build",
    ".eggs": "build",
    "__pycache__": "cache",
    ".pytest_cache": "cache",
    ".mypy_cache": "cache",
    ".ruff_cache": "cache",
    ".cache": "cache",
    ".tox": "cache",
    ".nox": "cache",
    ".gradle": "cache",
    ".parcel-cache": "cache",
    ".sass-cache": "cache",
    ".eslintcache": "cache",
    ".hypothesis": "cache",
}

_SENSITIVE_NAMES = {
    ".env",
    ".netrc",
    ".npmrc",
    ".pypirc",
    ".pgpass",
    ".htpasswd",
    "id_rsa",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
    "credentials.json",
    "secrets.json",
    "auth.json",
    "service-account.json",
    "secrets.yaml",
    "secrets.yml",
}
_SENSITIVE_SUFFIXES = (
    ".pem",
    ".key",
    ".p12",
    ".pfx",
    ".kdbx",
    ".keystore",
    ".jks",
)
_SENSITIVE_TOKENS = ("secret", "credential", "password", "passwd", "private-key", "private_key")


def bounded_int(value: object, *, default: int, lower: int, upper: int) -> tuple[int, bool]:
    """Return ``(applied, clamped)``. ``None`` selects the default.

    Booleans are rejected because they are integers in Python. Values outside
    ``lower``..``upper`` are clamped so a caller cannot request an unbounded scan.
    """
    if value is None:
        return default, False
    if isinstance(value, bool) or not isinstance(value, int):
        raise ArgumentError("expected an integer")
    if value < lower:
        return lower, True
    if value > upper:
        return upper, True
    return value, False


def resolve_directory(raw: object) -> tuple[Path, dict]:
    """Resolve ``raw`` to an existing real directory.

    The returned metadata records whether a symlink was resolved. Callers inspect
    the resolved directory and do not walk back through the link.
    """
    if not isinstance(raw, str) or not raw.strip():
        raise PathSafetyError("invalid_path", "path must be a non-empty string")
    if any(ord(ch) < 32 for ch in raw):
        raise PathSafetyError("invalid_path", "path contains a control character")

    expanded = os.path.expanduser(raw)
    requested = Path(expanded)
    if not requested.is_absolute():
        requested = Path.cwd() / requested
    requested_abs = Path(os.path.abspath(requested))

    try:
        requested_abs.lstat()
    except FileNotFoundError as exc:
        raise PathSafetyError("not_found", "path does not exist") from exc
    except OSError as exc:
        raise PathSafetyError("unreadable", f"path could not be read: {exc.strerror or exc}") from exc

    try:
        resolved = requested_abs.resolve(strict=True)
    except FileNotFoundError as exc:
        raise PathSafetyError("not_found", "path does not exist") from exc
    except OSError as exc:
        raise PathSafetyError("unreadable", f"path could not be resolved: {exc.strerror or exc}") from exc

    if not resolved.is_dir():
        raise PathSafetyError("not_a_directory", "path is not a directory")
    try:
        next(os.scandir(resolved), None)
    except PermissionError as exc:
        raise PathSafetyError("unreadable", "directory is not readable") from exc
    except OSError as exc:
        raise PathSafetyError("unreadable", f"directory is not readable: {exc.strerror or exc}") from exc

    followed = os.path.realpath(requested_abs) != os.path.abspath(requested_abs) or os.path.islink(requested_abs)
    info = {
        "requested": raw,
        "resolved": str(resolved),
        "symlink_resolved": bool(followed),
    }
    return resolved, info


def exclusion_reason(name: str, directory: Path) -> str | None:
    """Return why ``directory`` should not be descended into, or ``None``."""
    lowered = name.lower()
    reason = EXCLUSION_REASONS.get(lowered)
    if reason:
        return reason
    if lowered.endswith(".egg-info"):
        return "build"
    if lowered == "env":
        marker = directory / "pyvenv.cfg"
        try:
            if marker.is_symlink():
                return None
            if marker.is_file():
                return "dependency"
        except OSError:
            return None
    return None


def is_sensitive_name(name: str) -> bool:
    """True when the file name looks like credentials, keys, or a dotenv file."""
    lowered = name.lower()
    if lowered in _SENSITIVE_NAMES or lowered.startswith(".env"):
        return True
    if lowered.endswith(_SENSITIVE_SUFFIXES):
        return True
    stem = lowered.rsplit(".", 1)[0]
    return any(token in stem or token in lowered for token in _SENSITIVE_TOKENS)


def resolve_inside_project(project: Path, raw_path: str) -> Path | str:
    """Return a regular file inside ``project``, or a short omission reason.

    Absolute and relative paths are accepted. ``..``, symlinks, and any path
    that resolves outside ``project`` are refused before the file is opened.
    """
    if not isinstance(raw_path, str) or not raw_path or any(ord(ch) < 32 for ch in raw_path):
        return "invalid_path"
    project_real = project.resolve()
    candidate = Path(raw_path)
    if candidate.is_absolute():
        try:
            relative = candidate.relative_to(project_real)
        except ValueError:
            return "outside_project"
        parts = relative.parts
    else:
        if any(part in {"", ".", ".."} for part in candidate.parts):
            return "outside_project"
        parts = candidate.parts

    current = project_real
    for part in parts:
        if part in {"", ".", ".."}:
            return "outside_project"
        current = current / part
        try:
            if current.is_symlink():
                return "symlink"
            if not current.exists():
                return "not_in_project"
        except OSError:
            return "unreadable"
    try:
        if not current.is_file():
            return "not_a_file"
    except OSError:
        return "unreadable"
    if is_sensitive_name(current.name):
        return "sensitive_path"
    try:
        real = current.resolve()
    except OSError:
        return "unreadable"
    if real != project_real and project_real not in real.parents:
        return "outside_project"
    return current


def read_bounded_text(path: Path) -> str | None:
    """Read up to ``MAX_SOURCE_BYTES`` of a regular file as UTF-8 text.

    Returns ``None`` when the file is larger than the bound. Callers must
    already have rejected symlinks and paths outside the project.
    """
    try:
        size = path.stat().st_size
    except OSError:
        return None
    if size > MAX_SOURCE_BYTES:
        return None
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if len(data) > MAX_SOURCE_BYTES:
        return None
    return data.decode("utf-8", errors="replace")


def json_text(payload: dict) -> str:
    """Serialize ``payload`` and keep the string inside ``MAX_OUTPUT_CHARS``."""
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if len(text) <= MAX_OUTPUT_CHARS:
        return text

    reduced = dict(payload)
    reduced["output_truncated"] = True
    for key in ("entries", "frames", "leads"):
        value = reduced.get(key)
        if isinstance(value, list) and len(value) > 10:
            reduced[key] = value[:10]
    for key in ("staged", "unstaged"):
        scope = reduced.get(key)
        if isinstance(scope, dict) and isinstance(scope.get("files"), list):
            files = []
            for item in scope["files"][:8]:
                if isinstance(item, dict) and isinstance(item.get("patch"), str) and len(item["patch"]) > 400:
                    item = dict(item)
                    item["patch"] = item["patch"][:400]
                    item["patch_truncated"] = True
                files.append(item)
            scope = dict(scope)
            scope["files"] = files
            reduced[key] = scope
    text = json.dumps(reduced, ensure_ascii=False, indent=2)
    if len(text) <= MAX_OUTPUT_CHARS:
        return text
    return json.dumps(
        {
            "ok": False,
            "error": {
                "code": "output_too_large",
                "message": "The result exceeded the output bound after reduction.",
            },
        }
    )


def error_payload(tool: str, code: str, message: str) -> dict:
    return {"ok": False, "tool": tool, "error": {"code": code, "message": message}}

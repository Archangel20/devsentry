"""Hermes tool handlers.

Each handler accepts the argument dict Hermes passes and ``**kwargs`` for the
context fields Hermes may add later. Every path returns a JSON string.
"""

from __future__ import annotations

import json
import subprocess

from .diagnose import attach_source_context, parse_trace
from .inspector import inspect_directory
from .review import review_repository
from .safety import (
    ArgumentError,
    PathSafetyError,
    bounded_int,
    error_payload,
    json_text,
    resolve_directory,
)


def _finish(payload: dict) -> str:
    return json_text(payload)


def inspect_project(args: dict, **kwargs) -> str:
    """Inventory one directory. ``kwargs`` is accepted and ignored."""
    del kwargs
    if not isinstance(args, dict):
        return _finish(error_payload("inspect_project", "invalid_argument", "arguments must be an object"))
    try:
        root, path_info = resolve_directory(args.get("path"))
        max_depth, depth_clamped = bounded_int(args.get("max_depth"), default=6, lower=1, upper=12)
        max_entries, entries_clamped = bounded_int(
            args.get("max_entries"), default=500, lower=1, upper=2000
        )
    except PathSafetyError as exc:
        return _finish(error_payload("inspect_project", exc.code, str(exc)))
    except ArgumentError as exc:
        return _finish(error_payload("inspect_project", "invalid_argument", str(exc)))
    except Exception as exc:  # defensive: handlers must not raise
        return _finish(error_payload("inspect_project", "internal", exc.__class__.__name__))

    try:
        body = inspect_directory(root, max_depth=max_depth, max_entries=max_entries)
    except Exception as exc:
        return _finish(error_payload("inspect_project", "internal", exc.__class__.__name__))
    return _finish(
        {
            "ok": True,
            "tool": "inspect_project",
            "path": path_info,
            "limits": {
                "max_depth": max_depth,
                "max_entries": max_entries,
                "clamped": depth_clamped or entries_clamped,
            },
            **body,
        }
    )


def diagnose_error(args: dict, **kwargs) -> str:
    """Parse a pasted trace and, optionally, quote a few in-project source lines."""
    del kwargs
    if not isinstance(args, dict):
        return _finish(error_payload("diagnose_error", "invalid_argument", "arguments must be an object"))
    trace = args.get("trace")
    if not isinstance(trace, str) or not trace.strip():
        return _finish(error_payload("diagnose_error", "invalid_argument", "trace must be a non-empty string"))
    if "\x00" in trace:
        return _finish(error_payload("diagnose_error", "invalid_argument", "trace contains a null byte"))
    try:
        context_lines, context_clamped = bounded_int(
            args.get("context_lines"), default=2, lower=0, upper=5
        )
    except ArgumentError as exc:
        return _finish(error_payload("diagnose_error", "invalid_argument", str(exc)))

    try:
        parsed = parse_trace(trace)
    except Exception as exc:
        return _finish(error_payload("diagnose_error", "internal", exc.__class__.__name__))

    project_note = None
    raw_project = args.get("project_path")
    if raw_project is not None:
        try:
            project, path_info = resolve_directory(raw_project)
            parsed = attach_source_context(parsed, project, context_lines=context_lines)
            project_note = path_info
        except PathSafetyError as exc:
            project_note = {"ok": False, "error": {"code": exc.code, "message": str(exc)}}
        except Exception as exc:
            project_note = {"ok": False, "error": {"code": "internal", "message": exc.__class__.__name__}}

    payload = {
        "ok": True,
        "tool": "diagnose_error",
        "limits": {"context_lines": context_lines, "clamped": context_clamped},
        **parsed,
    }
    if project_note is not None:
        payload["project_path"] = project_note
    if not parsed["parsed"]:
        excerpt = trace.strip().replace("\r\n", "\n")
        if len(excerpt) > 500:
            excerpt = excerpt[:500]
        payload["excerpt"] = excerpt
    return _finish(payload)


def review_changes(args: dict, **kwargs) -> str:
    """Read staged and unstaged tracked diffs. Does not change the repository."""
    del kwargs
    if not isinstance(args, dict):
        return _finish(error_payload("review_changes", "invalid_argument", "arguments must be an object"))
    try:
        root, path_info = resolve_directory(args.get("path"))
        context_lines, context_clamped = bounded_int(
            args.get("context_lines"), default=3, lower=0, upper=10
        )
        max_patch_bytes, patch_clamped = bounded_int(
            args.get("max_patch_bytes"), default=20_000, lower=200, upper=80_000
        )
    except PathSafetyError as exc:
        return _finish(error_payload("review_changes", exc.code, str(exc)))
    except ArgumentError as exc:
        return _finish(error_payload("review_changes", "invalid_argument", str(exc)))
    except Exception as exc:
        return _finish(error_payload("review_changes", "internal", exc.__class__.__name__))

    try:
        body = review_repository(root, context_lines=context_lines, max_patch_bytes=max_patch_bytes)
    except subprocess.TimeoutExpired:
        return _finish(error_payload("review_changes", "git_timeout", "git did not finish within the time limit"))
    except FileNotFoundError:
        return _finish(error_payload("review_changes", "git_not_found", "git is not available on PATH"))
    except Exception as exc:
        return _finish(error_payload("review_changes", "internal", exc.__class__.__name__))

    if not body.get("ok") and "error" in body and "tool" not in body:
        error = body["error"]
        return _finish(error_payload("review_changes", error.get("code", "git_error"), error.get("message", "git failed")))
    body["tool"] = "review_changes"
    body["path"] = path_info
    body["limits"] = {
        "context_lines": context_lines,
        "max_patch_bytes": max_patch_bytes,
        "clamped": context_clamped or patch_clamped,
    }
    return _finish(body)


def loads(payload: str) -> dict:
    """Parse a handler result. Used by tests and the demo script."""
    parsed = json.loads(payload)
    if not isinstance(parsed, dict):
        raise TypeError("tool result must be a JSON object")
    return parsed

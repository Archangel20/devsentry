#!/usr/bin/env python3
"""Print concise results from Hermes's real tool registry.

This file is a demo helper. It is not a Hermes CLI command. Hermes must
launch it with the runtime interpreter so ``discover_plugins`` and
``tools.registry.dispatch`` are the ones shipped with that install.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

from hermes_cli.plugins import discover_plugins
from tools.registry import registry


def say(text: str = "") -> None:
    print(text, flush=True)


def screen(title: str) -> None:
    print("\033[H\033[2J", end="", flush=True)
    say("Direct Hermes tool execution; no model inference")
    say("")
    say(title)


def hold(seconds: float) -> None:
    time.sleep(seconds)


def clip(text: str, limit: int) -> str:
    single = " ".join(text.split())
    if len(single) <= limit:
        return single
    return single[: limit - 1] + "…"


def main() -> int:
    project = Path(os.environ["DEVSENTRY_PROJECT"])
    trace_path = Path(os.environ["DEVSENTRY_TRACE"])
    out_path = Path(os.environ["DEVSENTRY_RESULTS"])
    screen("Helper: scripts/hermes_demo_tools.py")
    say("Calls tools.registry.dispatch inside this Hermes process.")
    say("Not a built-in hermes subcommand.")
    say("")
    say("Loading plugins from this Hermes home…")
    discover_plugins(force=True)
    names = ["inspect_project", "diagnose_error", "review_changes"]
    missing = [name for name in names if registry.get_entry(name) is None]
    if missing:
        say("Missing tools: " + ", ".join(missing))
        return 1
    say("Registered toolset devsentry:")
    for name in names:
        entry = registry.get_entry(name)
        say(f"  {name}   toolset={entry.toolset}")
    hold(4)

    screen("inspect_project")
    say(f"directory: {project}")
    inspected = json.loads(registry.dispatch("inspect_project", {"path": str(project)}))
    say(f"ok: {inspected.get('ok')}")
    summary = inspected.get("summary") or {}
    say(
        "files {files}   directories {directories}   "
        "skipped directories {skipped_directories}".format(**{
            "files": summary.get("files"),
            "directories": summary.get("directories"),
            "skipped_directories": summary.get("skipped_directories"),
        })
    )
    say("approximate languages: " + ", ".join(
        f"{row['language']} {row['files']}" for row in inspected.get("languages") or []
    ))
    skipped = inspected.get("skipped") or []
    say("skipped: " + ", ".join(item["path"] for item in skipped))
    say("contents were not opened. symlinks were not followed.")
    hold(7)

    screen("diagnose_error")
    say(f"trace: {trace_path.name}")
    diagnosis = json.loads(registry.dispatch("diagnose_error", {
        "trace": trace_path.read_text(encoding="utf-8"),
        "project_path": str(project),
        "context_lines": 1,
    }))
    say(f"ok: {diagnosis.get('ok')}    certainty: {diagnosis.get('certainty')}")
    for item in diagnosis.get("exceptions") or []:
        message = item.get("message") or ""
        say(f"exception: {item.get('name')}" + (f": {message}" if message else ""))
    for frame in diagnosis.get("frames") or []:
        function = frame.get("function") or ""
        say(f"frame: {frame.get('path')}:{frame.get('line')}  {function}".rstrip())
    leads = diagnosis.get("leads") or []
    if leads:
        say("lead: " + clip(leads[0], 78))
    disclaimer = diagnosis.get("disclaimer") or ""
    first, _, rest = disclaimer.partition(". ")
    say("disclaimer: " + first + ("." if first and not first.endswith(".") else ""))
    if rest:
        say(rest)
    cited = None
    for frame in diagnosis.get("frames") or []:
        context = frame.get("context") or {}
        if context.get("omitted"):
            continue
        for row in context.get("snippet") or []:
            if row.get("cited"):
                cited = row.get("text")
    if cited:
        say("cited line: " + clip(cited, 80))
    hold(8)

    screen("review_changes")
    reviewed = json.loads(registry.dispatch("review_changes", {"path": str(project)}))
    say(f"ok: {reviewed.get('ok')}")
    mutation = reviewed.get("mutation") or {}
    say(f"staging: {mutation.get('staging')}")
    say(f"worktree writes: {mutation.get('worktree_writes')}")
    say(f"index unchanged: {mutation.get('index_sha256_unchanged')}")
    say(f"untracked count (not read): {reviewed.get('untracked_count')}")
    for label in ("staged", "unstaged"):
        scope = reviewed.get(label) or {}
        files = scope.get("files") or []
        if not files:
            say(f"{label}: none")
            continue
        for item in files:
            if item.get("patch_omitted"):
                say(f"{label}: {item.get('path')}  {item.get('status')}  patch omitted ({item.get('reason')})")
                continue
            patch = item.get("patch") or ""
            added = ""
            for line in patch.splitlines():
                if line.startswith("+") and not line.startswith("+++") and line.strip() != "+":
                    added = line[1:]
            say(f"{label}: {item.get('path')}  {item.get('status')}  {clip(added, 60)}".rstrip())
    hold(8)

    screen("Limits")
    say("No model chat was tested. The model did not choose these tools.")
    say("Three read-only tools only. Nothing was staged or edited.")
    say("This is not a claim of hackathon acceptance.")
    payload = {
        "inspect_project": inspected,
        "diagnose_error": diagnosis,
        "review_changes": reviewed,
    }
    out_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    hold(6)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"helper failed: {exc.__class__.__name__}", flush=True)
        raise

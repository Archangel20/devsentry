#!/usr/bin/env python3
"""Story-demo printer for real Hermes registry results.

Not a Hermes subcommand and not a model. Each phase prints a short screen
from tools.registry.dispatch, then waits so a recording can hold it.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

from hermes_cli.plugins import discover_plugins
from tools.registry import registry

PHASE = os.environ["DEVSENTRY_PHASE"]
PROJECT = Path(os.environ["DEVSENTRY_PROJECT"])
TRACE = Path(os.environ["DEVSENTRY_TRACE"])
RESULTS = Path(os.environ["DEVSENTRY_RESULTS"])


GOLD = "\033[38;5;179m"
DIM = "\033[38;5;245m"
RED = "\033[38;5;174m"
GREEN = "\033[38;5;108m"
RESET = "\033[0m"


def say(text: str = "") -> None:
    print(text, flush=True)


def screen(heading: str) -> None:
    print("\033[H\033[2J", end="", flush=True)
    say(f"{GOLD}{heading}{RESET}")
    say("")


def settle() -> None:
    path = Path(os.environ["STORY_MARKS"])
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"{PHASE} {time.time():.3f}\n")
    time.sleep(float(os.environ.get("STORY_HOLD", "8")))


def clip(text: str, limit: int) -> str:
    single = " ".join(text.split())
    if len(single) <= limit:
        return single
    return single[: limit - 1] + "…"


def save(phase: str, payload: dict) -> None:
    current = {}
    if RESULTS.exists():
        current = json.loads(RESULTS.read_text(encoding="utf-8"))
    current[phase] = payload
    RESULTS.write_text(json.dumps(current, indent=2) + "\n", encoding="utf-8")


def tools_ready() -> None:
    discover_plugins(force=True)
    missing = [
        name for name in ("inspect_project", "diagnose_error", "review_changes")
        if registry.get_entry(name) is None
    ]
    if missing:
        say("Missing tools: " + ", ".join(missing))
        raise SystemExit(1)


def inspect() -> None:
    tools_ready()
    payload = json.loads(registry.dispatch("inspect_project", {"path": str(PROJECT)}))
    save("inspect_project", payload)
    summary = payload.get("summary") or {}
    languages = ", ".join(
        f"{row['language']} {row['files']}" for row in payload.get("languages") or []
    )
    skipped = ", ".join(item["path"] for item in payload.get("skipped") or [])
    screen("inspect_project")
    say(f"{DIM}files{RESET}         {summary.get('files')}")
    say(f"{DIM}directories{RESET}   {summary.get('directories')}")
    say(f"{DIM}approximate{RESET}   {languages}")
    say(f"{DIM}skipped{RESET}       {skipped}")
    settle()


def diagnose() -> None:
    tools_ready()
    payload = json.loads(registry.dispatch("diagnose_error", {
        "trace": TRACE.read_text(encoding="utf-8"),
        "project_path": str(PROJECT),
        "context_lines": 1,
    }))
    save("diagnose_error", payload)
    screen("diagnose_error")
    exc = (payload.get("exceptions") or [{}])[0]
    message = exc.get("message") or ""
    say(f"{RED}{exc.get('name')}{RESET}: {message}".rstrip(": "))
    for frame in payload.get("frames") or []:
        name = Path(str(frame.get("path"))).name
        say(f"{DIM}{name}:{frame.get('line')}{RESET}  {frame.get('function') or ''}".rstrip())
    cited = ""
    for frame in payload.get("frames") or []:
        context = frame.get("context") or {}
        for row in context.get("snippet") or []:
            if not row.get("cited"):
                continue
            text = str(row.get("text") or "").strip()
            if "denominator" in text or not cited:
                cited = text
    if cited:
        say(f"{DIM}cited{RESET}        {cited}")
    lead = ((payload.get("leads") or [""])[0])
    clause = lead.split(",")[0].strip()
    if clause != lead:
        clause = clause + "…"
    say(f"{DIM}lead{RESET}         {clause}")
    say(f"{DIM}certainty{RESET}    {GOLD}{payload.get('certainty')}{RESET}")
    settle()


def review() -> None:
    tools_ready()
    payload = json.loads(registry.dispatch("review_changes", {"path": str(PROJECT)}))
    save("review_changes", payload)
    screen("review_changes")
    mutation = payload.get("mutation") or {}
    for label in ("staged", "unstaged"):
        files = (payload.get(label) or {}).get("files") or []
        if not files:
            say(f"{DIM}{label}{RESET}    none")
            continue
        for item in files:
            say(f"{DIM}{label}{RESET}    {item.get('path')}")
            shown = 0
            for line in (item.get("patch") or "").splitlines():
                if line[:1] not in "+-" or line.startswith(("+++", "---")):
                    continue
                if line.strip() in {"+", "-"}:
                    continue
                color = GREEN if line.startswith("+") else RED
                say(f"  {color}{clip(line, 64)}{RESET}")
                shown += 1
                if shown == 2:
                    break
    say("")
    say(f"{DIM}index unchanged{RESET}  {GREEN}{mutation.get('index_sha256_unchanged')}{RESET}")
    say(f"{DIM}staging{RESET}           {mutation.get('staging')}")
    settle()


{"inspect": inspect, "diagnose": diagnose, "review": review}[PHASE]()

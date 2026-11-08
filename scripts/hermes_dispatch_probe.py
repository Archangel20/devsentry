"""Dispatch DevSentry tools through Hermes's own registry.

Hermes launches this file. It is not a unit test. HERMES_HOME and
DEVSENTRY_PROJECT must already be set.
"""

from __future__ import annotations

import json
import os
import sys

from hermes_cli.plugins import discover_plugins
from tools.registry import registry


def main() -> int:
    discover_plugins(force=True)
    project = os.environ["DEVSENTRY_PROJECT"]
    names = ["inspect_project", "diagnose_error", "review_changes"]
    missing = [name for name in names if registry.get_entry(name) is None]
    results = {}
    if not missing:
        trace = "\n".join(
            [
                "Traceback (most recent call last):",
                f'  File "{project}/app.py", line 2, in value',
                "    return 1 / 1",
                "ZeroDivisionError: division by zero",
            ]
        )
        results["inspect_project"] = json.loads(registry.dispatch("inspect_project", {"path": project}))
        results["diagnose_error"] = json.loads(
            registry.dispatch(
                "diagnose_error",
                {"trace": trace, "project_path": project, "context_lines": 1},
            )
        )
        results["review_changes"] = json.loads(registry.dispatch("review_changes", {"path": project}))
    registered = {}
    for name in names:
        entry = registry.get_entry(name)
        registered[name] = None if entry is None else {
            "toolset": entry.toolset,
            "schema_name": (entry.schema or {}).get("name"),
        }
    print("DEVSENTRY_JSON:" + json.dumps({
        "missing": missing,
        "registered": registered,
        "results": results,
    }))
    return 0 if not missing else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"DEVSENTRY_PROBE_ERROR:{exc.__class__.__name__}: {exc}", file=sys.stderr)
        raise

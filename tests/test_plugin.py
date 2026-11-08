"""Plugin wiring tests.

``register`` is called with a stand-in context object. That checks our manifest
and handlers agree. It does not load Hermes. Runtime discovery against a real
Hermes install is ``scripts/hermes_integration.py``.
"""

from __future__ import annotations

from pathlib import Path

from devsentry import register
from devsentry.schemas import DIAGNOSE_ERROR, INSPECT_PROJECT, REVIEW_CHANGES

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "devsentry" / "plugin.yaml"


class RecordingContext:
    def __init__(self) -> None:
        self.tools = []

    def register_tool(self, **kwargs) -> None:
        self.tools.append(kwargs)


def declared_tools() -> list[str]:
    tools = []
    grabbing = False
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        if line.startswith("provides_tools:"):
            grabbing = True
            continue
        if not grabbing:
            continue
        if line.startswith("  - "):
            tools.append(line.split("- ", 1)[1].strip())
            continue
        if line.strip():
            break
    return tools


def test_manifest_matches_registration_and_schemas():
    ctx = RecordingContext()
    register(ctx)
    names = [tool["name"] for tool in ctx.tools]
    assert names == ["inspect_project", "diagnose_error", "review_changes"]
    assert names == declared_tools()
    schemas = {
        "inspect_project": INSPECT_PROJECT,
        "diagnose_error": DIAGNOSE_ERROR,
        "review_changes": REVIEW_CHANGES,
    }
    for tool in ctx.tools:
        assert tool["toolset"] == "devsentry"
        assert tool["schema"] is schemas[tool["name"]]
        assert tool["schema"]["name"] == tool["name"]
        assert tool["description"] == tool["schema"]["description"]
        assert callable(tool["handler"])
        assert "provides_hooks" not in MANIFEST.read_text(encoding="utf-8")

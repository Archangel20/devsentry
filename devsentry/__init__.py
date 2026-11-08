"""DevSentry registration for Hermes Agent.

Hermes loads this module and calls ``register(ctx)`` once. The call matches
``PluginContext.register_tool`` in Hermes Agent v0.23.0
(commit 2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19): name, toolset, schema, and
handler. Handlers follow the documented ``(args, **kwargs) -> str`` contract.
"""

from __future__ import annotations

from . import schemas, tools


def register(ctx) -> None:
    """Register the three read-only MVP tools."""
    ctx.register_tool(
        name="inspect_project",
        toolset="devsentry",
        schema=schemas.INSPECT_PROJECT,
        handler=tools.inspect_project,
        description=schemas.INSPECT_PROJECT_DESCRIPTION,
    )
    ctx.register_tool(
        name="diagnose_error",
        toolset="devsentry",
        schema=schemas.DIAGNOSE_ERROR,
        handler=tools.diagnose_error,
        description=schemas.DIAGNOSE_ERROR_DESCRIPTION,
    )
    ctx.register_tool(
        name="review_changes",
        toolset="devsentry",
        schema=schemas.REVIEW_CHANGES,
        handler=tools.review_changes,
        description=schemas.REVIEW_CHANGES_DESCRIPTION,
    )

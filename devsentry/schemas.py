"""Tool schemas Hermes shows to the model.

Descriptions live here and are repeated as ``register_tool(description=...)``
so the schema text and the registry metadata stay the same.
"""

INSPECT_PROJECT_DESCRIPTION = (
    "Read-only inventory of one selected project directory. Returns nested "
    "entries, approximate language counts by file extension, and directories "
    "that were skipped because they are dependencies, build output, caches, "
    "or version control. Does not open file contents, follow symlinks, or "
    "execute project code. Use this when the user asks what a folder contains "
    "or which languages it uses."
)

DIAGNOSE_ERROR_DESCRIPTION = (
    "Analyze a pasted error message or stack trace. Extracts exception names, "
    "file paths, line numbers, and explainable debugging leads. Leads are "
    "suggestions to verify, not a confirmed root cause. When project_path is "
    "set, may include a few source lines only for cited files that stay inside "
    "that directory and are not symlinks. Does not execute project code. Use "
    "this when the user pastes a traceback or exception."
)

REVIEW_CHANGES_DESCRIPTION = (
    "Read tracked Git changes for one repository directory. Reports staged "
    "changes (index compared with HEAD) and unstaged changes (working tree "
    "compared with the index) as separate scopes. Does not include untracked "
    "file contents, does not stage or edit files, and omits patch text for "
    "paths that look like secrets. Use this when the user wants their current "
    "tracked diff explained."
)

INSPECT_PROJECT = {
    "name": "inspect_project",
    "description": INSPECT_PROJECT_DESCRIPTION,
    "parameters": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Directory to inventory. Absolute or relative to the current working directory.",
            },
            "max_depth": {
                "type": "integer",
                "description": "How many directory levels to enter below the selected directory. Clamped to 1..12. Default 6.",
            },
            "max_entries": {
                "type": "integer",
                "description": "Maximum entries to return. Clamped to 1..2000. Default 500.",
            },
        },
        "required": ["path"],
    },
}

DIAGNOSE_ERROR = {
    "name": "diagnose_error",
    "description": DIAGNOSE_ERROR_DESCRIPTION,
    "parameters": {
        "type": "object",
        "properties": {
            "trace": {
                "type": "string",
                "description": "The pasted error message or stack trace. The tool only parses this text.",
            },
            "project_path": {
                "type": "string",
                "description": "Optional project directory. Cited files are read only when they resolve inside this directory.",
            },
            "context_lines": {
                "type": "integer",
                "description": "Source lines to include on each side of a cited line. Clamped to 0..5. Default 2.",
            },
        },
        "required": ["trace"],
    },
}

REVIEW_CHANGES = {
    "name": "review_changes",
    "description": REVIEW_CHANGES_DESCRIPTION,
    "parameters": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Git work tree, or a directory inside one. Review is limited to this directory.",
            },
            "context_lines": {
                "type": "integer",
                "description": "Unified diff context lines. Clamped to 0..10. Default 3.",
            },
            "max_patch_bytes": {
                "type": "integer",
                "description": "Maximum bytes kept from each file's patch. Clamped to 200..80000. Default 20000.",
            },
        },
        "required": ["path"],
    },
}

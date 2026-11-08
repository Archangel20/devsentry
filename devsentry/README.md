# DevSentry

Read-only Hermes Agent tools: `inspect_project`, `diagnose_error`, and `review_changes`.

They register from `register(ctx)` in this directory. They do not edit, stage, or commit files, and they do not run the project under inspection.

This copy was loaded on Hermes Agent v0.23.0 (`requires_hermes: ">=0.23.0"`). Older releases were not tested.

## What it accesses

- Local filesystem: directory names and file sizes, plus a few source lines when a pasted traceback cites a file inside the directory you pass.
- Git: a subprocess with an argument list, used to read tracked diffs. It does not stage.
- It does not make network calls, send telemetry, or read Hermes `auth.json`, `.env` contents, or another application's credential store.

Leads from `diagnose_error` include `certainty: leads_only`. They are not a confirmed root cause.

Install and test steps for the full tree are in the repository `README.md` and `docs/install.md`.

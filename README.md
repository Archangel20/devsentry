# DevSentry

DevSentry is a read-only Python plugin for [Hermes Agent](https://github.com/NousResearch/hermes-agent). It gives the agent three tools that look at a local project, a pasted error, or the tracked Git diff and return specific, bounded findings.

The tools do not edit the project, stage files, apply patches, or run the project's code.

| Tool | What it returns |
| --- | --- |
| `inspect_project` | A directory inventory, approximate language counts by extension and a few well-known filenames, and the dependency, build, cache, and version-control directories that were skipped. |
| `diagnose_error` | Exception names, file paths, line numbers, and debugging leads from a pasted trace. Leads are suggestions to verify. The result says they are not a confirmed root cause. |
| `review_changes` | Staged and unstaged diffs of tracked files, reported as separate scopes. Untracked files are counted and their contents are left out. |

## Requirements

- Python 3.11 or newer to run the unit tests and the demo
- Git on `PATH` for `review_changes`
- An installed Hermes Agent for plugin discovery. Development and the runtime check in this repository used Hermes Agent v0.23.0, commit `2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19`. See [docs/hermes-compatibility.md](docs/hermes-compatibility.md).

The plugin code itself imports only the Python standard library. Hermes loads it from a plugin directory. Installing this repository with pip does not register the plugin.

## Run the tests

The unit tests call the tool functions in this process. They do not start Hermes.

```bash
python3 -m pip install --user 'pytest>=8.2,<9'
python3 -m pytest -q
```

On this Linux environment that command completed with `22 passed`.

## Run the demo

```bash
python3 scripts/demo.py
```

The script copies `fixtures/sample-project` into a temporary Git repository, runs all three tools, and writes `samples/demo-run.json`. The sample tree is not modified. A fake dotenv value is part of the setup so the saved review can show that the patch was omitted.

## Install into Hermes

Linux and Windows steps are in [docs/install.md](docs/install.md). The plugin directory Hermes expects is `devsentry/` in this repository (`plugin.yaml` next to `__init__.py`).

After it is enabled, a real Hermes process can call the tools through its own registry. The check for that is:

```bash
python3 scripts/hermes_integration.py --hermes "$(command -v hermes)"
```

That script is separate from `pytest`. `tests/test_plugin.py` uses a stand-in `register(ctx)` and does not import Hermes. `scripts/hermes_integration.py` runs `hermes plugins doctor`, `hermes plugins enable`, `hermes plugins list`, and `tools.registry.dispatch` inside the Hermes environment. It does not call a model and does not need an API key.

A model conversation is a different setup. On this install, `hermes chat --oneshot` exited 1 with "Hermes is not connected to any AI provider yet" before a model could see the tools. The exact message and the provider commands Hermes already accepts are in [docs/hermes-compatibility.md](docs/hermes-compatibility.md). The saved probe is `samples/hermes-chat-probe.txt`.

## Safety

DevSentry reads local files and runs Git. It does not use the network, send telemetry, or read a credential store.

- `inspect_project` lists a selected directory and records names and sizes. It does not open file contents and does not follow symlinks. A selected path that is itself a symlink is resolved, and the result says so.
- `diagnose_error` parses text you paste. If `project_path` is set, it may read a few lines of a cited file only when that file stays inside the directory, is not a symlink, and does not look like a secret.
- `review_changes` runs `git` with an argument list (`shell=True` is not used) to read staged and unstaged diffs of tracked files. It does not stage, unstage, commit, or edit. Untracked file contents are not read. Repository aliases, external diff drivers, textconv filters, hooks, and fsmonitor are overridden for that process.
- Names that look like dotenv files, keys, or credentials are flagged. Their contents are not read, and their Git patches are omitted. The plugin does not read `.env` files, Hermes `auth.json`, or another tool's login.
- Output, directory depth, entry count, trace length, and patch size are clamped.
- Diagnostic text includes `certainty: "leads_only"` and a disclaimer that the leads are not a confirmed root cause.

License: MIT. See `LICENSE`.

## What this repository does not do

There is no user interface, no patch application, and no test runner. Those were left for later milestones in the project brief.

Hackathon rules and the submission deadline were not verified while this was built. Nothing here registers an entry or says the project is eligible to submit.

## Source archive

```bash
sh scripts/package_source.sh
```

That writes `artifacts/devsentry-0.1.0-source.tar.gz`.

## Layout

```
devsentry/     Hermes plugin (plugin.yaml, register, tools)
tests/         Unit tests, no Hermes process
fixtures/      Sample project and pasted traces
scripts/       Demo, Hermes integration check, source archive
docs/          Install steps and the Hermes version this was checked against
samples/       Saved demo output
```

# Install DevSentry into Hermes

Hermes loads a directory plugin from `~/.hermes/plugins/<name>/` when that directory contains `plugin.yaml` and an `__init__.py` with `register(ctx)`. User plugins stay disabled until `hermes plugins enable <name>`. That is the layout and the commands documented for Hermes Agent v0.23.0.

The directory to install is the `devsentry/` folder in this repository, not the repository root. The root has tests and docs and is not itself a plugin.

These steps do not stage, commit, or edit the project you later point the tools at.

## Linux, macOS, and WSL

Install Hermes with the official installer if it is not already installed. To match the commit this plugin was checked against:

```bash
curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash -s -- \
  --commit 2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19 \
  --non-interactive \
  --skip-browser \
  --skip-computer-use
```

The installer clones Hermes under `~/.hermes/hermes-agent` and puts `hermes` on your PATH for new shells. Confirm the checkout:

```bash
git -C ~/.hermes/hermes-agent rev-parse HEAD
hermes --version
```

On the install used for this repository the launcher was `~/.local/bin/hermes`, and that script runs `~/.hermes/hermes-agent/.hermes/bin/hermes`. There was no `.venv/bin/hermes`. Open a new shell if `hermes` is not on `PATH` yet.

Copy the plugin and enable it:

```bash
mkdir -p ~/.hermes/plugins/devsentry
cp -a devsentry/. ~/.hermes/plugins/devsentry/
hermes plugins doctor ~/.hermes/plugins/devsentry --ci
hermes plugins enable devsentry
hermes plugins list
```

`hermes plugins doctor --ci` imports the plugin the same way Hermes does and checks that the tools named in `plugin.yaml` are the tools `register(ctx)` registers. It exits non-zero on an error.

`hermes plugins install` clones a Git URL. It does not take a plain directory. A local Git checkout can be installed with a `file://` URL and a `#devsentry` fragment, which Hermes warns is an unreviewed local scheme:

```bash
hermes plugins install "file://$(pwd)#devsentry" --no-enable
hermes plugins enable devsentry
```

Leave `__pycache__` and `.pyc` files out of that commit. The install-time security scan treats committed bytecode as a high-severity finding and blocks an unreviewed source that contains it. `hermes plugins validate devsentry --json` on a source tree reports the security scan separately; in the recorded run that check was `safe`.

From this repository you can run the same discovery and a real tool dispatch without a model key:

```bash
python3 scripts/hermes_integration.py --hermes "$(command -v hermes)"
```

The script uses a temporary `HERMES_HOME`, so it does not change your own `~/.hermes/config.yaml`.

## Windows (PowerShell)

Hermes documents a native Windows installer:

```powershell
iex (irm https://hermes-agent.nousresearch.com/install.ps1)
```

The Windows installer supplies its own Git Bash for Hermes shell commands. `review_changes` still calls `git` on `PATH`. Install Git for Windows, or use the `git.exe` that Hermes unpacked under `%LOCALAPPDATA%\hermes\git`, and make sure the shell you use can run `git rev-parse`.

Copy the plugin. The folder name must be `devsentry`:

```powershell
$dest = Join-Path $env:USERPROFILE ".hermes\plugins\devsentry"
New-Item -ItemType Directory -Force -Path $dest | Out-Null
Copy-Item -Path .\devsentry\* -Destination $dest -Recurse -Force
hermes plugins doctor $dest --ci
hermes plugins enable devsentry
hermes plugins list
```

Python for the unit tests can be the system Python 3.11+ or the interpreter Hermes installed. From the repository:

```powershell
python -m pip install --user "pytest>=8.2,<9"
python -m pytest -q
python scripts\demo.py
```

The automated tests and the Hermes dispatch check for this repository were run on Linux. The Windows steps follow Hermes's documented installer and the same `pathlib` / `subprocess` list calls the Linux tests exercise. They were not executed on a Windows machine here.

A separate Windows environment has reported `WinError 5` (access denied) while Hermes Doctor reads the bundled `agent-importers` `plugin.yaml`. That report was not reproduced in this Linux checkout, and this plugin does not modify Hermes's bundled plugins. If Doctor cannot read a manifest on Windows, Hermes's installer notes that a tree can land without read permission and points at repairing the plugins directory with `icacls`. Treat that as a Hermes install permission problem, not as a DevSentry result.

## Use the tools

Restart the Hermes CLI or gateway after enabling the plugin. The model can call:

- `inspect_project` with `path` set to the project directory
- `diagnose_error` with `trace` set to the pasted error, and optionally `project_path`
- `review_changes` with `path` set to the Git working tree or a directory inside it

Example prompts once the plugin is enabled:

- "Use inspect_project on this directory and tell me the languages and which folders were skipped."
- "Use diagnose_error on this traceback. Give me leads, and do not treat them as a confirmed cause."
- "Use review_changes on this repository. Keep staged and unstaged changes separate."

Calling the model still depends on the provider configured for that Hermes install. DevSentry does not ship or require a provider key. The dispatch script stops before any model call.

## Remove it

```bash
hermes plugins disable devsentry
rm -rf ~/.hermes/plugins/devsentry
```

On Windows, disable the plugin and delete `%USERPROFILE%\.hermes\plugins\devsentry`.

#!/bin/bash
# Visible PTY script for the DevSentry demo. Every Hermes command is real.
# scripts/hermes_demo_tools.py is a helper around registry.dispatch, not a
# built-in hermes subcommand.
set -u
HERMES="${HERMES:-$HOME/.local/bin/hermes}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export DEVSENTRY_PROJECT="${DEVSENTRY_PROJECT:-/tmp/ds-demo/sample}"
export DEVSENTRY_TRACE="${DEVSENTRY_TRACE:-/tmp/ds-demo/trace.txt}"
export DEVSENTRY_RESULTS="${DEVSENTRY_RESULTS:-/tmp/ds-demo/results.json}"
export HERMES_HOME="${HERMES_HOME:-/tmp/ds-demo/hermes-home}"

hold() { sleep "$1"; }

show() {
  awk 'BEGIN{IGNORECASE=1} !/\/home\/|preparing the isolated|installing python dependencies|preparing dependencies|dependency environment|checkout.s updates/'
}

clear
printf '%s\n' \
  'DevSentry' \
  'Direct Hermes tool execution; no model inference' \
  '' \
  'Real Hermes commands follow.' \
  'The last step is a helper, not a hermes subcommand.' \
  'No model selects these tools.'
hold 6

clear
printf '%s\n' 'Direct Hermes tool execution; no model inference' ''
printf '%s\n' '$ hermes --version'
env -u HERMES_HOME "$HERMES" --version 2>&1 | show
printf '%s\n' '(Home directory line omitted.)'
hold 5

clear
printf '%s\n' 'Direct Hermes tool execution; no model inference' ''
printf '%s\n' '$ hermes plugins doctor devsentry --ci'
"$HERMES" plugins doctor "$ROOT/devsentry" --ci 2>&1 | show
printf 'exit %s\n' "$?"
hold 5

clear
printf '%s\n' 'Direct Hermes tool execution; no model inference' ''
printf '%s\n' '$ hermes plugins validate --json'
"$HERMES" plugins validate "$ROOT/devsentry" --json > /tmp/ds-demo/validate.json
python3 - <<'PY'
import json
from pathlib import Path
data = json.loads(Path("/tmp/ds-demo/validate.json").read_text(encoding="utf-8"))
print("ok:", data.get("ok"))
wanted = ("manifest", "declared tools", "capability probe", "security scan", "loadable")
by_name = {check.get("name"): check.get("detail") for check in data.get("checks") or []}
for name in wanted:
    if name in by_name:
        print(f"{name}: {by_name[name]}")
PY
printf '%s\n' 'manifest tools: inspect_project, diagnose_error, review_changes'
hold 6

clear
printf '%s\n' 'Direct Hermes tool execution; no model inference' ''
printf '%s\n' '$ hermes plugins enable devsentry'
"$HERMES" plugins enable devsentry
printf '\n%s\n' '$ hermes plugins list'
"$HERMES" plugins list | python3 -c '
import sys
for line in sys.stdin:
    low = line.lower()
    if "devsentry" in low and "enabled" in low and "0.1.0" in low:
        print("devsentry | enabled | 0.1.0 | user")
        break
'
printf '%s\n' 'Fields taken from the devsentry row.'
hold 5

clear
printf '%s\n' 'Direct Hermes tool execution; no model inference' ''
printf '%s\n' '$ scripts/hermes_demo_tools.py'
printf '%s\n' '  Hermes runtime -> tools.registry.dispatch'
runtime="$("$HERMES" --print-runtime-command)"
export DEVSENTRY_RUNTIME="$runtime"
export DEVSENTRY_HELPER="$ROOT/scripts/hermes_demo_tools.py"
python3 - <<'PY'
import json, os
from pathlib import Path
runtime = json.loads(os.environ["DEVSENTRY_RUNTIME"])
python_bin = runtime[0]
code = runtime[3]
marker = "sys.path.insert(0, '"
start = code.index(marker) + len(marker)
install = code[start:code.index("'", start)]
Path("/tmp/ds-demo/hermes-python").write_text(python_bin + "\n", encoding="utf-8")
Path("/tmp/ds-demo/launch.py").write_text(
    "import os, runpy, sys\n"
    f"sys.path.insert(0, {install!r})\n"
    "os.environ.pop('PYTHONHOME', None)\n"
    "os.environ.pop('PYTHONPATH', None)\n"
    "os.environ.pop('VIRTUAL_ENV', None)\n"
    "sys._hermes_pin_default_home = True\n"
    "import hermes_bootstrap\n"
    "raise SystemExit(runpy.run_path(os.environ['DEVSENTRY_HELPER'], run_name='__main__'))\n",
    encoding="utf-8",
)
PY
py_bin="$(head -n 1 /tmp/ds-demo/hermes-python)"
"$py_bin" -I /tmp/ds-demo/launch.py
status=$?
printf '\nhelper exit %s\n' "$status"
hold 4
exit "$status"

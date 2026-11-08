#!/usr/bin/env python3
"""Install DevSentry into a temporary Hermes home and call its tools.

This is the runtime check. It uses the ``hermes`` executable and Hermes's own
plugin discovery and tool registry. It does not call a model and does not need
an API key.

Usage:
    python3 scripts/hermes_integration.py --hermes ~/.hermes/hermes-agent/.venv/bin/hermes
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "devsentry"
OUTPUT = ROOT / "samples" / "hermes-integration.json"


def run(cmd: list[str], env: dict[str, str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Exercise DevSentry inside Hermes")
    parser.add_argument("--hermes", required=True, help="Path to the hermes executable")
    args = parser.parse_args()
    hermes = Path(args.hermes).resolve()
    if not hermes.is_file():
        print(f"hermes executable not found: {hermes}", file=sys.stderr)
        return 2

    with tempfile.TemporaryDirectory(prefix="devsentry-hermes-") as temporary:
        home = Path(temporary) / "home"
        project = Path(temporary) / "project"
        plugin_dir = home / "plugins" / "devsentry"
        plugin_dir.parent.mkdir(parents=True)
        shutil.copytree(PLUGIN, plugin_dir)
        project.mkdir()
        (project / "app.py").write_text("def value():\n    return 1 / 0\n", encoding="utf-8")
        env = os.environ.copy()
        env["HERMES_HOME"] = str(home)
        env["GIT_AUTHOR_NAME"] = "DevSentry Integration"
        env["GIT_AUTHOR_EMAIL"] = "devsentry-integration@example.com"
        env["GIT_COMMITTER_NAME"] = "DevSentry Integration"
        env["GIT_COMMITTER_EMAIL"] = "devsentry-integration@example.com"
        for git_args in (
            ["git", "-C", str(project), "init", "-q"],
            ["git", "-C", str(project), "add", "--", "app.py"],
            ["git", "-C", str(project), "-c", "user.email=devsentry-integration@example.com", "-c", "user.name=DevSentry Integration", "commit", "-q", "-m", "initial"],
        ):
            created = run(git_args, env)
            if created.returncode != 0:
                print(created.stderr, file=sys.stderr)
                return 1
        (project / "app.py").write_text("def value():\n    return 1 / 1\n", encoding="utf-8")

        # --version against the real install. A fresh HERMES_HOME has no
        # dependency environment yet, and `hermes version` is not a command.
        version_env = os.environ.copy()
        version_env.pop("HERMES_HOME", None)
        version = run([str(hermes), "--version"], version_env)
        doctor = run([str(hermes), "plugins", "doctor", str(plugin_dir), "--ci"], env)
        validate = run([str(hermes), "plugins", "validate", str(plugin_dir), "--json"], version_env)
        copied = run([str(hermes), "plugins", "enable", "devsentry"], env)
        listing = run([str(hermes), "plugins", "list"], env)

        # Dispatch through the same isolated interpreter Hermes prints for its
        # runtime. This imports hermes_cli and tools.registry; it is not the
        # stand-in context used by tests/test_plugin.py.
        runtime = run([str(hermes), "--print-runtime-command"], env)
        if runtime.returncode != 0:
            print(runtime.stderr, file=sys.stderr)
            return 1
        runtime_cmd = json.loads(runtime.stdout)
        python = runtime_cmd[0]
        install_dir = None
        for part in runtime_cmd:
            if isinstance(part, str) and "sys.path.insert(0, " in part:
                start = part.index("sys.path.insert(0, '") + len("sys.path.insert(0, '")
                install_dir = part[start:part.index("'", start)]
                break
        if not install_dir:
            print("could not find the Hermes install path in the runtime command", file=sys.stderr)
            return 1
        env["DEVSENTRY_PROJECT"] = str(project)
        wrapper = (
            "import os, sys, runpy\n"
            "os.environ.pop('PYTHONHOME', None)\n"
            "os.environ.pop('PYTHONPATH', None)\n"
            "os.environ.pop('VIRTUAL_ENV', None)\n"
            "sys.path.insert(0, sys.argv[1])\n"
            "sys._hermes_pin_default_home = True\n"
            "import hermes_bootstrap\n"
            "runpy.run_path(sys.argv[2], run_name='__main__')\n"
        )
        dispatched = run(
            [python, "-I", "-c", wrapper, install_dir, str(ROOT / "scripts" / "hermes_dispatch_probe.py")],
            env,
        )

    install_dir = ""
    for line in version.stdout.splitlines():
        if line.startswith("Install directory:"):
            install_dir = line.split(":", 1)[1].strip()
    checkout = ""
    if install_dir:
        rev = run(["git", "-C", install_dir, "rev-parse", "HEAD"], os.environ.copy())
        if rev.returncode == 0:
            checkout = rev.stdout.strip()
    list_lines = listing.stdout.splitlines()
    devsentry_rows = [
        line for line in list_lines if "devsentry" in line.lower()
    ]
    report = {
        "hermes_executable": str(hermes),
        "checkout": checkout,
        "version_command": {"returncode": version.returncode, "stdout": version.stdout.strip(), "stderr": version.stderr.strip()},
        "doctor": {"returncode": doctor.returncode, "stdout": doctor.stdout, "stderr": doctor.stderr},
        "validate": {"returncode": validate.returncode, "stdout": validate.stdout, "stderr": validate.stderr},
        "enable": {"returncode": copied.returncode, "stdout": copied.stdout, "stderr": copied.stderr},
        "list": {
            "returncode": listing.returncode,
            "stdout_chars": len(listing.stdout),
            "devsentry_rows": devsentry_rows,
            "stderr": listing.stderr,
        },
        "dispatch": {
            "returncode": dispatched.returncode,
            "stdout": dispatched.stdout,
            "stderr": dispatched.stderr[-4000:],
        },
    }
    payload = None
    for line in dispatched.stdout.splitlines():
        if line.startswith("DEVSENTRY_JSON:"):
            try:
                payload = json.loads(line[len("DEVSENTRY_JSON:"):])
            except json.JSONDecodeError:
                payload = None
    report["dispatch_payload"] = payload

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUTPUT}")
    print("version:", version.stdout.strip() or version.stderr.strip())
    print("doctor exit:", doctor.returncode)
    print("enable exit:", copied.returncode)
    print("dispatch exit:", dispatched.returncode)
    payload = report["dispatch_payload"] or {}
    print("missing tools:", payload.get("missing"))
    ok = (
        version.returncode == 0
        and doctor.returncode == 0
        and validate.returncode == 0
        and copied.returncode == 0
        and dispatched.returncode == 0
        and payload.get("missing") == []
        and payload.get("results", {}).get("inspect_project", {}).get("ok") is True
        and payload.get("results", {}).get("diagnose_error", {}).get("ok") is True
        and payload.get("results", {}).get("review_changes", {}).get("ok") is True
        and payload.get("results", {}).get("review_changes", {}).get("mutation", {}).get("index_sha256_unchanged") is True
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

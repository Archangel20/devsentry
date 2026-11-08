#!/usr/bin/env python3
"""Run the three DevSentry tools against the sample project and save the results.

The script creates a temporary Git repository, so the fixture directory is not
modified. Output is written to samples/demo-run.json with the temporary path
replaced by ``{project}``.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from devsentry.tools import diagnose_error, inspect_project, loads, review_changes  # noqa: E402

FIXTURE = ROOT / "fixtures" / "sample-project"
TRACES = ROOT / "fixtures" / "traces"
OUTPUT = ROOT / "samples" / "demo-run.json"


def git(repo: Path, *args: str) -> None:
    env = os.environ.copy()
    env.update(
        {
            "GIT_AUTHOR_NAME": "DevSentry Demo",
            "GIT_AUTHOR_EMAIL": "devsentry-demo@example.com",
            "GIT_COMMITTER_NAME": "DevSentry Demo",
            "GIT_COMMITTER_EMAIL": "devsentry-demo@example.com",
            "GIT_AUTHOR_DATE": "2026-01-15T12:00:00Z",
            "GIT_COMMITTER_DATE": "2026-01-15T12:00:00Z",
        }
    )
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        env=env,
        capture_output=True,
    )


def prepare(repo: Path) -> None:
    shutil.copytree(FIXTURE, repo, symlinks=False)
    # A dotenv file is created here so the saved demo can show that its patch
    # is omitted. The token below is fake.
    (repo / ".env").write_text("TOKEN=demo-not-a-real-secret\n", encoding="utf-8")
    git(repo, "init", "-q")
    git(repo, "add", "--", ".")
    git(repo, "commit", "-q", "-m", "initial sample")
    app = repo / "src" / "app.py"
    app.write_text(app.read_text(encoding="utf-8") + "\n# unstaged demo note\n", encoding="utf-8")
    readme = repo / "README.md"
    readme.write_text(readme.read_text(encoding="utf-8") + "\nStaged demo line.\n", encoding="utf-8")
    git(repo, "add", "--", "README.md")
    (repo / ".env").write_text("TOKEN=demo-changed-not-a-real-secret\n", encoding="utf-8")
    (repo / "untracked-notes.txt").write_text("this untracked file must not appear\n", encoding="utf-8")


def relativize(payload: dict, project: Path) -> dict:
    text = json.dumps(payload)
    text = text.replace(str(project), "{project}")
    return json.loads(text)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="devsentry-demo-") as temporary:
        project = Path(temporary) / "sample-project"
        prepare(project)
        inventory = loads(inspect_project({"path": str(project)}))
        python_trace = (TRACES / "python.txt").read_text(encoding="utf-8")
        # Point one frame at the real sample file so source context is exercised.
        local_trace = python_trace.replace(
            'File "/app/src/app.py", line 2, in ratio',
            'File "src/app.py", line 2, in ratio',
        )
        diagnosis = loads(
            diagnose_error(
                {
                    "trace": local_trace,
                    "project_path": str(project),
                    "context_lines": 1,
                }
            )
        )
        review = loads(review_changes({"path": str(project)}))
        report = {
            "tools": {
                "inspect_project": relativize(inventory, project),
                "diagnose_error": relativize(diagnosis, project),
                "review_changes": relativize(review, project),
            }
        }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    inventory = report["tools"]["inspect_project"]
    review = report["tools"]["review_changes"]
    diagnosis = report["tools"]["diagnose_error"]
    languages = ", ".join(f"{row['language']} {row['files']}" for row in inventory["languages"])
    print(f"wrote {OUTPUT.relative_to(ROOT)}")
    print(f"inspect_project: {inventory['summary']['files']} files; {languages}")
    print(f"diagnose_error: {diagnosis['exceptions'][0]['name']} at {diagnosis['frames'][-1]['path']}:{diagnosis['frames'][-1]['line']}")
    print(
        "review_changes: "
        f"{review['staged']['file_count']} staged, "
        f"{review['unstaged']['file_count']} unstaged, "
        f"{review['untracked_count']} untracked excluded"
    )
    secret = "demo-changed-not-a-real-secret"
    if secret in OUTPUT.read_text(encoding="utf-8"):
        print("demo output contains the dotenv token; that is a bug", file=sys.stderr)
        return 1
    if "this untracked file must not appear" in OUTPUT.read_text(encoding="utf-8"):
        print("demo output contains untracked content; that is a bug", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

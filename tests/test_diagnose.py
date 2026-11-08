"""Trace parsing tests. These call the tool functions directly, without Hermes."""

from __future__ import annotations

import json
from pathlib import Path

from devsentry.diagnose import DISCLAIMER
from devsentry.tools import diagnose_error, loads

TRACES = Path(__file__).resolve().parents[1] / "fixtures" / "traces"


def _trace(name: str) -> dict:
    return loads(diagnose_error({"trace": (TRACES / name).read_text(encoding="utf-8")}))


def test_python_trace_extracts_exception_frames_and_leads():
    result = _trace("python.txt")
    assert result["ok"] is True
    assert result["certainty"] == "leads_only"
    assert result["disclaimer"] == DISCLAIMER
    assert "not a confirmed root cause" in result["disclaimer"]
    assert "root_cause" not in result
    names = [item["name"] for item in result["exceptions"]]
    assert names == ["ZeroDivisionError"]
    assert result["frames"][0]["path"] == "/app/src/app.py"
    assert result["frames"][0]["line"] == 5
    assert result["frames"][0]["function"] == "main"
    assert result["frames"][1]["line"] == 2
    assert result["frames"][1]["function"] == "ratio"
    assert any("divisor" in lead for lead in result["leads"])
    blob = json.dumps(result).lower()
    assert "the root cause is" not in blob
    assert "guaranteed" not in blob


def test_javascript_java_go_rust_and_dotnet_traces():
    js = _trace("javascript.txt")
    assert js["exceptions"][0]["name"] == "TypeError"
    assert js["frames"][0]["path"] == "/app/src/util.js"
    assert js["frames"][0]["line"] == 2
    assert js["frames"][0]["column"] == 15
    assert js["frames"][0]["function"] == "readName"
    assert any("undefined" in lead.lower() or "null" in lead.lower() for lead in js["leads"])

    java = _trace("java.txt")
    assert [item["name"] for item in java["exceptions"]] == [
        "java.lang.NullPointerException",
        "java.lang.IllegalStateException",
    ]
    assert java["frames"][0]["path"] == "App.java"
    assert java["frames"][0]["line"] == 14
    assert java["frames"][1]["line"] == 9

    go = _trace("go.txt")
    assert go["exceptions"][0]["name"] == "panic"
    assert "nil pointer" in go["exceptions"][0]["message"]
    assert go["frames"][0]["path"] == "/tmp/main.go"
    assert go["frames"][0]["line"] == 10
    assert go["frames"][0]["function"] == "main.main()"

    rust = _trace("rust.txt")
    assert rust["exceptions"][0]["name"] == "panic"
    assert rust["frames"][0]["path"] == "src/main.rs"
    assert rust["frames"][0]["line"] == 5
    assert rust["frames"][0]["column"] == 5

    dotnet = _trace("dotnet.txt")
    assert dotnet["exceptions"][0]["name"] == "System.NullReferenceException"
    assert dotnet["frames"][0]["path"] == r"C:\src\Program.cs"
    assert dotnet["frames"][0]["line"] == 12
    assert dotnet["frames"][0]["function"] == "App.Program.Main()"

    rustc = _trace("rustc.txt")
    assert rustc["exceptions"][0]["name"] == "error"
    assert "E0382" in rustc["exceptions"][0]["message"]
    assert rustc["frames"][0]["path"] == "src/main.rs"
    assert rustc["frames"][0]["line"] == 4


def test_unrecognized_text_does_not_invent_a_frame():
    result = loads(diagnose_error({"trace": "build finished in 3s"}))
    assert result["ok"] is True
    assert result["parsed"] is False
    assert result["exceptions"] == []
    assert result["frames"] == []
    assert result["disclaimer"] == DISCLAIMER
    assert "build finished" in result["excerpt"]


def test_empty_and_hostile_trace_inputs():
    assert loads(diagnose_error({"trace": "  "}))["error"]["code"] == "invalid_argument"
    assert loads(diagnose_error({}))["error"]["code"] == "invalid_argument"
    assert loads(diagnose_error({"trace": "boom\x00"}))["error"]["code"] == "invalid_argument"
    huge = "noise\n" * 80_000 + "ValueError: too many\n"
    result = loads(diagnose_error({"trace": huge}))
    assert result["input_truncated"] is True
    assert result["exceptions"][0]["name"] == "ValueError"


def test_source_context_stays_inside_the_project(tmp_path: Path):
    project = tmp_path / "proj"
    source = project / "src"
    source.mkdir(parents=True)
    app = source / "app.py"
    app.write_text(
        "def ratio(numerator, denominator):\n    return numerator / denominator\n",
        encoding="utf-8",
    )
    outside = tmp_path / "outside.py"
    outside.write_text("OUTSIDE_SECRET = 'nope'\n", encoding="utf-8")
    (project / ".env").write_text("SUPER_SECRET_TOKEN=abc\n", encoding="utf-8")
    linked = source / "linked.py"
    linked.symlink_to(outside)

    trace = "\n".join(
        [
            "Traceback (most recent call last):",
            f'  File "{app}", line 2, in ratio',
            "    return numerator / denominator",
            f'  File "{outside}", line 1, in <module>',
            "    OUTSIDE_SECRET",
            '  File "src/linked.py", line 1, in <module>',
            "    pass",
            '  File ".env", line 1, in <module>',
            "    pass",
            '  File "../outside.py", line 1, in <module>',
            "    pass",
            "ZeroDivisionError: division by zero",
        ]
    )
    result = loads(diagnose_error({"trace": trace, "project_path": str(project), "context_lines": 1}))
    blob = json.dumps(result)
    assert "return numerator / denominator" in blob
    assert "OUTSIDE_SECRET" not in blob
    assert "SUPER_SECRET_TOKEN" not in blob
    reasons = [frame["context"]["reason"] for frame in result["frames"] if frame["context"].get("omitted")]
    assert "outside_project" in reasons
    assert "symlink" in reasons
    assert "sensitive_path" in reasons
    cited = next(frame for frame in result["frames"] if frame["path"] == str(app))
    assert cited["context"]["omitted"] is False
    assert any(row.get("cited") and "denominator" in row["text"] for row in cited["context"]["snippet"])


def test_bad_project_path_still_returns_the_parse(tmp_path: Path):
    result = loads(
        diagnose_error(
            {
                "trace": "KeyError: 'missing'\n",
                "project_path": str(tmp_path / "missing"),
            }
        )
    )
    assert result["ok"] is True
    assert result["exceptions"][0]["name"] == "KeyError"
    assert result["project_path"]["ok"] is False
    assert result["project_path"]["error"]["code"] == "not_found"

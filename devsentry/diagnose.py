"""Parse pasted traces into exception names, frames, and debugging leads.

The leads are hints a person can verify. Nothing in this module decides that a
cause has been confirmed, and nothing here executes the pasted project.
"""

from __future__ import annotations

import re
from pathlib import Path

from .safety import MAX_SOURCE_BYTES, read_bounded_text, resolve_inside_project

DISCLAIMER = (
    "These are explainable debugging leads for a person to verify. "
    "They are not a confirmed root cause, and this tool does not claim one."
)

MAX_TRACE_CHARS = 200_000
MAX_FRAMES = 50
MAX_EXCEPTIONS = 20
MAX_CONTEXT_FRAMES = 5
MAX_LINE_CHARS = 200

_PY_FRAME = re.compile(
    r'^\s*File "(?P<path>.*)", line (?P<line>\d+)(?:, in (?P<func>.*))?$'
)
_JS_FRAME = re.compile(
    r"^\s*at (?:(?P<func>.+?) \()?(?P<path>.+):(?P<line>\d+):(?P<col>\d+)\)?\s*$"
)
_JAVA_FRAME = re.compile(
    r"^\s*at (?P<func>[\w.$/<>]+)\((?P<path>[^():]+):(?P<line>\d+)\)\s*$"
)
_DOTNET_FRAME = re.compile(
    r"^\s*at (?P<func>.+?) in (?P<path>.+):line (?P<line>\d+)\s*$"
)
_GO_FRAME = re.compile(
    r"^(?P<path>.+\.go):(?P<line>\d+)(?: \+0x[0-9a-fA-F]+)?$"
)
_RUST_OLD = re.compile(
    r"panicked at '(?P<message>(?:\\'|[^'])*)', (?P<path>[^:\n]+):(?P<line>\d+):(?P<col>\d+)"
)
_RUST_NEW = re.compile(
    r"panicked at (?P<path>[^:'\n]+):(?P<line>\d+):(?P<col>\d+)"
)
_RUSTC_ERROR = re.compile(
    r"^(?P<name>error|warning)(?:\[(?P<code>E\d+)\])?: (?P<message>.*)$"
)
_RUSTC_LOC = re.compile(
    r"^\s*--> (?P<path>[^:\n]+):(?P<line>\d+):(?P<col>\d+)\s*$"
)
_JAVA_EXC = re.compile(
    r'^(?:Exception in thread "[^"]+" )?(?:Caused by: )?'
    r"(?P<name>(?:[\w$]+\.)+[\w$]+(?:Exception|Error))(?:: (?P<message>.*))?$"
)
_GENERIC_EXC = re.compile(
    r"^(?P<name>(?:[\w]+\.)*[A-Za-z_][\w]*(?:Error|Exception|Interrupt|Exit|Warning))"
    r"(?:: ?(?P<message>.*))?$"
)
_PANIC_LINE = re.compile(r"^panic: (?P<message>.*)$")

_LEADS = {
    "ZeroDivisionError": (
        "Check the divisor at the cited line, including a value returned by an earlier call. "
        "Confirm it cannot be zero for this input."
    ),
    "KeyError": (
        "The mapping did not contain the reported key. Compare that key with the keys actually "
        "present, including spelling and nested structure."
    ),
    "IndexError": (
        "An index was outside the sequence. Check the length before the access and whether the sequence was empty."
    ),
    "TypeError": (
        "An operation received an unexpected type. In Python this is often None. In JavaScript the "
        "message often names undefined or null. Inspect the value at the cited call."
    ),
    "AttributeError": (
        "The receiver may be None or a different type than the code expects. Check the object at "
        "the cited line before the attribute is used."
    ),
    "NameError": "A name is not defined on this path. Check spelling, imports, and assignments that may have been skipped.",
    "UnboundLocalError": (
        "A local name was read before assignment. An assignment later in the function makes that name local for the whole function."
    ),
    "ImportError": "An import failed. Check that the module is installed in this environment and that the import path matches the package layout.",
    "ModuleNotFoundError": (
        "Python could not find the module. Check the active environment, the package name, and whether the project root is on the import path."
    ),
    "FileNotFoundError": (
        "The path was not found. Check whether it is relative to the process working directory and whether the file exists there."
    ),
    "FileNotFoundException": "The path was not found. Check the working directory and the path string at the cited frame.",
    "PermissionError": "The process was denied access. Check filesystem permissions and whether a directory was used as a file.",
    "IsADirectoryError": "A directory was used where a file was required.",
    "NotADirectoryError": "A file was used where a directory was required.",
    "SyntaxError": "The cited line may not be valid syntax. Use the message, and the caret when one is present, to locate the token.",
    "IndentationError": "The cited line may mix indentation or not match the surrounding block.",
    "TabError": "Tabs and spaces may be mixed in the indentation around the cited line.",
    "AssertionError": "An assertion failed. Read the expression at the cited line and the inputs that reached it.",
    "ValueError": "A value had an acceptable type but was not acceptable to the operation. Read the message together with the cited call.",
    "JSONDecodeError": "The input was not valid JSON. The message usually includes a position to inspect.",
    "UnicodeDecodeError": "Bytes could not be decoded with the chosen encoding. Check whether the data is binary or uses another encoding.",
    "RecursionError": "Recursion exceeded the limit. Look for a call that never reaches its base case.",
    "StopIteration": "Iteration ended unexpectedly. Check a next() call or a generator that does not yield.",
    "RuntimeError": "A runtime check failed. Treat the message as the specific lead and inspect the cited frame.",
    "OSError": "An operating-system call failed. Use the message at the cited frame as the lead.",
    "ConnectionError": "A network operation failed. This tool did not retry it. Check the endpoint and whether the service was running.",
    "TimeoutError": "An operation timed out. This tool did not retry it. Check the timeout and whether the peer responded.",
    "MemoryError": "The process ran out of memory. Look for an unbounded read or a structure that grows with the input.",
    "OverflowError": "A numeric result was too large for the operation. Check the operands at the cited line.",
    "NotImplementedError": "Execution reached a method that is not implemented. Check which subclass or branch was used.",
    "KeyboardInterrupt": "Execution was interrupted. That is a signal rather than a fault in the cited expression by itself.",
    "SystemExit": "The process requested an exit. Check the exit code in the message and the call that raised it.",
    "ReferenceError": "JavaScript evaluated a name that is not defined in this scope. Check spelling and imports.",
    "RangeError": "A number was outside the range JavaScript allows. Check the value at the cited call.",
    "NullPointerException": "A null reference was used. Check the receiver at the cited frame and where it should have been assigned.",
    "IllegalArgumentException": "A method rejected an argument. Compare the argument at the cited frame with the method's requirements.",
    "IllegalStateException": "An object was used in a state the method does not allow. Check the calls that led to the cited frame.",
    "IndexOutOfBoundsException": "An index was outside the collection. Check the size before the access.",
    "ClassCastException": "An object was cast to a type it does not have. Check the value's runtime type at the cited frame.",
    "NullReferenceException": "A null reference was used. Check the object at the cited line and the assignment that should have set it.",
    "panic": "A panic stopped the goroutine or Rust thread. Read the panic message against the cited file and line.",
    "error": "The compiler reported an error at the cited location. Read the error code and message against that line.",
}


def _short_name(name: str) -> str:
    return name.rsplit(".", 1)[-1]


def _lead_for(name: str, message: str) -> str:
    short = _short_name(name)
    specific = _LEADS.get(short) or _LEADS.get(name)
    extra = ""
    lowered = message.lower()
    if short == "TypeError" and any(token in lowered for token in ("undefined", "null", "nonetype")):
        extra = " The message mentions undefined, null, or None, so find where that empty value is produced before the cited call."
    if specific:
        return specific + extra
    if message:
        return f"The trace names {name}. Compare its message with the last cited frame and the inputs there."
    return f"The trace names {name}. Inspect the last cited frame and the inputs that reached it."


def _frame(style: str, path: str, line: str, function: str | None = None, column: str | None = None) -> dict:
    item = {"style": style, "path": path.strip(), "line": int(line)}
    if column is not None:
        item["column"] = int(column)
    if function:
        item["function"] = function.strip()
    return item


def _exception(style: str, name: str, message: str | None) -> dict:
    item = {"style": style, "name": name.strip()}
    if message:
        item["message"] = message.strip()
    return item


def parse_trace(text: str) -> dict:
    """Extract structured frames and exception names from ``text``."""
    truncated_input = False
    if len(text) > MAX_TRACE_CHARS:
        text = text[-MAX_TRACE_CHARS:]
        truncated_input = True

    frames: list[dict] = []
    exceptions: list[dict] = []
    frames_truncated = False
    exceptions_truncated = False
    previous_code = ""

    def add_frame(item: dict) -> None:
        nonlocal frames_truncated
        if len(frames) >= MAX_FRAMES:
            frames_truncated = True
            return
        frames.append(item)

    def add_exception(item: dict) -> None:
        nonlocal exceptions_truncated
        if len(exceptions) >= MAX_EXCEPTIONS:
            exceptions_truncated = True
            return
        exceptions.append(item)

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("Traceback (most recent call last):"):
            continue
        if stripped.startswith(("During handling of the above exception", "The above exception was the direct cause")):
            continue

        rust_old = _RUST_OLD.search(stripped)
        if rust_old:
            add_exception(_exception("rust", "panic", rust_old.group("message")))
            add_frame(_frame("rust", rust_old.group("path"), rust_old.group("line"), column=rust_old.group("col")))
            previous_code = ""
            continue
        rust_new = _RUST_NEW.search(stripped)
        if rust_new:
            add_exception(_exception("rust", "panic", ""))
            add_frame(_frame("rust", rust_new.group("path"), rust_new.group("line"), column=rust_new.group("col")))
            previous_code = ""
            continue

        py = _PY_FRAME.match(line)
        if py:
            add_frame(_frame("python", py.group("path"), py.group("line"), py.group("func")))
            previous_code = ""
            continue

        dotnet = _DOTNET_FRAME.match(line)
        if dotnet:
            add_frame(_frame("dotnet", dotnet.group("path"), dotnet.group("line"), dotnet.group("func")))
            previous_code = ""
            continue

        java = _JAVA_FRAME.match(line)
        if java and ":line " not in stripped:
            add_frame(_frame("java", java.group("path"), java.group("line"), java.group("func")))
            previous_code = ""
            continue

        js = _JS_FRAME.match(line)
        if js and stripped.startswith("at "):
            add_frame(_frame("javascript", js.group("path"), js.group("line"), js.group("func"), js.group("col")))
            previous_code = ""
            continue

        go = _GO_FRAME.match(stripped)
        if go:
            function = previous_code if previous_code.endswith("()") else None
            add_frame(_frame("go", go.group("path"), go.group("line"), function))
            previous_code = ""
            continue

        rustc_loc = _RUSTC_LOC.match(line)
        if rustc_loc:
            add_frame(_frame("rustc", rustc_loc.group("path"), rustc_loc.group("line"), column=rustc_loc.group("col")))
            previous_code = ""
            continue

        panic = _PANIC_LINE.match(stripped)
        if panic:
            add_exception(_exception("go", "panic", panic.group("message")))
            previous_code = ""
            continue

        rustc = _RUSTC_ERROR.match(stripped)
        if rustc:
            code = rustc.group("code")
            message = rustc.group("message")
            if code:
                message = f"{code}: {message}"
            add_exception(_exception("rustc", rustc.group("name"), message))
            previous_code = ""
            continue

        java_exc = _JAVA_EXC.match(stripped)
        if java_exc:
            name = java_exc.group("name")
            style = "java"
            if name.startswith("System."):
                style = "dotnet"
            add_exception(_exception(style, name, java_exc.group("message")))
            previous_code = ""
            continue

        generic = _GENERIC_EXC.match(stripped)
        if generic and not stripped.startswith(("File ", "at ")):
            name = generic.group("name")
            style = "dotnet" if name.startswith("System.") else "generic"
            add_exception(_exception(style, name, generic.group("message")))
            previous_code = ""
            continue

        if stripped.endswith("()") and " " not in stripped:
            previous_code = stripped
        else:
            previous_code = ""

    # A Rust "panicked at file:line" match also records an empty message. Drop
    # empty duplicates that sit next to a panic which already has a message.
    cleaned: list[dict] = []
    for item in exceptions:
        if item["name"] == "panic" and not item.get("message") and any(
            other["name"] == "panic" and other.get("message") for other in exceptions
        ):
            continue
        if item not in cleaned:
            cleaned.append(item)

    leads: list[str] = []
    seen: set[str] = set()
    for item in cleaned:
        lead = _lead_for(item["name"], item.get("message", ""))
        if lead not in seen:
            seen.add(lead)
            leads.append(lead)
    parsed = bool(cleaned or frames)
    if not parsed:
        leads.append(
            "No exception name or stack frame matched the Python, JavaScript, Java, Go, "
            "Rust, or .NET patterns this tool knows. The text may be a log line or another format."
        )

    return {
        "parsed": parsed,
        "input_truncated": truncated_input,
        "exceptions": cleaned,
        "frames": frames,
        "frames_truncated": frames_truncated,
        "exceptions_truncated": exceptions_truncated,
        "leads": leads,
        "disclaimer": DISCLAIMER,
        "certainty": "leads_only",
    }


def _snippet(path: Path, line_number: int, context: int) -> dict:
    if path.stat().st_size > MAX_SOURCE_BYTES:
        return {"omitted": True, "reason": "file_too_large"}
    text = read_bounded_text(path)
    if text is None:
        return {"omitted": True, "reason": "file_too_large"}
    lines = text.splitlines()
    if line_number > len(lines):
        return {"omitted": True, "reason": "line_not_in_file", "file_lines": len(lines)}
    start = max(1, line_number - context)
    end = min(len(lines), line_number + context)
    snippet = []
    for number in range(start, end + 1):
        text_line = lines[number - 1]
        if len(text_line) > MAX_LINE_CHARS:
            text_line = text_line[:MAX_LINE_CHARS]
        row = {"line": number, "text": text_line}
        if number == line_number:
            row["cited"] = True
        snippet.append(row)
    return {"omitted": False, "snippet": snippet}


def attach_source_context(parsed: dict, project: Path, *, context_lines: int) -> dict:
    """Add a few source lines for frames that stay inside ``project``."""
    attached = 0
    for frame in parsed["frames"]:
        if attached >= MAX_CONTEXT_FRAMES:
            frame["context"] = {"omitted": True, "reason": "context_limit"}
            continue
        located = resolve_inside_project(project, frame["path"])
        if isinstance(located, str):
            frame["context"] = {"omitted": True, "reason": located}
            continue
        frame["context"] = _snippet(located, frame["line"], context_lines)
        if not frame["context"].get("omitted"):
            attached += 1
    return parsed

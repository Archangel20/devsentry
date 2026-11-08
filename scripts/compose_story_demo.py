#!/usr/bin/env python3
"""Cut one real terminal recording into a 1080p story.

Title cards are drawn here. They are illustrated. The terminal pictures are
frames from the PTY recording, not a mock interface.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

WIDTH = 1920
HEIGHT = 1080
BAR = 96
SANS = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
SANS_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

# Illustrated cards. Durations keep the finished film under 90 seconds.
CARDS = [
    ("card-open", 4.6, "A sample call divides by zero.", ["The program stops before it can print a result."]),
    ("card-orient", 3.4, "What is in the tree?", ["inspect_project counts files.", "It does not open or run them."]),
    ("card-trace", 3.6, "Where does the traceback land?", ["The cited line is the division.", "The result is a lead, not a confirmed cause."]),
    ("card-edit", 3.8, "The developer changes the call.", ["This edit is manual.", "DevSentry does not write it."]),
    ("card-diff", 3.4, "Staged note. Unstaged fix.", ["review_changes reads those scopes apart.", "It does not stage or unstage."]),
    ("card-end", 6.4, "Cited line. Unstaged call. Staged note.", ["The traceback names the return.", "The developer changed the call. The index was not touched."]),
]
SEGMENTS = [
    ("crash", "card-open", 8.8),
    ("inspect", "card-orient", 8.4),
    ("diagnose", "card-trace", 9.2),
    ("fixed", "card-edit", 9.4),
    ("review", "card-diff", 9.0),
]


def font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size)


def draw_card(path: Path, title: str, lines: list[str]) -> None:
    image = Image.new("RGB", (WIDTH, HEIGHT), "#10141a")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 14, HEIGHT), fill="#d7b15e")
    eyebrow = font(SANS_BOLD, 28)
    title_font = font(SANS_BOLD, 64)
    body = font(SANS, 36)
    draw.text((96, 300), "Direct tool demo  ·  no model inference", fill="#d7b15e", font=eyebrow)
    draw.text((96, 390), title, fill="#f7f4ec", font=title_font)
    y = 510
    for line in lines:
        draw.text((96, y), line, fill="#c8c2b4", font=body)
        y += 56
    image.save(path)


def draw_bar(path: Path) -> None:
    image = Image.new("RGBA", (WIDTH, BAR), (16, 20, 26, 255))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, BAR - 3, WIDTH, BAR), fill="#d7b15e")
    label = "Direct tool demo  ·  no model inference"
    face = font(SANS_BOLD, 28)
    draw.text((36, 30), label, fill="#f4efe4", font=face)
    image.save(path)


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def main() -> int:
    if len(sys.argv) != 4:
        print("usage: compose_story_demo.py capture.mp4 marks.txt out.mp4", file=sys.stderr)
        return 2
    capture = Path(sys.argv[1])
    marks_path = Path(sys.argv[2])
    out = Path(sys.argv[3])
    work = out.parent / "story-build"
    work.mkdir(parents=True, exist_ok=True)
    marks = {}
    # Marks are absolute timestamps. capture_t0.txt is when the screen grab started.
    origin = float(marks_path.with_name("capture_t0.txt").read_text(encoding="utf-8").strip())
    for line in marks_path.read_text(encoding="utf-8").splitlines():
        name, stamp = line.split()
        marks[name] = float(stamp) - origin
    draw_bar(work / "bar.png")
    for name, _duration, title, lines in CARDS:
        draw_card(work / f"{name}.png", title, lines)
    interleaved = []
    for (seg_name, card_name, duration), card in zip(SEGMENTS, CARDS):
        interleaved.append(("card", card[0], card[1]))
        interleaved.append(("term", seg_name, duration))
    interleaved.append(("card", CARDS[-1][0], CARDS[-1][1]))

    inputs = []
    filters = []
    index = 0
    for kind, name, duration in interleaved:
        if kind == "card":
            inputs.extend(["-loop", "1", "-t", f"{duration:.3f}", "-i", str(work / f"{name}.png")])
            filters.append(
                f"[{index}:v]scale={WIDTH}:{HEIGHT},fps=30,format=yuv420p,setsar=1[v{index}]"
            )
        else:
            start = marks[name] + 0.35
            inputs.extend(["-ss", f"{start:.3f}", "-t", f"{duration:.3f}", "-i", str(capture)])
            filters.append(
                f"[{index}:v]scale={WIDTH}:{HEIGHT - BAR - 24}:force_original_aspect_ratio=decrease,"
                f"pad={WIDTH}:{HEIGHT}:(ow-iw)/2:{BAR + 12}:black,fps=30,format=yuv420p,setsar=1[scaled{index}];"
                f"[scaled{index}][{index + 1}:v]overlay=0:0[v{index}]"
            )
            # bar is a separate input inserted after this clip
            inputs.extend(["-i", str(work / "bar.png")])
            index += 1  # account for bar input; clip index is index-1
            # The filter above used index before increment incorrectly.
            # Rebuild below instead of this fragile loop.
            inputs = []
            filters = []
            break
        index += 1
    # Clear partial construction and build filters carefully.
    inputs = []
    filters = []
    labels = []
    cursor = 0
    for kind, name, duration in interleaved:
        if kind == "card":
            inputs.extend(["-loop", "1", "-t", f"{duration:.3f}", "-i", str(work / f"{name}.png")])
            filters.append(f"[{cursor}:v]scale={WIDTH}:{HEIGHT},fps=30,format=yuv420p,setsar=1[v{cursor}]")
            labels.append(f"[v{cursor}]")
            cursor += 1
            continue
        start = marks[name] + 0.35
        inputs.extend(["-ss", f"{start:.3f}", "-t", f"{duration:.3f}", "-i", str(capture)])
        clip = cursor
        cursor += 1
        inputs.extend(["-i", str(work / "bar.png")])
        bar = cursor
        cursor += 1
        filters.append(
            f"[{clip}:v]scale={WIDTH}:{HEIGHT - BAR - 20}:force_original_aspect_ratio=decrease,"
            f"pad={WIDTH}:{HEIGHT}:(ow-iw)/2:{BAR + 8}:color=black,fps=30,format=yuv420p,setsar=1[scaled{clip}];"
            f"[scaled{clip}][{bar}:v]overlay=0:0:format=auto[v{clip}]"
        )
        labels.append(f"[v{clip}]")
    count = len(labels)
    filters.append("".join(labels) + f"concat=n={count}:v=1:a=0[out]")
    run([
        "ffmpeg", "-y", "-loglevel", "error",
        *inputs,
        "-filter_complex", ";".join(filters),
        "-map", "[out]",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", "-preset", "medium",
        "-movflags", "+faststart",
        str(out),
    ])
    meta = {
        "output": str(out),
        "capture": str(capture),
        "marks": marks,
        "segments": [
            {"name": name, "start": marks[name] + 0.35, "duration": duration}
            for name, _card, duration in SEGMENTS
        ],
        "illustrated": [name for name, _d, _t, _s in CARDS],
        "caption": "Direct tool execution; no model inference",
    }
    (out.with_suffix(".story.json")).write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

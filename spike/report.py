"""Merge Phase 0 bench rows (*.jsonl) into a markdown report. Stdlib only."""
import argparse
import json
import sys
from pathlib import Path

COLUMNS = ["model", "mode", "status", "tok/s", "TTFT ms", "TTFA ms", "peak RSS MB", "detail"]
VERDICTS = [
    ("Omni speech output via llama.cpp", "omni", "tts"),
    ("Omni ASR via llama.cpp", "omni", "asr"),
    ("Omni vision via llama.cpp", "omni", "vision"),
    ("d1 via llama.cpp", "", "d1"),
]


def load_rows(results_dir):
    rows = []
    for path in sorted(Path(results_dir).glob("*.jsonl")):
        for n, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                row = None
            if not isinstance(row, dict):
                print(f"warning: skipping malformed line {path.name}:{n}", file=sys.stderr)
                continue
            rows.append(row)
    return rows


def _cell(value, limit=None):
    if value is None:
        return ""
    if isinstance(value, float):
        value = f"{value:.1f}"
    text = " ".join(str(value).split())
    if limit and len(text) > limit:
        text = text[: limit - 3] + "..."
    return text.replace("|", r"\|")


def verdict(rows, model_substr, mode):
    matches = [r for r in rows if model_substr in str(r.get("model", "")) and r.get("mode") == mode]
    if not matches:
        return "UNKNOWN"
    return "YES" if any(r.get("status") == "ok" for r in matches) else "NO"


def render(rows):
    out = ["# Phase 0 results", ""]
    if not rows:
        out += ["No results", ""]
    else:
        out.append("| " + " | ".join(COLUMNS) + " |")
        out.append("|" + "---|" * len(COLUMNS))
        for r in sorted(rows, key=lambda r: (str(r.get("model", "")), str(r.get("mode", "")))):
            cells = [
                _cell(r.get("model")), _cell(r.get("mode")), _cell(r.get("status")),
                _cell(r.get("tok_s")), _cell(r.get("ttft_ms")), _cell(r.get("ttfa_ms")),
                _cell(r.get("peak_rss_mb")), _cell(r.get("detail"), 80),
            ]
            out.append("| " + " | ".join(cells) + " |")
        out.append("")
    out += ["## Verdict", ""]
    for label, substr, mode in VERDICTS:
        out.append(f"- {label}: **{verdict(rows, substr, mode)}**")
    out.append("")
    return "\n".join(out)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results_dir")
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    Path(args.out).write_text(render(load_rows(args.results_dir)), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())

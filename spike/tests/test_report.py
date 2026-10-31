"""report.py: merge *.jsonl rows into a markdown table plus verdicts."""
import json
import re

import pytest

import report


def row(model="omni-2b", mode="tts", status="ok", **kw):
    r = {"model": model, "mode": mode, "status": status, "runs": 1, "tok_s": None,
         "ttft_ms": None, "ttfa_ms": None, "peak_rss_mb": None, "wall_s": None,
         "detail": "", "llama_tag": "b11960"}
    r.update(kw)
    return r


def write_jsonl(path, lines):
    path.write_text("\n".join(l if isinstance(l, str) else json.dumps(l) for l in lines) + "\n",
                    encoding="utf-8")


def table_lines(md):
    return [l for l in md.splitlines() if l.startswith("| ") and not l.startswith("| model")]


# -- load_rows

def test_load_rows_skips_malformed_blank_and_non_object(tmp_path, capsys):
    write_jsonl(tmp_path / "a.jsonl", [row(mode="text"), "{not json", "", "[1, 2]", row(mode="asr")])
    rows = report.load_rows(tmp_path)
    assert [r["mode"] for r in rows] == ["text", "asr"]
    assert "malformed" in capsys.readouterr().err


def test_load_rows_merges_files_and_ignores_other_extensions(tmp_path):
    write_jsonl(tmp_path / "a.jsonl", [row(model="a")])
    write_jsonl(tmp_path / "b.jsonl", [row(model="b")])
    write_jsonl(tmp_path / "notes.txt", [row(model="c")])
    assert sorted(r["model"] for r in report.load_rows(tmp_path)) == ["a", "b"]


def test_empty_dir_says_no_results(tmp_path):
    out = tmp_path / "out.md"
    assert report.main([str(tmp_path), "--out", str(out)]) == 0
    text = out.read_text(encoding="utf-8")
    assert "No results" in text
    assert "## Verdict" in text
    assert "UNKNOWN" in text


# -- verdict

@pytest.mark.parametrize("rows,expected", [
    ([row(status="ok")], "YES"),
    ([row(status="unsupported")], "NO"),
    ([row(status="error"), row(status="ok")], "YES"),   # any ok row wins
    ([row(status="timeout"), row(status="oom")], "NO"),
    ([], "UNKNOWN"),
    ([row(mode="asr", status="ok")], "UNKNOWN"),          # wrong mode
    ([row(model="audio-2b", status="ok")], "UNKNOWN"),    # wrong model
])
def test_verdict(rows, expected):
    assert report.verdict(rows, "omni", "tts") == expected


def test_render_states_omni_speech_verdict():
    md = report.render([row(status="ok", ttfa_ms=321.0)])
    line = next(l for l in md.splitlines() if "Omni speech output" in l)
    assert "YES" in line


# -- render cells

def test_pipe_escaped_in_detail():
    md = report.render([row(detail="a|b")])
    assert r"a\|b" in md
    # escaping must not add a column
    (line,) = table_lines(md)
    assert line.replace(r"\|", "").count("|") == len(report.COLUMNS) + 1


def test_long_detail_truncated():
    md = report.render([row(detail="x" * 500)])
    (line,) = table_lines(md)
    assert "x" * 81 not in line
    assert "x" * 77 + "..." in line


def test_newlines_in_detail_do_not_break_table():
    md = report.render([row(detail="line1\nline2\r\nline3")])
    assert len(table_lines(md)) == 1


def test_none_and_float_formatting():
    (line,) = table_lines(report.render([row(tok_s=12.345, ttft_ms=None)]))
    assert "12.3" in line and "12.345" not in line
    assert "None" not in line


# -- ordering

def test_sorted_by_model_then_deterministic():
    rows = [row(model="vl-2b", mode="vision"), row(model="audio-2b", mode="tts"),
            row(model="vl-2b", mode="text"), row(model="audio-2b", mode="asr")]
    md = report.render(rows)
    models_in_order = [l.split("|")[1].strip() for l in table_lines(md)]
    assert models_in_order == sorted(models_in_order)
    assert md == report.render(list(reversed(rows)))


def test_main_end_to_end(tmp_path):
    res = tmp_path / "results"
    res.mkdir()
    write_jsonl(res / "omni-2b.jsonl", [row(mode="tts", status="unsupported", detail="404 /tts")])
    write_jsonl(res / "d1-2b.jsonl", [row(model="d1-2b", mode="d1", status="ok")])
    out = tmp_path / "phase0.md"
    assert report.main([str(res), "--out", str(out)]) == 0
    md = out.read_text(encoding="utf-8")
    assert len(table_lines(md)) == 2
    assert re.search(r"Omni speech output.*NO", md)
    assert re.search(r"d1 via llama\.cpp.*YES", md)

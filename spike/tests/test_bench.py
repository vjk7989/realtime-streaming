"""bench.py: pure helpers plus run_bench with llama-server, HTTP and psutil mocked."""
import json
import socket
import subprocess
from unittest.mock import MagicMock

import pytest
import requests

import bench
from conftest import ROW_FIELDS, STATUSES

MODES = ["text", "tts", "d1"]


# ---------------------------------------------------------------- helpers

@pytest.mark.parametrize("rc,stderr,expected", [
    (-9, "", "oom"),
    (137, "anything", "oom"),
    (1, "llama_model_load: error loading model: unknown model architecture: 'lfm3'", "unsupported"),
    (1, "error: Unsupported audio format", "unsupported"),
    (1, "segfault somewhere", "error"),
    (1, "", "error"),
    (1, None, "error"),
    (0, "", "error"),
])
def test_classify_exit(rc, stderr, expected):
    assert bench.classify_exit(rc, stderr) == expected


@pytest.mark.parametrize("xs,expected", [
    ([3, 1, 2], 2),
    ([4, 1, 3, 2], 2.5),
    ([7.5], 7.5),
    ([], None),
    ([None, 5, None], 5),
    ([None], None),
])
def test_median(xs, expected):
    assert bench.median(xs) == expected


def test_make_row_has_contract_fields_and_defaults():
    row = bench.make_row("omni-2b", "tts", "ok", ttfa_ms=12.0)
    assert set(row) == ROW_FIELDS
    assert (row["model"], row["mode"], row["status"], row["ttfa_ms"]) == ("omni-2b", "tts", "ok", 12.0)
    assert row["runs"] == 0 and row["detail"] == "" and row["tok_s"] is None
    json.dumps(row)  # must be serializable


def test_make_row_rejects_unknown_field():
    with pytest.raises(TypeError):
        bench.make_row("m", "text", "ok", bogus=1)


# ---------------------------------------------------------------- run_bench harness

def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def resp(status=200, lines=(), content=b"", body=None):
    r = MagicMock(status_code=status, text=json.dumps(body or {}))
    r.__enter__.return_value = r
    r.iter_lines.return_value = list(lines)
    r.iter_content.return_value = [content] if content else []
    r.json.return_value = body or {}
    return r


@pytest.fixture
def env(tmp_path, monkeypatch):
    """A tmp models.yaml, model files, and mocked Popen/psutil/requests.

    env.post_routes maps a URL suffix to a response or an exception to raise.
    """
    e = MagicMock()
    (tmp_path / "models.yaml").write_text(
        "llama_tag: b11960\nmodels:\n"
        f"  - id: m\n    repo: x/y\n    file: m.gguf\n    mmproj: p.gguf\n    modes: [{', '.join(MODES)}]\n",
        encoding="utf-8")
    e.model, e.mmproj = tmp_path / "m.gguf", tmp_path / "p.gguf"
    e.model.write_bytes(b"gguf")
    e.mmproj.write_bytes(b"gguf")
    e.out = tmp_path / "out" / "m.jsonl"
    e.tmp = tmp_path

    proc = MagicMock(pid=4242, returncode=None)
    proc.poll.return_value = None
    proc.wait.return_value = 0
    e.proc = proc
    e.popen = MagicMock(return_value=proc)
    monkeypatch.setattr(bench.subprocess, "Popen", e.popen)

    ps = MagicMock()
    ps.memory_info.return_value.rss = 256 * 2**20
    monkeypatch.setattr(bench.psutil, "Process", MagicMock(return_value=ps))

    monkeypatch.setattr(bench.requests, "get", MagicMock(return_value=resp(200)))
    e.post_routes = {}

    def post(url, **kw):
        for suffix, r in e.post_routes.items():
            if url.endswith(suffix):
                if isinstance(r, BaseException):
                    raise r
                return r
        return resp(500, body={"error": "unmocked"})

    monkeypatch.setattr(bench.requests, "post", post)
    monkeypatch.setattr(bench.time, "sleep", lambda s: None)

    def run(*extra, model=None, mmproj=None, model_id="m"):
        argv = [model_id, "--bin", str(tmp_path / "bin"),
                "--model", str(model or e.model), "--mmproj", str(mmproj or e.mmproj),
                "--out", str(e.out), "--runs", "1", "--timeout", "5",
                "--port", str(free_port()), "--models", str(tmp_path / "models.yaml"), *extra]
        return bench.main(argv)

    def rows():
        return [json.loads(l) for l in e.out.read_text(encoding="utf-8").splitlines() if l.strip()]

    e.run, e.rows = run, rows
    e.by_mode = lambda: {r["mode"]: r for r in rows()}
    return e


def assert_rows_valid(rows):
    for r in rows:
        assert set(r) == ROW_FIELDS
        assert r["status"] in STATUSES
        assert r["llama_tag"] == "b11960"


def assert_stopped(proc):
    assert proc.terminate.called or proc.kill.called, "llama-server was not stopped"


# ---------------------------------------------------------------- run_bench behavior

def test_unknown_id_exits_2(env):
    assert env.run(model_id="nope") == 2
    env.popen.assert_not_called()


@pytest.mark.parametrize("which", ["model", "mmproj"])
def test_missing_file_rows_and_no_server(env, which):
    assert env.run(**{which: env.tmp / "absent.gguf"}) == 0
    rows = env.rows()
    assert [r["mode"] for r in rows] == MODES
    assert {r["status"] for r in rows} == {"missing_file"}
    assert all("absent.gguf" in r["detail"] for r in rows)
    assert_rows_valid(rows)
    env.popen.assert_not_called()


def test_port_in_use_gives_error_rows(env):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        s.listen()
        assert env.run("--port", str(s.getsockname()[1])) == 0
    assert {r["status"] for r in env.rows()} == {"error"}
    env.popen.assert_not_called()


def test_missing_binary_gives_error_rows(env):
    env.popen.side_effect = FileNotFoundError("llama-server not found")
    assert env.run() == 0
    rows = env.rows()
    assert len(rows) == len(MODES) and {r["status"] for r in rows} == {"error"}


def test_runner_exception_becomes_error_row_and_server_stopped(env, monkeypatch):
    def boom(*a, **kw):
        raise RuntimeError("kaboom")
    monkeypatch.setattr(bench, "RUNNERS", {m: boom for m in MODES})
    assert env.run() == 0
    rows = env.rows()
    assert {r["status"] for r in rows} == {"error"}
    assert "kaboom" in rows[0]["detail"]
    assert_stopped(env.proc)


def test_server_stopped_even_on_base_exception(env, monkeypatch):
    def interrupt(*a, **kw):
        raise KeyboardInterrupt
    monkeypatch.setattr(bench, "RUNNERS", {m: interrupt for m in MODES})
    with pytest.raises(KeyboardInterrupt):
        env.run()
    assert_stopped(env.proc)


def test_server_killed_if_terminate_hangs(env, monkeypatch):
    monkeypatch.setattr(bench, "RUNNERS", {m: (lambda *a, **k: {}) for m in MODES})
    env.proc.wait.side_effect = [subprocess.TimeoutExpired("llama-server", 10), 0]
    assert env.run() == 0
    env.proc.terminate.assert_called()
    env.proc.kill.assert_called()


def test_server_crash_on_load_classified_from_log(env):
    def start(cmd, stdout=None, **kw):
        stdout.write(b"llama_model_load: error: unknown model architecture: 'lfm3'\n")
        stdout.flush()
        env.proc.returncode = 1
        env.proc.poll.return_value = 1
        return env.proc
    env.popen.side_effect = start
    assert env.run() == 0
    rows = env.rows()
    assert len(rows) == len(MODES)
    assert {r["status"] for r in rows} == {"unsupported"}
    assert (env.out.parent / "m-server.log").exists()


def test_server_oom_kill_on_load(env):
    env.proc.returncode = -9
    env.proc.poll.return_value = -9
    assert env.run() == 0
    assert {r["status"] for r in env.rows()} == {"oom"}


def test_request_timeout_maps_to_timeout(env):
    for suffix in ("/v1/chat/completions", "/tts", "/v1/systemone"):
        env.post_routes[suffix] = requests.exceptions.ReadTimeout("read timed out")
    assert env.run() == 0
    assert {r["status"] for r in env.rows()} == {"timeout"}
    assert_stopped(env.proc)


def test_tts_404_and_d1_501_are_unsupported(env):
    env.post_routes["/tts"] = resp(404)
    env.post_routes["/v1/systemone"] = resp(501, body={"error": "not implemented"})
    assert env.run() == 0
    rows = env.by_mode()
    assert rows["tts"]["status"] == "unsupported"
    assert rows["d1"]["status"] == "unsupported"
    assert rows["text"]["status"] == "error"  # unmocked 500
    assert_rows_valid(env.rows())


def test_happy_path_metrics(env):
    chunks = [
        'data: {"choices":[{"delta":{"content":"A rainbow"}}]}',
        "",
        'data: {"choices":[{"delta":{"content":" is light."}}],"timings":{"predicted_per_second":42.5}}',
        "data: [DONE]",
    ]
    env.post_routes["/v1/chat/completions"] = resp(200, lines=chunks)
    env.post_routes["/tts"] = resp(200, content=b"RIFF" + b"\0" * 2000)
    env.post_routes["/v1/systemone"] = resp(200, body={"answers": {"person": "no"}})
    assert env.run() == 0
    rows = env.by_mode()
    assert_rows_valid(env.rows())
    assert {r["status"] for r in rows.values()} == {"ok"}, rows
    t = rows["text"]
    assert t["tok_s"] == 42.5 and t["ttft_ms"] is not None and "rainbow" in t["detail"]
    assert t["runs"] == 1 and t["ttfa_ms"] is None
    assert rows["tts"]["ttfa_ms"] is not None
    assert (env.out.parent / "m-tts.wav").read_bytes().startswith(b"RIFF")
    assert_stopped(env.proc)


def test_tts_without_audio_is_error(env):
    env.post_routes["/tts"] = resp(200, content=b"<html>oops</html>")
    assert env.run() == 0
    assert env.by_mode()["tts"]["status"] == "error"


def test_rows_append_across_runs(env):
    env.run(model=env.tmp / "absent.gguf")
    env.run(model=env.tmp / "absent.gguf")
    assert len(env.rows()) == 2 * len(MODES)

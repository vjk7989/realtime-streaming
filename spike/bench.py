"""Phase 0 bench: start one llama-server, run each mode a model lists, append JSON rows.

Contract: docs/adr/0003-phase0-spike.md.
"""
import argparse
import base64
import json
import os
import socket
import statistics
import subprocess
import sys
import threading
import time
from pathlib import Path

import psutil
import requests
import yaml

FIXTURES = Path(__file__).resolve().parent / "fixtures"
ROW_FIELDS = ("runs", "tok_s", "ttft_ms", "ttfa_ms", "peak_rss_mb", "wall_s", "detail", "llama_tag")
TEXT_PROMPT = "Explain what a rainbow is in 3 sentences."
TTS_TEXT = "Hello, this is a local speech test."


class Fail(Exception):
    """A mode result that is not ok: carries the row status and detail."""

    def __init__(self, status, detail=""):
        super().__init__(detail)
        self.status, self.detail = status, detail


def classify_exit(returncode, stderr_text):
    if returncode in (-9, 137):
        return "oom"
    low = (stderr_text or "").lower()
    if "unknown model architecture" in low or "unsupported" in low:
        return "unsupported"
    return "error"


def median(xs):
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else None


def make_row(model, mode, status, **metrics):
    unknown = set(metrics) - set(ROW_FIELDS)
    if unknown:
        raise TypeError(f"unknown row fields: {sorted(unknown)}")
    row = {"model": model, "mode": mode, "status": status, "runs": 0, "tok_s": None,
           "ttft_ms": None, "ttfa_ms": None, "peak_rss_mb": None, "wall_s": None,
           "detail": "", "llama_tag": None}
    row.update(metrics)
    return row


def _b64(path):
    return base64.b64encode(Path(path).read_bytes()).decode("ascii")


def _check(resp):
    if resp.status_code != 200:
        raise Fail("error", f"HTTP {resp.status_code}: {resp.text[:200]}")


def _stream_chat(base_url, messages, timeout, max_tokens=128):
    """Streamed chat completion. Returns (text, ttft_ms, tok_s).

    TTFT counts reasoning tokens too: models with reasoning on stream
    `reasoning_content` first and may never reach `content` within max_tokens.
    """
    body = {"messages": messages, "stream": True, "max_tokens": max_tokens, "temperature": 0}
    t0 = time.perf_counter()
    ttft, parts, thinking, timings = None, [], [], {}
    with requests.post(f"{base_url}/v1/chat/completions", json=body, stream=True,
                       timeout=timeout) as r:
        _check(r)
        for line in r.iter_lines(decode_unicode=True):
            if not line or not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            chunk = json.loads(data)
            timings = chunk.get("timings") or timings
            for ch in chunk.get("choices") or []:
                d = ch.get("delta") or {}
                for key, sink in (("reasoning_content", thinking), ("content", parts)):
                    if d.get(key):
                        if ttft is None:
                            ttft = (time.perf_counter() - t0) * 1000
                        sink.append(d[key])
    text = "".join(parts) or ("[reasoning] " + "".join(thinking) if thinking else "")
    return text, ttft, timings.get("predicted_per_second")


def run_text(base_url, timeout, **_):
    text, ttft, tok_s = _stream_chat(base_url, [{"role": "user", "content": TEXT_PROMPT}], timeout)
    return {"tok_s": tok_s, "ttft_ms": ttft, "detail": text[:200]}


def run_vision(base_url, timeout, **_):
    uri = "data:image/jpeg;base64," + _b64(FIXTURES / "scene.jpg")
    content = [{"type": "image_url", "image_url": {"url": uri}},
               {"type": "text", "text": "What objects are in this image?"}]
    text, ttft, tok_s = _stream_chat(base_url, [{"role": "user", "content": content}], timeout)
    return {"tok_s": tok_s, "ttft_ms": ttft, "detail": text[:200]}


def run_asr(base_url, timeout, **_):
    audio = {"type": "input_audio", "input_audio": {"data": _b64(FIXTURES / "jfk.wav"), "format": "wav"}}
    msgs = [{"role": "system", "content": "Perform ASR in English."},
            {"role": "user", "content": [audio]}]
    text, ttft, tok_s = _stream_chat(base_url, msgs, timeout)
    match = "country" in text.lower()
    return {"tok_s": tok_s, "ttft_ms": ttft, "detail": f"match={match} {text.strip()[:180]}"}


def run_tts(base_url, timeout, out_dir=".", model_id="model", **_):
    t0 = time.perf_counter()
    ttfa, buf = None, bytearray()
    with requests.post(f"{base_url}/tts", json={"input": TTS_TEXT, "stream": True},
                       stream=True, timeout=timeout) as r:
        if r.status_code == 404:
            raise Fail("unsupported", "POST /tts returned 404")
        _check(r)
        for chunk in r.iter_content(chunk_size=4096):
            buf.extend(chunk)
            # The streamed WAV header (44 bytes) may arrive before any audio.
            if ttfa is None and len(buf) > 44:
                ttfa = (time.perf_counter() - t0) * 1000
    if not buf.startswith(b"RIFF") or len(buf) <= 44:
        raise Fail("error", f"no audio: {len(buf)} bytes, starts {bytes(buf[:16])!r}")
    path = Path(out_dir) / f"{model_id}-tts.wav"
    path.write_bytes(bytes(buf))
    return {"ttfa_ms": ttfa, "detail": f"{len(buf)} bytes wav -> {path.name}"}


def run_d1(base_url, timeout, **_):
    body = {"state": None,
            "images": ["data:image/jpeg;base64," + _b64(FIXTURES / "scene.jpg")],
            "questions": {
                "person": {"type": "noul", "instructions": "Is there a person in the picture?"},
                "place": {"type": "choice", "instructions": "Is this an indoor or outdoor scene?",
                          "criteria": {"indoor": "indoor scene", "outdoor": "outdoor scene"}}}}
    t0 = time.perf_counter()
    r = requests.post(f"{base_url}/v1/systemone", json=body, timeout=timeout)
    latency = (time.perf_counter() - t0) * 1000
    if r.status_code == 501:
        raise Fail("unsupported", f"/v1/systemone 501: {r.text[:150]}")
    _check(r)
    return {"ttft_ms": latency, "detail": json.dumps(r.json().get("answers"))[:300]}


RUNNERS = {"text": run_text, "vision": run_vision, "asr": run_asr, "tts": run_tts, "d1": run_d1}


class RssSampler(threading.Thread):
    def __init__(self, pid, interval=0.2):
        super().__init__(daemon=True)
        self.proc, self.interval, self.peak = psutil.Process(pid), interval, 0
        self.stop = threading.Event()

    def run(self):
        while not self.stop.is_set():
            try:
                self.peak = max(self.peak, self.proc.memory_info().rss)
            except psutil.Error:
                return
            self.stop.wait(self.interval)

    def peak_mb(self):
        return round(self.peak / 2**20, 1) if self.peak else None


def _tail(log_path):
    try:
        lines = [ln for ln in Path(log_path).read_text(errors="replace").splitlines() if ln.strip()]
    except OSError:
        return "", ""
    return "\n".join(lines[-200:]), (lines[-1] if lines else "")


def _exit_fail(proc, log_path):
    text, last = _tail(log_path)
    return Fail(classify_exit(proc.returncode, text), f"exit {proc.returncode}: {last[:200]}")


def _port_free(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def _wait_healthy(proc, base_url, timeout, log_path):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise _exit_fail(proc, log_path)
        try:
            if requests.get(f"{base_url}/health", timeout=5).status_code == 200:
                return
        except requests.RequestException:
            pass
        time.sleep(1)
    raise Fail("timeout", f"server not healthy after {timeout}s")


def _stop(proc):
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


def _run_mode(mode, args, base_url, proc, log_path, sampler, out_dir):
    """Run one mode --runs times. Returns the row metrics plus status."""
    sampler.peak = 0
    t0 = time.perf_counter()
    results, status, detail = [], "ok", ""
    try:
        for _ in range(args.runs):
            results.append(RUNNERS[mode](base_url, args.timeout, out_dir=out_dir, model_id=args.id))
    except Fail as f:
        status, detail = f.status, f.detail
    except requests.Timeout:
        status, detail = "timeout", f"request exceeded {args.timeout}s"
    except requests.RequestException as e:
        if proc.poll() is not None:
            f = _exit_fail(proc, log_path)
            status, detail = f.status, f.detail
        else:
            status, detail = "error", f"{type(e).__name__}: {e}"[:200]
    except Exception as e:  # malformed response etc.: record it, keep going
        status, detail = "error", f"{type(e).__name__}: {e}"[:200]
    metrics = {k: median([r.get(k) for r in results]) for k in ("tok_s", "ttft_ms", "ttfa_ms")}
    if status == "ok":
        detail = results[-1].get("detail", "")
    return status, dict(metrics, runs=len(results), peak_rss_mb=sampler.peak_mb(),
                        wall_s=round(time.perf_counter() - t0, 2), detail=detail)


def run_bench(args):
    cfg = yaml.safe_load(Path(args.models).read_text())
    spec = next((m for m in cfg.get("models", []) if m.get("id") == args.id), None)
    if spec is None:
        print(f"unknown model id: {args.id}", file=sys.stderr)
        return 2
    tag, modes = cfg.get("llama_tag"), spec.get("modes", [])
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out_dir = out.parent

    def write(rows):
        with out.open("a", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row) + "\n")

    missing = [p for p in (args.model, args.mmproj) if p and not Path(p).is_file()]
    if missing:
        write([make_row(args.id, m, "missing_file", detail="missing: " + ", ".join(Path(p).name for p in missing),
                        llama_tag=tag)
               for m in modes])
        return 0
    if not _port_free(args.port):
        write([make_row(args.id, m, "error", detail=f"port {args.port} already in use",
                        llama_tag=tag) for m in modes])
        return 0

    cmd = [str(Path(args.bin) / "llama-server"), "-m", args.model]
    if args.mmproj:
        cmd += ["--mmproj", args.mmproj]
    cmd += ["--port", str(args.port), "-c", "4096"] + [str(a) for a in spec.get("server_args", [])]
    base_url = f"http://127.0.0.1:{args.port}"
    log_path = out_dir / f"{args.id}-server.log"
    t0 = time.perf_counter()
    with open(log_path, "wb") as log:
        try:
            proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT)
        except OSError as e:
            write([make_row(args.id, m, "error", detail=f"cannot start {cmd[0]}: {e}"[:200],
                            llama_tag=tag) for m in modes])
            return 0
        sampler = RssSampler(proc.pid)
        sampler.start()
        try:
            try:
                _wait_healthy(proc, base_url, args.timeout, log_path)
            except Fail as f:
                wall = round(time.perf_counter() - t0, 2)
                write([make_row(args.id, m, f.status, detail=f.detail, wall_s=wall,
                                peak_rss_mb=sampler.peak_mb(), llama_tag=tag) for m in modes])
                return 0
            for mode in modes:
                if mode not in RUNNERS:
                    write([make_row(args.id, mode, "error", detail=f"unknown mode {mode}",
                                    llama_tag=tag)])
                    continue
                status, metrics = _run_mode(mode, args, base_url, proc, log_path, sampler, out_dir)
                write([make_row(args.id, mode, status, llama_tag=tag, **metrics)])
        finally:
            sampler.stop.set()
            _stop(proc)
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description="Benchmark one model with llama-server.")
    p.add_argument("id")
    p.add_argument("--bin", required=True, help="directory holding llama-server")
    p.add_argument("--model", required=True)
    p.add_argument("--mmproj")
    p.add_argument("--out", required=True, help="JSONL file to append rows to")
    p.add_argument("--runs", type=int, default=3)
    p.add_argument("--timeout", type=int, default=600)
    p.add_argument("--port", type=int, default=8089)
    p.add_argument("--models", default=str(Path(__file__).resolve().parent / "models.yaml"))
    return run_bench(p.parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())

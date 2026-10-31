# ADR 0003: Phase 0 spike design and contract
Date: 2026-11-01 · Status: Accepted

## Decisions
- **Only `llama-server` is used.** It covers chat (text, plus image and audio input), `POST /tts` (speech output, 24 kHz), and `POST /v1/systemone` (d1). This matches how `lfm-hub` will run models. `llama-tts` and `llama-mtmd-cli` are not used (YAGNI).
- **llama.cpp is pinned to `b11960`** (v0.8.0, the minimum for LFM3). The prebuilt `ubuntu-x64` tarball is used in CI.
- **CI runs one model per matrix job,** so a ~14 GB runner disk is enough. Models are never downloaded on the laptop.
- **Fixtures:**
  - `spike/fixtures/jfk.wav`: the whisper.cpp sample, public domain, 16 kHz mono.
  - `spike/fixtures/scene.jpg`: a small public-domain photo.
- **Integrity:** the sha256 of each file is read at runtime from the HF API (`lfs.sha256`) and compared after download.

## Contract (shared by fetch, bench, report, and tests)
`spike/models.yaml`:
```yaml
llama_tag: b11960
models:
  - id: omni-2b                      # unique, [a-z0-9-]
    repo: LiquidAI/LFM3-Omni-2B-GGUF
    file: LFM3-Omni-2B-Q4_K_M.gguf
    mmproj: mmproj-LFM3-Omni-2B-Q8_0.gguf   # optional
    modes: [text, vision, asr, tts]  # subset of: text vision asr tts d1
    server_args: ["--reasoning", "off"]     # optional
```
`python spike/fetch.py <id> --dest DIR` downloads and verifies the files, then prints a JSON object to stdout:
`{"id","model_path","mmproj_path"|null}`.

Exit codes:
- 0: ok
- 2: sha256 mismatch (the file is deleted)
- 3: not enough free disk (less than size × 1.2)
- 4: unknown id, or the file is missing on HF

`python spike/bench.py <id> --bin DIR --model PATH [--mmproj PATH] --out FILE.jsonl [--runs 3] [--timeout 600] [--port 8089]` starts one `llama-server`, runs each mode the model lists, writes one JSON row per mode, and always stops the server.

Row fields:
- `model`, `mode`
- `status`: `ok` | `unsupported` | `oom` | `timeout` | `missing_file` | `error`
- `runs`
- `tok_s` (median), `ttft_ms` (median), `ttfa_ms` (TTS only, else null)
- `peak_rss_mb`, `wall_s`
- `detail` (a short string with evidence or the error)
- `llama_tag`

`python spike/report.py RESULTS_DIR --out docs/phase0-results.md` merges every `*.jsonl` into one markdown table and states the answer to "Omni speech out via llama.cpp?" with evidence.

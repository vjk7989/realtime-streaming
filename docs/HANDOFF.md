# Handoff
Read this first in any new session, then read `docs/adr/` and `docs/TODO.md`.

## Where we are (2026-11-01)
- The plan is approved (`docs/PLAN.md`). **The Phase 0 CI leg is done and green** (ADR 0004). The Android-phone leg is waiting on the user's phone. Phase 1 (lfm-hub) is next.
- Tooling on this machine:
  - Graphify reinstalled at `G:\voice-model\.tools\venv\Scripts\graphify.exe`. The global C: install was broken.
  - Headroom 0.20.15 is installed globally.
  - Go and Flutter are **not** installed locally. Builds run in CI.

## Things to note
- Before running uv or pip locally, set `UV_CACHE_DIR`, `PIP_CACHE_DIR`, `HF_HOME`, and `TEMP`/`TMP` to paths under `G:\voice-model\.cache`.
- llama.cpp produces Omni speech output (CI-verified). Use `--reasoning off` for chat models.
- CI timings are noisy (up to 2.5× between runs). Trust the RAM figures and pass/fail, not the latency figures.

## Planner findings, 2026-11-01 (from docs; not yet verified by running them)
- llama.cpp **b11960** or newer is needed for LFM3. `llama-server` provides:
  - `POST /tts`: 24 kHz speech output for Omni and Audio. The mmproj holds the codec decoder.
  - `/v1/realtime` WebSocket: voice chat.
  - `POST /v1/systemone`: d1 decisions. No chat template; Noul/Choice/Score answers come back as probabilities.
- Omni must be run with `--reasoning off`. d1 models need `--cache-ram 0` and a large `-b/-ub`.
- d1-omni-600M is a separate repo (`d1-omni-600M-GGUF`) and only comes as Q8_0. d1-Omni-2B's smallest quant is Q8_0 (1.85 GB).
- Risk: the prebuilt Android tarball may contain only `llama-cli`, `llama-server`, and `llama-bench`. That's fine, because we only need `llama-server`.

## Change log
- 2026-11-01: Repo created. ADR 0001 (architecture) and ADR 0002 (process) written.
- 2026-11-01: ADR 0003 (Phase 0 spike contract). Devs 1-3 and the test-writer started.
- 2026-11-01: Phase 0 harness + CI landed. Run 41235922728 was all green but exposed empty TTFT for reasoning-on models. Fixed in bench.py with a regression test. Run 41236367391 was green with complete rows. ADR 0004 written.

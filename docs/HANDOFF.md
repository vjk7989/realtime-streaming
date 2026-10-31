# Handoff
Read this first in any new session, then read `docs/adr/` and `docs/TODO.md`.

## Where we are (2026-11-01)
- The plan is approved (`docs/PLAN.md`). Phase 0 (model spike) is in progress.
- Tooling on this machine:
  - Graphify reinstalled at `G:\voice-model\.tools\venv\Scripts\graphify.exe`. The global C: install was broken.
  - Headroom 0.20.15 is installed globally.
  - Go and Flutter are **not** installed locally. Builds run in CI.

## Things to note
- Before running uv or pip locally, set `UV_CACHE_DIR`, `PIP_CACHE_DIR`, `HF_HOME`, and `TEMP`/`TMP` to paths under `G:\voice-model\.cache`.
- llama.cpp is not confirmed to produce Omni speech output, so the Phase 0 result decides it.

## Change log
- 2026-11-01: Repo created. ADR 0001 (architecture) and ADR 0002 (process) written.

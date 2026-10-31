# TODO
The orchestrator keeps this file current. `[x]` means done and verified by tests.

## Phase 0: model spike
- [x] Repo, docs, and process ADRs
- [x] Research: how each LFM3 model runs in llama.cpp (planner, see ADR 0003)
- [ ] Spike harness (`spike/`) and CI workflow
- [ ] Tests for the harness (edge cases)
- [ ] CI run green, plus a results report (`docs/phase0-results.md`)
- [ ] Android on-phone benchmark (needs the user's phone over adb)
- [ ] Decide: Omni speech output through llama.cpp, or the Android TTS fallback

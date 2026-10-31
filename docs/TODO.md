# TODO
The orchestrator keeps this file current. `[x]` means done and verified by tests.

## Phase 0: model spike
- [x] Repo, docs, and process ADRs
- [x] Research: how each LFM3 model runs in llama.cpp (planner, see ADR 0003)
- [x] Spike harness (`spike/`) and CI workflow
- [x] Tests for the harness (edge cases, 71 passing)
- [x] CI run green, plus a results report (`docs/phase0-results.md`; run 41236367391)
- [ ] Android on-phone benchmark (needs the user's phone over adb)
- [x] Decide: Omni speech output through llama.cpp works (ADR 0004)

## Phase 1: laptop server (lfm-hub), not started
- [ ] Planner breakdown (also validates `/v1/realtime` for voice chat)

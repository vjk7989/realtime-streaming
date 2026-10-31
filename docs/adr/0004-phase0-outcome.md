# ADR 0004: Phase 0 outcome, CI (x64 CPU) leg
Date: 2026-11-01 Â· Status: Accepted (the Android leg is still pending)

## Evidence
CI runs 41235922728 and 41236367391 used llama.cpp b11960 `llama-server`, Q4_K_M, on GitHub ubuntu-latest (4 vCPU). Full table: `docs/phase0-results.md`.
- **Omni speech output works through llama.cpp.**
  - `POST /tts` works on LFM3-Omni-2B, with 590–920 ms to the first audio.
  - It also works on LFM3-Audio-2B (~900 ms).
- **ASR works.** The JFK sample is transcribed correctly by both Omni and Audio.
- **Vision works.**
  - Omni-2B: 22–28 tok/s.
  - VL-2B: 13–19 tok/s.
- **d1 works through `/v1/systemone`.**
  - d1-omni-600M: 2.8–6.1 s per image question, 850 MB RSS.
  - d1-2B: 6.2–15.5 s, 2.3 GB RSS.
- **Timing is noisy.** Shared runners vary up to 2.5× between runs, so only RAM figures and pass/fail are firm on CI.
- **Peak RSS is about 1.9â€“2.7 GB per model.**

## Decisions
1. **Omni-2B is the single main model** for voice, vision and text in both laptop mode and Tier A phones. The Android TTS fallback is no longer the plan for laptop mode.
2. **Run every chat model with `--reasoning off`** for interactive use. Text, VL and Audio default to thinking first. In CI they spent all 128 tokens reasoning before giving any answer, which is bad for live use.
3. **d1-omni-600M is the default decision model,** including on the laptop. It's 5Ã— faster than d1-2B on CPU. d1-2B is dropped (YAGNI).
4. **VL-2B is kept only as a Tier B phone candidate.** On x64 it's slower than Omni, so the Android benchmark has to justify keeping it.

## Still open
- The Android arm64 numbers need the user's phone over adb, using the prebuilt `llama-server` for android-arm64. They decide the Tier A/B thresholds.
- `/v1/realtime` (streaming voice chat) is untested. It's covered in Phase 1, since lfm-hub will use it.

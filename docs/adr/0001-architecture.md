# ADR 0001: Overall architecture
Date: 2026-11-01 · Status: Accepted

## Decision
- **Android first.** The UI is **Flutter**. iOS comes later, in Phase 5.
- **Laptop server:** a single **Go** binary, `lfm-hub`. It supervises llama.cpp `llama-server` processes and stores history in SQLite. The user picked "Rust/Go", and we chose Go because it's simpler.
- **Transport:** WSS on the LAN and on the Tailscale interface. Pairing uses a QR code that carries a one-time token and the TLS cert pin. No public ports are opened.
- **On-device:** llama.cpp (+ mtmd) built with the NDK and called through Dart FFI. Phones are sorted into capability tiers A, B, or C.
- **Models:** LFM3-Omni-2B (voice, vision, text), LFM3-VL-2B (vision fallback), LFM3-1.7B (text and tools), and d1-omni (decisions: Noul/Choice/Score only through llama.cpp).
- **One session protocol** is shared by the remote and on-device backends.

## Consequences
- We need to know whether llama.cpp supports Omni speech output, so Phase 0 is a spike that answers it. If it doesn't, the fallback is Android TTS.
- d1 typed answers (boxes, numbers) are out of scope because they require Python Transformers.

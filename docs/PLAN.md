# Plan: Private multimodal assistant on LFM3 (phone + self-hosted laptop)

## Context
The goal is a private assistant similar to Google Live Transcribe and Gemini Live camera, built on Liquid AI's open-weight LFM3 family. It should let the user talk, type, and point the camera, then ask what's happening around them. Nothing goes to the cloud. There are two ways to run it:
1. **Laptop-hosted (primary).** The model and all data stay on the user's laptop. The phone is a thin client connected over WebSocket, on the home LAN or anywhere through Tailscale.
2. **On-device.** The model runs on the phone itself when the phone has enough RAM and CPU.

The working directory `G:\voice-model` is empty, so this is a new project.

**Decisions made:** Android first, a Flutter UI, LAN + Tailscale for the connection, and a single-binary server. I chose **Go** for the server because it is simple, cross-compiles easily, and has good WebSocket and process-supervision support.

## Models used (from the LFM3 release, Oct 27, 2026)
| Role | Model | Runtime | Notes |
|---|---|---|---|
| Voice + vision + text, all in one | `LiquidAI/LFM3-Omni-2B-GGUF` | llama.cpp | Takes text, image, video, and audio in. Puts out text and speech, or both interleaved. Does ASR, TTS, voice chat, and tool calls. |
| Vision Q&A (lighter fallback) | `LiquidAI/LFM3-VL-2B-GGUF` (+ `mmproj`) | llama.cpp mtmd | Used on mid-tier phones. |
| Text / agent / tools | `LiquidAI/LFM3-1.7B-GGUF` | llama.cpp | About 1 GB at Q4. 256K context. |
| Decisions / routing / gating | `d1-omni-600M` (phone), `d1-omni-2B` (laptop) | llama.cpp (Noul/Choice/Score only) | Returns calibrated probabilities with zero generated tokens. Used to route intents and to decide whether a frame is worth describing. |

Quantization is Q4_K_M by default and Q4_0 on low-end phones.

## Architecture
```
Flutter app ──► InferenceBackend (interface)
                 ├─ RemoteBackend  ── WSS (LAN / Tailscale) ──► Go server "lfm-hub" on laptop
                 │                                              ├─ supervises llama-server processes (omni, text, d1)
                 │                                              ├─ SQLite: conversations, transcripts, settings
                 │                                              └─ pairing + auth
                 └─ OnDeviceBackend ── Dart FFI ──► libllama + libmtmd (Android NDK, arm64)
```
Both backends use the **same session protocol**. The UI never knows where the model runs, and the user can switch backends at runtime.

### Wire protocol (`/protocol`, JSON Schema plus binary frames)
- Control messages are JSON: `hello{token, client_ver}`, `session.start{mode: chat|voice|live_transcript|live_vision}`, `input.text`, `input.image{jpeg}`, `input.audio.start/stop`, `output.text.delta`, `output.transcript{partial|final}`, `output.audio.start/stop`, `decision.result{type, probs}`, `tool.call`, `error`.
- Audio travels in binary frames: PCM16 mono, 16 kHz up and 24 kHz down. Camera frames travel as JPEG binary frames. Each frame has a 1-byte type header.
- The on-device backend emits the same event stream in-process through Dart Streams.

### Features → pipeline
- **Live transcript:** mic → VAD (Silero VAD, ONNX) → about 2 s chunks → Omni in ASR mode → partial and final captions. Captions are saved to the laptop DB.
- **Voice chat:** push-to-talk, or VAD for hands-free. Omni produces interleaved text and speech, and the app plays the speech as it streams.
- **Camera "what's around me":** a single snapshot plus a question, sent to Omni or VL. In continuous mode the app samples 1 frame/s, and d1 runs a Noul check ("has the scene meaningfully changed / is something notable?"). The app only describes the scene when that check passes, which saves compute and avoids talking too much.
- **Decision/router:** d1 Choice sorts each voice command into `{describe_scene, read_text, transcribe, chat, tool}` and picks the pipeline.
- **Text chat:** the LFM3-1.7B text model, with tool calls for local actions such as timers and notes.

### Device capability gate (on-device mode)
On first launch the app checks RAM, ABI, and Android version, then runs a 10-second micro-benchmark.
- **Tier A** (≥12 GB RAM, recent Snapdragon or Dimensity): Omni-2B Q4 plus d1-600M.
- **Tier B** (6–11 GB): VL-2B Q4_0 plus d1-600M. Speech uses Android's built-in SpeechRecognizer and TTS.
- **Tier C** (<6 GB, or benchmark under ~8 tok/s): remote mode only. The app explains why.

Models are downloaded on demand from Hugging Face. The download manager checks SHA256 hashes and lets the user remove models to free space.

### Privacy and security
- Pairing: the server shows a QR code containing `{url(s), one-time token, TLS cert SHA256}`. The app pins that cert and stores a long-lived device key in Android Keystore.
- The server listens with TLS on LAN and on its Tailscale interface. It never opens public ports.
- In remote mode the phone stores no data persistently. In on-device mode, data goes into an encrypted SQLite file on the phone.

## Repo layout (monorepo at `G:\voice-model`)
- `protocol/`: JSON Schemas plus generated Dart and Go types
- `server/` (Go): `cmd/lfm-hub`, `internal/{gateway,ws,models(supervisor),store(sqlite),pairing,router}`
- `app/` (Flutter): `lib/backends/{remote,ondevice}`, `lib/features/{transcript,voice,vision,chat}`, `lib/core/{audio,camera,vad,capability}`
- `native/`: llama.cpp git submodule plus a thin C wrapper (`lfm_bridge.c`) exposed to Dart through `ffigen`. Built with NDK and `LLAMA_BUILD_MTMD=ON` for arm64-v8a.
- `scripts/`: model fetch, benchmark, and release builds

## Phases
0. **Spike, 1 week. This is the gating step.**
   - Run each model with `llama-server` and `llama-mtmd-cli` on the laptop.
   - Run each model on an Android phone using the prebuilt binaries over adb or Termux.
   - Record tok/s, RAM use, and time to first audio.
   - **Confirm that llama.cpp supports Omni speech output on Android.** If it doesn't, ship with Omni text out plus Android TTS, and track upstream support.
1. **Server MVP:**
   - Go WS gateway
   - llama-server supervisor that starts models lazily and unloads them when idle
   - pairing via QR
   - SQLite history
   - a CLI test client
2. **App MVP (remote):**
   - pair by scanning the QR code
   - text chat
   - push-to-talk voice
   - snapshot-and-ask camera
3. **Live modes:**
   - live transcript with VAD
   - continuous vision with d1 gating
   - d1 intent router
   - a hands-free voice loop
4. **On-device backend:**
   - FFI bridge
   - model manager
   - capability tiers
   - fallback to the backend switcher
5. **Hardening:**
   - Tailscale setup guide
   - server installers for Windows (MSI) and macOS (brew)
   - battery and thermal throttling (lower the frame rate when the phone gets hot)
   - iOS port using `llama.xcframework`

## Key risks
- **Omni audio output in llama.cpp, especially on mobile, isn't clearly documented.** Phase 0 checks this first, and Android TTS is the fallback.
- **d1 typed answers (bounding boxes, numbers) work only in Transformers.** The plan uses only Noul, Choice, and Score through llama.cpp, so no Python is needed.
- **Thermals and battery during continuous camera and audio use.** d1 gating, a low frame rate, and a thermal-status API listener keep this in check.

## Verification
- **Server:**
  - `go test ./...`
  - CLI client script that streams a WAV file and gets a transcript, sends a JPEG and gets a description, and sends text and gets a reply
- **App:**
  - Flutter unit tests for the protocol codec and the backend switcher
  - an integration test against a mock WS server
- **End-to-end:**
  - On the same Wi-Fi: pair, run live transcript, ask "what is this?" with the camera, and have a voice conversation.
  - Switch the phone to mobile data and confirm the same flows work over Tailscale.
  - Confirm the laptop DB has the history and the phone has none.
- **On-device:**
  - Turn on airplane mode on a Tier A phone and run the same flows.
  - Check that a Tier C device is sent to remote mode.
  - Log tok/s and RAM use against the Phase 0 baselines.

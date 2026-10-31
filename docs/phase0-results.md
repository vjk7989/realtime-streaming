# Phase 0 results

| model | mode | status | tok/s | TTFT ms | TTFA ms | peak RSS MB | detail |
|---|---|---|---|---|---|---|---|
| audio-2b | asr | ok | 27.6 | 3277.5 |  | 2335.5 | match=True And so, my fellow Americans, ask not what your country can do for ... |
| audio-2b | text | ok | 27.9 | 499.0 |  | 2183.3 | [reasoning] We need to answer: "Explain what a rainbow is in 3 sentences." We... |
| audio-2b | tts | ok |  |  | 900.3 | 2359.4 | 138284 bytes wav -> audio-2b-tts.wav |
| d1-2b | d1 | ok |  | 6217.1 |  | 2256.8 | {"person": {"type": "noul", "noul": 0.9904885642760203}, "place": {"type": "c... |
| d1-omni-600m | d1 | ok |  | 6062.7 |  | 848.0 | {"person": {"type": "noul", "noul": 0.9999340676284783}, "place": {"type": "c... |
| omni-2b | asr | ok | 22.8 | 3174.5 |  | 2737.0 | match=True And so, my fellow Americans, ask not what your country can do for ... |
| omni-2b | text | ok | 23.3 | 370.7 |  | 2386.7 | A rainbow is a natural optical phenomenon that occurs when sunlight is refrac... |
| omni-2b | tts | ok |  |  | 916.4 | 2744.3 | 145964 bytes wav -> omni-2b-tts.wav |
| omni-2b | vision | ok | 22.3 | 7667.0 |  | 2600.6 | The image shows an urban street scene with the following objects: - **A wet a... |
| text-1-7b | text | ok | 21.4 | 427.1 |  | 1877.8 | [reasoning] We need to explain what a rainbow is in exactly three sentences. ... |
| vl-2b | text | ok | 18.8 | 434.8 |  | 2077.3 | [reasoning] The user asks: "Explain what a rainbow is in 3 sentences." So we ... |
| vl-2b | vision | ok | 18.6 | 7693.6 |  | 2290.8 | [reasoning] The user wants a list of objects in the image. I need to carefull... |

## Verdict

- Omni speech output via llama.cpp: **YES**
- Omni ASR via llama.cpp: **YES**
- Omni vision via llama.cpp: **YES**
- d1 via llama.cpp: **YES**

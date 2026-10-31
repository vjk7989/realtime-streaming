# ADR 0002: Development process and constraints
Date: 2026-11-01 · Status: Accepted (these are the user's non-negotiable rules)

1. **YAGNI.** Build only what the current phase needs.
2. **Disk:** only `G:\voice-model` may be written. Caches, models, tool venvs, and builds all live under `.cache/` and `.tools/`, which are gitignored. C: and D: are nearly full.
3. **CI:** heavy builds and model runs go in GitHub Actions on the public repo `vjk7989/realtime-streaming`, which keeps the laptop free.
4. **Multi-agent team, every phase:**
   1. A planner splits the phase into subtasks.
   2. The orchestrator (the main session) assigns work and keeps TODO, ADRs, and HANDOFF up to date.
   3. Up to 4 developer agents work in parallel on files that don't overlap.
   4. A test-writer agent writes tests, including edge cases.
   5. A test-runner agent runs them.
   6. **Any failure is fixed before the next phase starts.**
5. **Token tools:**
   - **Graphify** (at `.tools/venv`) builds a code graph once there's code to map.
   - **Headroom's** bundled `sg`, `loc`, and `diff` are used for compact searches and diffs.
   - The Headroom proxy changes Claude Code config, so it's only turned on if the user says so.

# AGENTS.md

## Mandatory first read
Before making architectural changes, read `PROJECT_SPECIFICATION.md`.

## Project identity
MercuryMesh is a multi-agent recruitment opportunity-generation system, not a standalone chatbot.

## Development rules
- Preserve Manager, Sourcing, Voice, and Evaluation agent separation.
- Design for multiple Voice Agents working in parallel.
- Persist conversation transcripts and outcomes.
- Use verified candidate facts only.
- Keep behavior versioned and reversible.
- Never introduce uncontrolled self-learning.
- Prevent duplicate outreach and respect opt-outs.
- Prefer incremental, testable changes over large rewrites.
- Do not commit secrets, recordings, model binaries, or local runtime artifacts.
- Treat PostgreSQL as the shared system of record unless explicitly changed.
- Measure changes that affect latency, conversion, reliability, or quality.
- New features should improve the probability of qualified job opportunities.

## Current stack
FastAPI, PostgreSQL, Ollama/Qwen, faster-whisper, Piper TTS, browser voice UI.

## Definition of success
A change is valuable when it improves legitimate interviews, referrals, recruiter submissions, or job opportunities without degrading accuracy, professionalism, reliability, or compliance.

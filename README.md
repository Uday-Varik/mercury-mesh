# MercuryMesh

**Autonomous agents turning conversations into opportunities.**

MercuryMesh is a multi-agent recruitment intelligence system designed to discover relevant job opportunities, identify recruiters, hiring managers, and staffing vendors, coordinate parallel outreach agents, conduct natural voice conversations, preserve every interaction, and continuously improve conversion quality over time.

## North Star

The system is optimized for real outcomes:

- Qualified recruiter and hiring-manager conversations
- Recruiter submissions
- Referrals
- Interviews
- Job opportunities
- Offers

It is **not** a single voice chatbot. MercuryMesh is designed as a coordinated autonomous recruitment workforce.

## Core Agents

- **Manager / Supervisor Agent** — orchestration, quality control, policy enforcement, prioritization, rollback.
- **Sourcing Agent** — discovers jobs, companies, recruiters, hiring managers, vendors, and verified contacts.
- **Voice Agents** — multiple parallel outbound agents that conduct conversations and move opportunities toward interviews.
- **Evaluation / Learning Agent** — scores conversations, detects mistakes, compares versions, and proposes improvements without uncontrolled self-learning.

## Current Foundation

The prototype currently uses:

- FastAPI
- PostgreSQL
- Ollama
- Qwen 2.5 3B
- faster-whisper
- Piper TTS
- Browser-based voice UI
- Resume-aware recruiter Q&A
- Session-based conversation memory
- Persistent transcript storage

## Development Principle

Every major implementation decision should answer one question:

> Does this increase the probability of creating a legitimate interview or job opportunity while preserving accuracy, professionalism, reliability, and compliance?

See [PROJECT_SPECIFICATION.md](PROJECT_SPECIFICATION.md) for the permanent source of truth.

## Status

Early-stage active development.

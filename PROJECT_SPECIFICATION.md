# MercuryMesh — Permanent Project Specification

## Mission
Build an autonomous multi-agent AI recruitment system that discovers relevant jobs and contacts, coordinates outreach, conducts natural voice conversations, preserves every interaction, and converts conversations into interviews, referrals, recruiter submissions, or other legitimate job opportunities.

MercuryMesh is **not** a single voice chatbot. It is a coordinated autonomous recruitment workforce.

## Core Agents

### Manager / Supervisor Agent
Coordinates agents, prioritizes opportunities, prevents duplicate outreach, enforces policy, reviews quality, tracks outcomes, approves improvements, and rolls back degraded behavior.

### Sourcing Agent
Discovers jobs, companies, recruiters, hiring managers, staffing vendors, and relevant verified contact information. It ranks opportunities and passes structured leads to the Manager Agent.

### Voice Agents
Multiple concurrent voice workers conduct outbound conversations, represent the candidate accurately, answer recruiter questions, qualify opportunities, request next steps, and attempt to secure interviews, referrals, or recruiter submissions.

### Evaluation / Learning Agent
Analyzes transcripts and outcomes, scores conversation quality, detects mistakes and missed opportunities, recommends improvements, and validates changes before production deployment.

## Shared Memory and Data
PostgreSQL is the initial system of record.

Persist:
- Candidate profile and verified resume facts
- Jobs
- Contacts
- Opportunities and stages
- Complete transcripts
- Call/session metadata
- Audio references when retained
- Agent/model/prompt versions
- Outcomes and follow-up actions
- Evaluation scores
- Learning experiments and rollback history

## Candidate Representation
The system should closely match Uday's natural communication style while remaining professional and factually accurate.

Never invent:
- Employers
- Skills
- Achievements
- Degrees
- Certifications
- Projects
- Work history

## Continuous Improvement
Learning must be controlled.

Required flow:
1. Save conversations and outcomes.
2. Score results.
3. Extract successful and unsuccessful patterns.
4. Propose changes.
5. Evaluate offline against a baseline.
6. Deploy only when quality improves without accuracy or safety regression.
7. Monitor production metrics.
8. Roll back degraded versions.

No uncontrolled self-modification.

## Parallelism
The architecture must support:
- Multiple sourcing tasks
- Multiple simultaneous voice agents
- Shared queues
- Task ownership
- Retry handling
- Priority scheduling
- Idempotency / duplicate prevention
- Contact cooldowns

## Conversation Lifecycle
1. Discover job.
2. Discover relevant contact.
3. Rank opportunity.
4. Assign outreach.
5. Conduct conversation.
6. Use resume, job, company, contact, and prior-history context.
7. Seek interview, referral, submission, or defined next step.
8. Save transcript and outcome.
9. Evaluate interaction.
10. Update opportunity.
11. Schedule follow-up when appropriate.

## Required Capabilities
- Resume ingestion and fact extraction
- Job matching and discovery
- Recruiter / hiring-manager / vendor discovery
- Contact enrichment and verification
- Voice calling
- Speech-to-text
- LLM reasoning
- Text-to-speech
- Conversation memory
- Call-state management
- Follow-up automation
- Email integration
- Calendar and interview scheduling
- Opportunity tracking
- Multi-agent orchestration
- Evaluation
- Versioning and rollback
- Analytics
- Audit logging

## Current Technical Foundation
- Windows + WSL2 Ubuntu
- FastAPI
- PostgreSQL 16
- Ollama
- Qwen 2.5 3B
- faster-whisper
- Piper TTS
- Browser voice UI
- Resume-aware recruiter Q&A
- Conversation/session memory

## Reliability and Safety
The system must include:
- Duplicate-outreach prevention
- Contact suppression / opt-out state
- Retry limits
- Failure handling
- Transcript quality checks
- Resume fact verification
- Agent health checks
- Version rollback
- Backups
- Audit logs
- Manual emergency stop

## Security and Privacy
- No hardcoded secrets
- Least-privilege access
- Sensitive-action logging
- Protected resume/contact/transcript data
- Retention policies for recordings and transcripts

## Compliance
Before real outbound automation is enabled, implement configurable controls for applicable calling, recording, privacy, anti-spam, opt-out, and provider requirements.

## North-Star Metrics
Optimize for:
1. Qualified conversations
2. Positive recruiter responses
3. Recruiter submissions
4. Referrals
5. Interviews scheduled
6. Qualified opportunities
7. Offers

Do not optimize primarily for raw call volume.

## MVP Definition
MVP is complete when MercuryMesh can:
1. Discover a relevant job.
2. Identify a relevant recruiter, hiring manager, or vendor.
3. Create a structured opportunity.
4. Assign it through the Manager Agent.
5. Have a Voice Agent conduct simulated or real outreach.
6. Use verified resume and conversation context.
7. Save the full transcript and outcome.
8. Update opportunity stage.
9. Schedule a follow-up.
10. Run multiple opportunities in parallel.
11. Produce an evaluation score.
12. Prevent duplicate outreach and respect opt-outs.

## Non-Negotiable Rules
1. Do not reduce MercuryMesh to a single voice agent.
2. Preserve the multi-agent architecture.
3. Preserve Manager Agent oversight.
4. Persist every conversation.
5. No uncontrolled self-learning.
6. No factual invention about the candidate.
7. Optimize for real job outcomes, not activity.
8. Prevent duplicate or uncontrolled outreach.
9. Version major behavior changes.
10. Maintain rollback capability.
11. Preserve parallel agent execution.
12. Major architectural changes must remain compatible with this specification unless this file is deliberately revised.

## Source-of-Truth Rule
This file is the permanent project-level source of truth. Development assistants and contributors should read it before making major architectural decisions.

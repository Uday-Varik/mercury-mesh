"""The candidate profile + pitch construction. Pure functions (testable).

Everything the voice agents say about the candidate comes from here, so the
pitch can never drift from the real resume.
"""
from __future__ import annotations

from . import compliance
from .models import Lead, ScriptVariant

try:
    # Your real profile. Gitignored — never committed.
    from .candidate_profile import CANDIDATE
except ImportError:
    # Public fallback so the repo works out of the box.
    from .candidate_profile_sample import CANDIDATE

TARGET_KEYWORDS = [
    "machine learning", "ml engineer", "data scientist", "data science",
    "ai engineer", "software engineer", "mlops",
]


def score_lead(lead: Lead) -> float:
    """Heuristic lead score 0..1. Higher = call sooner."""
    score = 0.45
    title = (lead.title or "").lower()
    if any(k in title for k in ("recruiter", "talent", "sourcing")):
        score += 0.25
    if "hiring manager" in title or "hiring" in title:
        score += 0.20
    if any(k in title for k in ("hr", "people operations")):
        score += 0.10
    company = (lead.company or "").lower()
    if any(k in company for k in ("staffing", "solutions", "consulting", "talent")):
        score += 0.10  # vendors/staffing firms are in-scope per the brief
    if lead.email:
        score += 0.05
    if lead.attempts >= 3:
        score -= 0.30
    return round(max(0.0, min(1.0, score)), 3)


def build_pitch(lead: Lead, variant: ScriptVariant) -> str:
    """The 30-second spoken pitch, personalized per lead."""
    c = CANDIDATE
    return variant.pitch.format(
        candidate=c["name"],
        current_role=c["current"],
        headline=c["headline"],
        highlight_1=c["highlights"][0],
        highlight_2=c["highlights"][1],
        seeking=c["seeking"],
        contact_name=(lead.name or "there").split()[0],
        company=lead.company or "your company",
        their_title=lead.title or "your team",
    )


def build_system_prompt(lead: Lead, variant: ScriptVariant) -> str:
    """Full system prompt for the Pipecat voice agent on one specific call."""
    c = CANDIDATE
    rebuttals = "\n".join(f"- If they say {k}: {v}" for k, v in variant.rebuttals.items())
    prompt = f"""You are a professional AI voice assistant calling on behalf of {c['name']}, {c['headline']}.

MANDATORY FIRST LINE (say this before anything else, verbatim in spirit):
"{compliance.disclosure_line(lead.name)}"

CALL CONTEXT
- You are calling: {lead.name} ({lead.title} at {lead.company})
- Goal, in priority order: 1) book an interview or intro call for {c['name']}, 2) get a callback / email follow-up, 3) at minimum have a real conversation and learn what roles are open.
- Candidate one-liner: {c['current']}; {c['education']}.

PITCH (adapt naturally, ~30 seconds):
{build_pitch(lead, variant)}

PROOF POINTS (use 1-2 max, only if relevant):
{chr(10).join('- ' + h for h in c['highlights'][:4])}

OBJECTION HANDLING:
{rebuttals}

RULES
- Never invent experience, dates, compensation expectations, or availability. If asked something you don't know (salary, start date), say "{c['name']} can discuss that directly — can I set up a brief intro call?"
- Keep responses short and conversational (1-3 sentences). This is a phone call, not an essay.
- If they ask to be removed from the call list, apologize, call the add_to_dnc tool, and end politely.
- If they agree to an interview or callback, call the matching tool with the details, confirm the details back, thank them, and end the call.
- When the call ends for any reason, call end_call_with_outcome with your honest assessment.

TOOLS: end_call_with_outcome, book_interview, request_callback, add_to_dnc.
"""
    compliance.assert_disclosure_present(prompt)
    return prompt


def default_variants() -> list[ScriptVariant]:
    """Three starting pitch variants. The learning loop will crown a winner."""
    return [
        ScriptVariant(
            name="results_opener",
            opener="metrics-led",
            pitch=("So {candidate} is currently {current_role}, where he {highlight_1}. "
                   "He also {highlight_2}. He's exploring {seeking} "
                   "and your team at {company} looked like a genuinely strong fit — "
                   "do you have two minutes?"),
            rebuttals={
                '"not hiring"': '"Totally understand — would you be open to a 15-minute intro anyway, in case something opens up next quarter?"',
                '"send a resume"': '"Happy to — what\'s the best email? And is there a specific role I should point him at?"',
                '"who is this"': '"I\'m an AI assistant calling for Uday Varikuppala, a machine learning engineer at FedEx — I said that up top, sorry if it went by fast."',
            },
        ),
        ScriptVariant(
            name="problem_opener",
            opener="pain-led",
            pitch=("Quick question, {contact_name} — is {their_title} hiring for ML or data roles at {company} right now? "
                   "The reason I ask: {candidate} ({headline}) just shipped a real-time ML system doing {highlight_1}, "
                   "and he's looking at {seeking}. Sound worth a brief intro?"),
            rebuttals={
                '"not hiring"': '"Got it — even a short intro call could be useful for your pipeline. Fifteen minutes sometime next week?"',
                '"send a resume"': '"Of course — best email? I\'ll also note which team it\'s for."',
                '"too junior/senior"': '"Fair — what level are you hiring at? He\'s flexible on scope and happy to start with a conversation."',
            },
        ),
        ScriptVariant(
            name="referral_opener",
            opener="warm-style",
            pitch=("Hi {contact_name}, I'll keep this brief. {candidate} is {headline} — currently {current_role}. "
                   "A couple of proof points: {highlight_1}, and {highlight_2}. "
                   "He's exploring {seeking}, and {company} stood out. "
                   "Worth a 15-minute intro call?"),
            rebuttals={
                '"not hiring"': '"No problem at all — if anything opens up, can I send his profile for your files?"',
                '"send a resume"': '"Absolutely — which email should I use?"',
                '"call back later"': '"Happy to — what day/time works, and is this the best number?"',
            },
        ),
    ]

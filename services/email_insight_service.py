from __future__ import annotations

import random
from sqlalchemy import select

from db.database import session_scope
from models.orm import ScholarshipEntry


def get_scholarship_details(scholarship_id: int | None) -> dict:
    if not scholarship_id:
        return {}

    with session_scope() as db:
        row = db.get(ScholarshipEntry, scholarship_id)
        if not row:
            return {}

        return {
            "title": row.title,
            "provider": row.provider,
            "country": row.country,
            "degree_level": row.degree_level,
            "deadline": row.deadline,
            "summary": row.summary,
            "source_url": row.source_url,
            "credibility": row.credibility,
        }


def scholarship_insight_text(
    *,
    name: str,
    scholarship: dict,
    next_step: str,
) -> tuple[str, str]:
    title = scholarship.get("title") or "your selected scholarship"
    provider = scholarship.get("provider") or "the scholarship provider"
    country = scholarship.get("country") or "your destination country"
    deadline = scholarship.get("deadline") or "not listed"
    summary = scholarship.get("summary") or "No summary is currently available."
    source_url = scholarship.get("source_url") or ""

    rotating_tip = random.choice([
        "Scholarship applications are usually strongest when documents, references, and essays are prepared early rather than near the deadline.",
        "A good scholarship application should clearly connect your academic background, future goals, and the scholarship’s purpose.",
        "Even when you meet the basic eligibility rules, your supporting documents and written answers often decide how competitive your application feels.",
        "For Pakistani students, preparing attestations, transcripts, passport validity, and references early can prevent delays later in the visa stage.",
    ])

    subject = f"Scholarship insight: {title}"

    body = f"""Hi {name},

You selected:

{title}

Provider:
{provider}

Destination:
{country}

Deadline:
{deadline}

What VisaForge knows about this scholarship:
{summary}

Your current next step:
{next_step}

Insight:
{rotating_tip}

What to do now:
- Review the official scholarship source.
- Check the eligibility criteria again.
- Prepare academic documents and references early.
- Keep your Pakistan-side documents ready where required.

Official source:
{source_url}

— VisaForge"""

    return subject, body


def destination_insight_text(
    *,
    name: str,
    country: str | None,
    next_step: str,
) -> tuple[str, str]:
    country = country or "your selected destination"

    country_tips = {
        "UK": [
            "For the UK, the CAS is one of the most important visa-stage documents. Without it, the Student visa application cannot properly move forward.",
            "UK student routes often require careful timing between offer, CAS, funds evidence, TB test if applicable, and biometrics.",
            "For Pakistani students applying to the UK, document readiness matters because delays in transcripts, references, or attestations can affect the application timeline.",
        ],
        "Canada": [
            "For Canada, the study permit process depends heavily on proof of admission, financial readiness, and a clear study plan.",
            "Canadian applications are stronger when the student can clearly explain why the chosen program fits their education and career path.",
            "For Pakistani students, financial documents and sponsor explanations should be prepared carefully for a Canada study permit route.",
        ],
        "Germany": [
            "For Germany, students often need to plan around blocked account requirements, admission letters, and sometimes APS-related preparation depending on the route.",
            "German student visa preparation can take time because financial proof, academic documents, and appointment availability must align.",
            "For Pakistani students, academic document consistency and financial readiness are especially important for Germany routes.",
        ],
    }

    tip = random.choice(country_tips.get(country, [
        "Your destination route depends on eligibility, documents, funding, and timing. Review your route plan regularly."
    ]))

    subject = f"VisaForge insight for {country}"

    body = f"""Hi {name},

Your selected destination is:

{country}

Insight:
{tip}

Your current next step:
{next_step}

Recommended focus:
- Keep your profile updated.
- Review eligibility gaps.
- Prepare documents early.
- Use your route plan to track progress.
- Ask the AI assistant if any step feels unclear.

— VisaForge"""

    return subject, body
from __future__ import annotations


def password_reset_email(name: str, reset_link: str) -> tuple[str, str]:
    return (
        "Reset your VisaForge password",
        f"""Hi {name},

You requested a password reset for your VisaForge account.

Reset your password here:
{reset_link}

This link expires in 1 hour.

If you did not request this, you can ignore this email.

— VisaForge"""
    )


def journey_reminder_email(name: str, next_step: str) -> tuple[str, str]:
    return (
        "Continue your VisaForge journey",
        f"""Hi {name},

You have not completed your VisaForge journey yet.

Your next step:
{next_step}

Log in to continue your profile, eligibility check, scholarship selection, or route plan.

— VisaForge"""
    )


def platform_tip_email(name: str) -> tuple[str, str]:
    return (
        "What VisaForge can help you with",
        f"""Hi {name},

VisaForge helps Pakistani students plan their study-abroad journey using:

- Profile-based eligibility checks
- Scholarship matching
- Country-specific route plans
- Pakistan preparation guidance
- Document OCR and review support
- AI explanations for complex steps

Log in anytime to continue your journey.

— VisaForge"""
    )


def destination_insight_email(name: str, country: str) -> tuple[str, str]:
    country = country or "your selected destination"
    return (
        f"Important guidance for {country}",
        f"""Hi {name},

Based on your selected destination, VisaForge can help you understand the key preparation steps for {country}.

This may include:
- visa route planning
- required documents
- scholarship preparation
- Pakistan-specific steps such as HEC, IBCC, MOFA, passport readiness, and police clearance where relevant

Log in to review your route plan and next actions.

— VisaForge"""
    )


def scholarship_insight_email(name: str, scholarship_title: str | None) -> tuple[str, str]:
    title = scholarship_title or "your selected scholarship"
    return (
        f"Scholarship guidance: {title}",
        f"""Hi {name},

VisaForge noticed that you selected:

{title}

Make sure you review:
- eligibility criteria
- application deadline
- required academic documents
- references or essays if required
- visa preparation steps after selection

Log in to compare your readiness and continue your route plan.

— VisaForge"""
    )


def important_notice_email(name: str, message: str) -> tuple[str, str]:
    return (
        "Important VisaForge notice",
        f"""Hi {name},

{message}

— VisaForge"""
    )
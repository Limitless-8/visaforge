from __future__ import annotations

from sqlalchemy import select

from db.database import session_scope
from models.orm import ScholarshipEntry
from models.user import User
from services.auth_service import list_users
from services.email_service import send_email
from services.email_templates import (
    destination_insight_email,
    important_notice_email,
    journey_reminder_email,
    platform_tip_email,
    scholarship_insight_email,
)
from services.journey_service import compute_journey

from services.email_insight_service import (
    get_scholarship_details,
    scholarship_insight_text,
    destination_insight_text,
)


def _selected_scholarship_title(scholarship_id: int | None) -> str | None:
    if not scholarship_id:
        return None

    with session_scope() as db:
        row = db.get(ScholarshipEntry, scholarship_id)
        return row.title if row else None


def _eligible_users(audience: str, country: str | None = None) -> list[User]:
    users = [u for u in list_users() if not u.is_admin() and u.is_active]

    selected: list[User] = []

    for user in users:
        journey = compute_journey(user.id)

        if audience == "all":
            selected.append(user)

        elif audience == "incomplete_journey":
            if journey.progress_ratio() < 1:
                selected.append(user)

        elif audience == "destination_country":
            if country and journey.destination_country == country:
                selected.append(user)

        elif audience == "selected_scholarship":
            if journey.scholarship_selected:
                selected.append(user)

        elif audience == "documents_started":
            if journey.documents_started:
                selected.append(user)

    return selected


def send_admin_email_campaign(
    *,
    audience: str,
    email_type: str,
    country: str | None = None,
    custom_message: str | None = None,
) -> dict:
    users = _eligible_users(audience, country=country)

    sent = 0
    failed = 0

    for user in users:
        journey = compute_journey(user.id)

        if email_type == "journey_reminder":
            next_step, _ = journey.current_step()
            subject, body = journey_reminder_email(user.name, next_step)

        elif email_type == "platform_tip":
            subject, body = platform_tip_email(user.name)

        elif email_type == "destination_insight":
            if not journey.destination_country:
                failed += 1
                continue

            next_step, _ = journey.current_step()
            subject, body = destination_insight_text(
                name=user.name,
                country=journey.destination_country,
                next_step=next_step,
            )

        elif email_type == "scholarship_insight":
            if not journey.scholarship_selected or not journey.selected_scholarship_id:
                failed += 1
                continue

            next_step, _ = journey.current_step()
            scholarship = get_scholarship_details(
                journey.selected_scholarship_id
            )

            if not scholarship:
                failed += 1
                continue

            subject, body = scholarship_insight_text(
                name=user.name,
                scholarship=scholarship,
                next_step=next_step,
            )

        elif email_type == "important_notice":
            subject, body = important_notice_email(
                user.name,
                custom_message or "Please log in to check your VisaForge account.",
            )

        else:
            failed += 1
            continue

        ok = send_email(user.email, subject, body)
        if ok:
            sent += 1
        else:
            failed += 1

    return {
        "targeted": len(users),
        "sent": sent,
        "failed": failed,
    }
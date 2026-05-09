from sqlalchemy import select
from db.database import session_scope
from models.user import User
from services.journey_service import compute_journey


STAGE_ORDER = [
    "Not Started",
    "Profile Complete",
    "Eligibility Complete",
    "Scholarship Selected",
    "Route Generated",
    "Documents Started",
    "Completed",
]


def _journey_stage(journey):
    if journey.documents_started:
        return "Documents Started"

    if journey.route_plan_generated:
        return "Route Generated"

    if journey.scholarship_selected:
        return "Scholarship Selected"

    if journey.eligibility_completed:
        return "Eligibility Complete"

    if journey.profile_complete:
        return "Profile Complete"

    return "Not Started"


def _completion_percentage(journey):
    score = 0

    if journey.profile_complete:
        score += 20

    if journey.eligibility_completed:
        score += 20

    if journey.scholarship_selected:
        score += 20

    if journey.route_plan_generated:
        score += 20

    if journey.documents_started:
        score += 20

    return score


def get_user_funnel_stats():
    stats = {
        "total_users": 0,
        "profile_complete": 0,
        "eligibility_completed": 0,
        "scholarship_selected": 0,
        "route_generated": 0,
        "documents_started": 0,
        "completed": 0,
    }

    stage_distribution = {
        stage: 0 for stage in STAGE_ORDER
    }

    with session_scope() as db:
        users = [
            u for u in db.scalars(select(User))
            if not u.is_admin()
        ]

    stats["total_users"] = len(users)

    for user in users:
        j = compute_journey(user.id)

        stage = _journey_stage(j)
        stage_distribution[stage] += 1

        if j.profile_complete:
            stats["profile_complete"] += 1

        if j.eligibility_completed:
            stats["eligibility_completed"] += 1

        if j.scholarship_selected:
            stats["scholarship_selected"] += 1

        if j.route_plan_generated:
            stats["route_generated"] += 1

        if j.documents_started:
            stats["documents_started"] += 1

        if _completion_percentage(j) == 100:
            stats["completed"] += 1

    stats["stage_distribution"] = stage_distribution

    return stats


def get_user_progress_table():
    rows = []

    with session_scope() as db:
        users = [
            u for u in db.scalars(select(User))
            if not u.is_admin()
        ]

    for user in users:
        j = compute_journey(user.id)

        completion = _completion_percentage(j)

        rows.append({
            "Name": user.name,
            "Email": user.email,
            "Destination": j.destination_country or "Not Selected",
            "Journey Stage": _journey_stage(j),
            "Completion %": completion,
            "Profile": "Complete" if j.profile_complete else "Pending",
            "Eligibility": "Complete" if j.eligibility_completed else "Pending",
            "Scholarship": "Selected" if j.scholarship_selected else "Pending",
            "Route Plan": "Generated" if j.route_plan_generated else "Pending",
            "Documents": "Started" if j.documents_started else "Pending",
        })

    rows.sort(
        key=lambda x: x["Completion %"],
        reverse=True,
    )

    return rows


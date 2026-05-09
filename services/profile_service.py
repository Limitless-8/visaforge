"""
services/profile_service.py
---------------------------
CRUD for user profiles. Thin wrapper around SQLAlchemy so the UI layer
never touches the ORM directly (easier to swap for FastAPI later).

v0.2 changes:
- Writes `offer_letter_status` and `proof_of_funds_status`, and keeps
  the legacy `has_offer_letter` / `has_proof_of_funds` booleans in sync
  so older code and saved records keep working.
- Writes `previous_field_of_study`.
- `field_of_study` accepts a list (multiselect) or comma-separated string.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import select

from db.database import session_scope
from models.orm import UserProfile
from models.schemas import ProfileIn
from utils.logger import get_logger
from utils.reference_data import (
    FUNDS_STATUS_STRENGTH,
    OFFER_STATUS_STRENGTH,
)

log = get_logger(__name__)


# --- back-compat helpers --------------------------------------------------

def _offer_status_from_bool(has: bool) -> str:
    """Map legacy bool → reasonable status default."""
    return "Unconditional offer received" if has else "Not yet applied"


def _funds_status_from_bool(has: bool) -> str:
    return "Fully prepared" if has else "Not prepared"


def _bool_from_offer_status(status: Optional[str]) -> bool:
    """Legacy boolean = True only when evidence is 'strong'."""
    return OFFER_STATUS_STRENGTH.get(status or "", "none") == "strong"


def _bool_from_funds_status(status: Optional[str]) -> bool:
    return FUNDS_STATUS_STRENGTH.get(status or "", "none") == "strong"


def _hydrate_legacy_profile(p: UserProfile) -> None:
    """If a profile was saved before v0.2, fill in the new status fields
    from the old booleans so the rest of the app sees consistent data."""
    if not p.offer_letter_status:
        p.offer_letter_status = _offer_status_from_bool(bool(p.has_offer_letter))
    if not p.proof_of_funds_status:
        p.proof_of_funds_status = _funds_status_from_bool(
            bool(p.has_proof_of_funds)
        )


# --- CRUD -----------------------------------------------------------------

def create_or_update_profile(
    data: ProfileIn,
    profile_id: Optional[int] = None,
    *,
    user_id: Optional[int] = None,
) -> int:
    """Create a new profile, or update an existing one. Returns the id.

    `user_id` — if provided, stamped onto new profiles for ownership.
    On updates, we never overwrite an existing owner.
    """
    payload = data.model_dump()

    # Derive legacy booleans from status fields for back-compat.
    payload["has_offer_letter"] = _bool_from_offer_status(
        payload.get("offer_letter_status")
    )
    payload["has_proof_of_funds"] = _bool_from_funds_status(
        payload.get("proof_of_funds_status")
    )

    with session_scope() as db:
        if profile_id is not None:
            profile = db.get(UserProfile, profile_id)
            if profile is None:
                raise ValueError(f"Profile {profile_id} not found")
        else:
            profile = UserProfile(
                full_name=payload["full_name"],
                nationality=payload["nationality"],
                country_of_residence=payload["country_of_residence"],
                destination_country=payload["destination_country"],
            )
            if user_id is not None:
                profile.user_id = user_id
            db.add(profile)

        for k, v in payload.items():
            # Guard against schema drift: only set attributes the ORM knows.
            if hasattr(profile, k):
                setattr(profile, k, v)

        # On updates: only set user_id if the profile is currently unowned
        # and a user_id was supplied.
        if user_id is not None and profile.user_id is None:
            profile.user_id = user_id

        db.flush()
        log.info(
            "Saved profile id=%s name=%s user_id=%s",
            profile.id, profile.full_name, profile.user_id,
        )
        return profile.id


def get_profile(profile_id: int) -> Optional[UserProfile]:
    with session_scope() as db:
        p = db.get(UserProfile, profile_id)
        if p is None:
            return None
        _hydrate_legacy_profile(p)
        db.expunge(p)
        return p


def list_profiles() -> list[UserProfile]:
    with session_scope() as db:
        rows = list(db.scalars(select(UserProfile).order_by(
            UserProfile.created_at.desc()
        )))
        for r in rows:
            _hydrate_legacy_profile(r)
            db.expunge(r)
        return rows


def list_profiles_for_user(user_id: int) -> list[UserProfile]:
    """Return only the profiles owned by the given user."""
    with session_scope() as db:
        rows = list(db.scalars(
            select(UserProfile)
            .where(UserProfile.user_id == user_id)
            .order_by(UserProfile.created_at.desc())
        ))
        for r in rows:
            _hydrate_legacy_profile(r)
            db.expunge(r)
        return rows


def delete_profile(profile_id: int) -> bool:
    with session_scope() as db:
        p = db.get(UserProfile, profile_id)
        if not p:
            return False
        db.delete(p)
        return True

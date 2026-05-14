"""
services/auth_service.py
------------------------
Authentication service. Thin wrapper around bcrypt + SQLAlchemy.

Responsibilities:
  * register_user(...)        â†’ create a new account (returns User or raises)
  * authenticate(email, pw)   â†’ verify credentials â†’ return User or None
  * get_current_user()        â†’ read from Streamlit session_state
  * login_session(user)       â†’ write user identity into session_state
  * logout_session()          â†’ clear auth keys from session_state
  * is_logged_in() / is_admin()
  * promote_to_admin(email)
  * seed_admin_from_env()     â†’ idempotent first-admin bootstrap
  * list_users() / get_user() / deactivate_user()

All password handling goes through bcrypt. Plaintext never leaves this file
except in memory during a single call.
"""

from __future__ import annotations

import os
import re
from datetime import datetime
from typing import Optional

import bcrypt
from sqlalchemy import select

from config.settings import settings
from db.database import session_scope
from models.user import AdminAuditLog, User
from utils.helpers import utcnow
from utils.logger import get_logger

import secrets
from datetime import timedelta
from services.email_service import send_email

log = get_logger(__name__)


# ---------- session keys (kept constant so pages import them) -------------

SESSION_USER_KEY = "auth_user"       # full dict of the logged-in user
SESSION_ROLE_KEY = "auth_role"       # "user" | "admin" | "super_admin"
SESSION_USER_ID_KEY = "auth_user_id"


# ---------- validation helpers --------------------------------------------

_EMAIL_RX = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class AuthError(Exception):
    """Generic auth failure, safe to surface to the UI."""


def _normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def _validate_password(password: str) -> None:
    if not password or len(password) < 8:
        raise AuthError("Password must be at least 8 characters long.")
    if len(password) > 128:
        raise AuthError("Password must be 128 characters or fewer.")


def _validate_email(email: str) -> None:
    if not email or not _EMAIL_RX.match(email):
        raise AuthError("Please provide a valid email address.")


# ---------- hashing -------------------------------------------------------

def _hash_password(password: str) -> str:
    # bcrypt has a 72-byte ceiling; our 128-char limit is already tighter
    # once UTF-8 expands, but guard anyway.
    return bcrypt.hashpw(
        password.encode("utf-8")[:72], bcrypt.gensalt(rounds=12)
    ).decode("utf-8")


def _verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(
            password.encode("utf-8")[:72], hashed.encode("utf-8")
        )
    except (ValueError, TypeError):
        # Malformed hash or bad input â€” fail closed.
        return False


# ---------- CRUD / auth flows ---------------------------------------------

def register_user(
    *,
    name: str,
    email: str,
    password: str,
    role: str = "user",
) -> User:
    """Create a new user. Raises AuthError on validation/duplication issues."""
    name = (name or "").strip()
    email = _normalize_email(email)
    if not name:
        raise AuthError("Please provide your name.")
    _validate_email(email)
    _validate_password(password)
    if role not in ("user", "admin", "super_admin"):
        raise AuthError("Invalid role.")

    with session_scope() as db:
        existing = db.scalar(select(User).where(User.email == email))
        if existing is not None:
            raise AuthError("An account with that email already exists.")

        user = User(
            name=name,
            email=email,
            password_hash=_hash_password(password),
            role=role,
            is_active=True,
        )
        db.add(user)
        db.flush()
        db.expunge(user)
        log.info("Registered user id=%s email=%s role=%s",
                 user.id, user.email, user.role)
        return user


def authenticate(email: str, password: str) -> Optional[User]:
    """Return the User on success, or None on any failure.

    We deliberately return None for both 'no such user' and 'wrong password'
    so callers can present a single generic message â€” this avoids
    account-enumeration leaks.
    """
    email = _normalize_email(email)
    if not email or not password:
        return None

    with session_scope() as db:
        user = db.scalar(select(User).where(User.email == email))
        if user is None or not user.is_active:
            # Still compute a hash to keep timing roughly uniform.
            _verify_password(password, "$2b$12$" + "a" * 53)
            return None
        if not _verify_password(password, user.password_hash):
            return None
        user.last_login_at = utcnow()
        db.flush()
        db.expunge(user)
        log.info("Login ok: id=%s email=%s", user.id, user.email)
        return user


def change_password(user_id: int, old_password: str, new_password: str) -> None:
    _validate_password(new_password)
    with session_scope() as db:
        user = db.get(User, user_id)
        if user is None or not user.is_active:
            raise AuthError("Account not found.")
        if not _verify_password(old_password, user.password_hash):
            raise AuthError("Current password is incorrect.")
        user.password_hash = _hash_password(new_password)


def promote_to_admin(email: str) -> bool:
    """Promote an existing user to admin. Returns True if changed."""
    email = _normalize_email(email)
    with session_scope() as db:
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            return False
        if user.role in ("admin", "super_admin"):
            return False
        user.role = "admin"
        log.info("Promoted to admin: id=%s email=%s", user.id, user.email)
        return True


def deactivate_user(user_id: int) -> bool:
    with session_scope() as db:
        user = db.get(User, user_id)
        if user is None:
            return False
        user.is_active = False
        return True


def list_users() -> list[User]:
    with session_scope() as db:
        rows = list(db.scalars(
            select(User).order_by(User.created_at.desc())
        ))
        for r in rows:
            db.expunge(r)
        return rows


def get_user(user_id: int) -> Optional[User]:
    with session_scope() as db:
        u = db.get(User, user_id)
        if u is None:
            return None
        db.expunge(u)
        return u


def get_user_by_email(email: str) -> Optional[User]:
    email = _normalize_email(email)
    with session_scope() as db:
        u = db.scalar(select(User).where(User.email == email))
        if u is None:
            return None
        db.expunge(u)
        return u


# ---------- session helpers (Streamlit) -----------------------------------

def login_session(user: User) -> None:
    """Write the user into Streamlit session state and persist across refresh."""
    import streamlit as st

    user_data = user.public_dict()

    st.session_state[SESSION_USER_KEY] = user_data
    st.session_state[SESSION_ROLE_KEY] = user.role
    st.session_state[SESSION_USER_ID_KEY] = user.id

    # hard persistence across refresh
    st.session_state["_persist_login"] = {
        "user": user_data,
        "role": user.role,
        "user_id": user.id,
    }


def logout_session() -> None:
    import streamlit as st

    for k in (
        SESSION_USER_KEY,
        SESSION_ROLE_KEY,
        SESSION_USER_ID_KEY,
        "_persist_login",
        "profile_id",
        "eligibility_report",
    ):
        st.session_state.pop(k, None)


def get_current_user() -> Optional[dict]:
    import streamlit as st

    user = st.session_state.get(SESSION_USER_KEY)

    if user is not None:
        uid = st.session_state.get(SESSION_USER_ID_KEY) or user.get("id")
        if uid is not None:
            try:
                st.query_params["vf_user_id"] = str(uid)
            except Exception:
                pass
        return user

    raw_user_id = st.query_params.get("vf_user_id")
    if isinstance(raw_user_id, list):
        raw_user_id = raw_user_id[0] if raw_user_id else None

    if not raw_user_id:
        return None

    try:
        user_id = int(raw_user_id)
    except (TypeError, ValueError):
        return None

    try:
        with session_scope() as db:
            restored = db.get(User, user_id)
            if restored is None or not getattr(restored, "is_active", True):
                return None

            st.session_state[SESSION_USER_KEY] = restored.public_dict()
            st.session_state[SESSION_ROLE_KEY] = restored.role
            st.session_state[SESSION_USER_ID_KEY] = restored.id

            try:
                st.query_params["vf_user_id"] = str(restored.id)
            except Exception:
                pass

            return st.session_state[SESSION_USER_KEY]
    except Exception:
        return None


def current_user_id() -> Optional[int]:
    import streamlit as st
    if st.session_state.get(SESSION_USER_ID_KEY) is None:
        get_current_user()
    return st.session_state.get(SESSION_USER_ID_KEY)


def is_logged_in() -> bool:
    return get_current_user() is not None


def is_admin() -> bool:
    import streamlit as st
    return (st.session_state.get(SESSION_ROLE_KEY) or "").lower() in {"admin", "super_admin"}


def is_super_admin() -> bool:
    import streamlit as st
    return (st.session_state.get(SESSION_ROLE_KEY) or "").lower() == "super_admin"



def _root_super_admin_email() -> str:
    """Return the protected/root super admin email.

    This is normally the ADMIN_EMAIL used to bootstrap the first admin.
    Fallback keeps local/demo deployments protected.
    """
    email = os.getenv("ADMIN_EMAIL", "").strip().lower()
    if not email:
        try:
            email = (settings.as_dict().get("ADMIN_EMAIL") or "").strip().lower()
        except Exception:
            email = ""
    return email or "admin@visaforge.local"


def _is_root_super_admin_email(email: str | None) -> bool:
    return (email or "").strip().lower() == _root_super_admin_email()


# ---------- super-admin account management --------------------------------

def _public_user_row(user: User) -> dict:
    return user.public_dict()


def count_active_super_admins() -> int:
    with session_scope() as db:
        rows = list(db.scalars(
            select(User).where(
                (User.role == "super_admin") & (User.is_active.is_(True))
            )
        ))
        return len(rows)


def log_admin_action(
    *,
    actor_user_id: int | None,
    actor_email: str | None,
    action: str,
    target_user_id: int | None = None,
    target_email: str | None = None,
    details: str | None = None,
) -> None:
    with session_scope() as db:
        db.add(
            AdminAuditLog(
                actor_user_id=actor_user_id,
                actor_email=actor_email,
                action=action,
                target_user_id=target_user_id,
                target_email=target_email,
                details=details,
            )
        )


def list_account_management_users() -> list[dict]:
    with session_scope() as db:
        rows = list(db.scalars(select(User).order_by(User.created_at.desc())))
        return [_public_user_row(row) for row in rows]


def list_admin_audit_logs(limit: int = 100) -> list[dict]:
    with session_scope() as db:
        rows = list(db.scalars(
            select(AdminAuditLog)
            .order_by(AdminAuditLog.created_at.desc())
            .limit(limit)
        ))
        return [
            {
                "id": row.id,
                "actor_user_id": row.actor_user_id,
                "actor_email": row.actor_email,
                "action": row.action,
                "target_user_id": row.target_user_id,
                "target_email": row.target_email,
                "details": row.details,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in rows
        ]


def create_admin_account(
    *,
    actor_user_id: int | None,
    actor_email: str | None,
    name: str,
    email: str,
    password: str,
    role: str,
) -> User:
    if role not in ("admin", "super_admin"):
        raise AuthError("Only admin or super admin accounts can be created here.")

    if role == "super_admin" and not _is_root_super_admin_email(actor_email):
        raise AuthError("Only the root super admin can create another super admin account.")

    user = register_user(
        name=name,
        email=email,
        password=password,
        role=role,
    )

    log_admin_action(
        actor_user_id=actor_user_id,
        actor_email=actor_email,
        action="create_account",
        target_user_id=user.id,
        target_email=user.email,
        details=f"Created {role} account.",
    )
    return user


def update_user_role(
    *,
    actor_user_id: int | None,
    actor_email: str | None,
    target_user_id: int,
    new_role: str,
) -> bool:
    if new_role not in ("user", "admin", "super_admin"):
        raise AuthError("Invalid role selected.")

    actor_is_root = _is_root_super_admin_email(actor_email)

    with session_scope() as db:
        target = db.get(User, target_user_id)
        if target is None:
            raise AuthError("Target account not found.")

        old_role = target.role or "user"
        target_email = target.email

        if _is_root_super_admin_email(target_email) and new_role != "super_admin":
            raise AuthError("The root super admin account cannot be demoted.")

        if old_role == "super_admin" and new_role != "super_admin" and not actor_is_root:
            raise AuthError("Only the root super admin can demote another super admin.")

        if new_role == "super_admin" and old_role != "super_admin" and not actor_is_root:
            raise AuthError("Only the root super admin can promote accounts to super admin.")

        if old_role == "super_admin" and new_role != "super_admin":
            active_super_admins = db.scalars(
                select(User).where(
                    (User.role == "super_admin") & (User.is_active.is_(True))
                )
            ).all()
            if len(active_super_admins) <= 1:
                raise AuthError("You cannot demote the only active super admin.")

        target.role = new_role

    log_admin_action(
        actor_user_id=actor_user_id,
        actor_email=actor_email,
        action="change_role",
        target_user_id=target_user_id,
        target_email=target_email,
        details=f"Role changed from {old_role} to {new_role}.",
    )
    return True


def set_user_active_status(
    *,
    actor_user_id: int | None,
    actor_email: str | None,
    target_user_id: int,
    active: bool,
) -> bool:
    if actor_user_id == target_user_id and not active:
        raise AuthError("You cannot deactivate your own account.")

    actor_is_root = _is_root_super_admin_email(actor_email)

    with session_scope() as db:
        target = db.get(User, target_user_id)
        if target is None:
            raise AuthError("Target account not found.")

        target_email = target.email

        if _is_root_super_admin_email(target_email) and not active:
            raise AuthError("The root super admin account cannot be deactivated.")

        if target.role == "super_admin" and not active and not actor_is_root:
            raise AuthError("Only the root super admin can deactivate another super admin.")

        if target.role == "super_admin" and not active:
            active_super_admins = db.scalars(
                select(User).where(
                    (User.role == "super_admin") & (User.is_active.is_(True))
                )
            ).all()
            if len(active_super_admins) <= 1:
                raise AuthError("You cannot deactivate the only active super admin.")

        target.is_active = bool(active)

    log_admin_action(
        actor_user_id=actor_user_id,
        actor_email=actor_email,
        action="activate_account" if active else "deactivate_account",
        target_user_id=target_user_id,
        target_email=target_email,
        details=f"Account active status set to {active}.",
    )
    return True



# ---------- bootstrap -----------------------------------------------------

def seed_admin_from_env() -> Optional[int]:
    """If ADMIN_EMAIL / ADMIN_PASSWORD are set and no user with that email
    exists yet, create one. Returns new user id if created, else None."""
    email = os.getenv("ADMIN_EMAIL", "").strip().lower() \
        or (settings.as_dict().get("ADMIN_EMAIL") or "").strip().lower()
    password = os.getenv("ADMIN_PASSWORD", "")

    # Fallback: read via Streamlit secrets if available
    if not email or not password:
        try:
            import streamlit as st
            email = email or (st.secrets.get("ADMIN_EMAIL", "") if hasattr(st, "secrets") else "")
            password = password or (st.secrets.get("ADMIN_PASSWORD", "") if hasattr(st, "secrets") else "")
        except Exception:
            pass

    email = (email or "").strip().lower()
    if not email or not password:
        return None

    with session_scope() as db:
        existing = db.scalar(select(User).where(User.email == email))
        if existing is not None:
            if existing.role != "super_admin":
                existing.role = "super_admin"
                log.info("Existing user %s upgraded to super_admin via env.", email)
            return None

    try:
        user = register_user(
            name="VisaForge Admin",
            email=email,
            password=password,
            role="super_admin",
        )
        log.info("Seeded initial super admin: %s", email)
        return user.id
    except AuthError as e:
        log.warning("Could not seed admin: %s", e)
        return None

# ---------- password_reset -----------------------------------------------------

def create_password_reset(email: str):
    user = get_user_by_email(email)
    if not user:
        return False

    token = secrets.token_urlsafe(32)
    expiry = utcnow() + timedelta(hours=1)

    with session_scope() as db:
        u = db.get(User, user.id)
        u.reset_token = token
        u.reset_token_expires_at = expiry

    reset_link = f"http://localhost:8501/0_Reset_Password?token={token}"

    send_email(
        user.email,
        "Reset your VisaForge password",
        f"Hi {user.name},\n\nClick below to reset your password:\n{reset_link}\n\nThis link expires in 1 hour."
    )

    return True


def reset_password_with_token(token: str, new_password: str):
    _validate_password(new_password)

    with session_scope() as db:
        user = db.scalar(select(User).where(User.reset_token == token))

        if not user:
            raise AuthError("Invalid reset link.")

        if not user.reset_token_expires_at or user.reset_token_expires_at < utcnow():
            raise AuthError("Reset link expired.")

        user.password_hash = _hash_password(new_password)
        user.reset_token = None
        user.reset_token_expires_at = None


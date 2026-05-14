"""
models/user.py
--------------
User ORM entity + related types.

Kept in its own file per the auth upgrade spec, but imported into
`models.__init__` so downstream code can do `from models import User`.

Schema:
  id            INTEGER PK
  name          VARCHAR(200)
  email         VARCHAR(200) UNIQUE, lowercased
  password_hash VARCHAR(200)     — bcrypt hash
  role          VARCHAR(20)      — "user" | "admin"
  is_active     BOOLEAN          — soft-disable without deletion
  created_at    DATETIME
  last_login_at DATETIME NULL
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from models.orm import Base
from utils.helpers import utcnow


UserRole = Literal["user", "admin", "super_admin"]


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(20), default="user")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )

    def is_admin(self) -> bool:
        return (self.role or "").lower() in {"admin", "super_admin"}

    def is_super_admin(self) -> bool:
        return (self.role or "").lower() == "super_admin"

    def public_dict(self) -> dict:
        """Safe-to-render dict (no password hash)."""
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "role": self.role,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat()
            if self.created_at else None,
            "last_login_at": self.last_login_at.isoformat()
            if self.last_login_at else None,
        }


class AdminAuditLog(Base):
    """Audit trail for super-admin account management actions."""

    __tablename__ = "admin_audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor_user_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    actor_email: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    action: Mapped[str] = mapped_column(String(80))
    target_user_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    target_email: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

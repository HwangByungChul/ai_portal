from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal
from uuid import UUID


@dataclass(frozen=True)
class AuthContext:
    session_id: UUID
    user_id: UUID
    tenant_id: UUID | None
    effective_role: str | None
    csrf_secret: str = field(repr=False)


@dataclass(frozen=True)
class LoginResult:
    session_token: str = field(repr=False)
    csrf_token: str = field(repr=False)
    user_id: UUID
    display_name: str
    expires_at: datetime


@dataclass(frozen=True)
class SessionView:
    session_id: UUID
    user_id: UUID
    display_name: str
    csrf_secret: str = field(repr=False)
    expires_at: datetime
    auth_revision: int


@dataclass(frozen=True)
class TenantView:
    tenant_id: UUID
    display_name: str
    effective_role: Literal['USER', 'TADMIN', 'PADMIN']
    can_manage: bool


@dataclass(frozen=True)
class MembershipView:
    user_id: UUID
    display_name: str
    role: Literal['USER', 'TADMIN', 'PADMIN']
    active: bool
    revision: int


@dataclass(frozen=True)
class MemberPage:
    items: list[MembershipView]
    next_cursor: UUID | None

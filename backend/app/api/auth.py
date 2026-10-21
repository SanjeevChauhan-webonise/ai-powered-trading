import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Response
from sqlalchemy import delete, select

from app.api.deps import Cfg, CurrentUser, Db
from app.core.models import AuthSession, User
from app.core.security import DUMMY_HASH, hash_password, hash_token, new_token, verify_password
from app.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    RegisterRequest,
    TokenOut,
    UpdateProfileRequest,
    UserOut,
)

router = APIRouter(prefix="/auth", tags=["auth"])

MAX_FAILS, WINDOW_SECONDS = 8, 600.0
_fails: dict[str, list[float]] = {}  # per-email failed logins, in memory (resets on restart)


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _user_out(u: User) -> UserOut:
    return UserOut(id=u.id, email=u.email, name=u.name, level=u.level)


def _issue(db: Db, settings: Cfg, user: User) -> TokenOut:
    token = new_token()
    expires = _now() + timedelta(hours=settings.auth_session_hours)
    db.add(AuthSession(token_hash=hash_token(token), user_id=user.id, expires_at=expires))
    db.execute(delete(AuthSession).where(AuthSession.expires_at < _now()))  # tidy expired logins
    db.commit()
    return TokenOut(token=token, expires_at=expires, user=_user_out(user))


@router.post("/register", response_model=TokenOut, status_code=201, summary="Create an account and log in")
def register(req: RegisterRequest, db: Db, settings: Cfg) -> TokenOut:
    if not settings.allow_registration:
        raise HTTPException(403, "Registration is disabled")
    email = req.email.strip().lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(409, "An account with this email already exists")
    user = User(
        id=uuid.uuid4().hex,
        email=email,
        name=req.name.strip(),
        level=req.level,
        password_hash=hash_password(req.password),
    )
    db.add(user)
    db.commit()
    return _issue(db, settings, user)


@router.post("/login", response_model=TokenOut, summary="Log in with email and password")
def login(req: LoginRequest, db: Db, settings: Cfg) -> TokenOut:
    email = req.email.strip().lower()
    now = time.monotonic()
    recent = [t for t in _fails.get(email, []) if now - t < WINDOW_SECONDS]
    if len(recent) >= MAX_FAILS:
        raise HTTPException(429, "Too many failed attempts. Try again in a few minutes.")
    user = db.scalar(select(User).where(User.email == email))
    ok = verify_password(req.password, user.password_hash if user else DUMMY_HASH)
    if not (user and ok):
        _fails[email] = [*recent, now]
        raise HTTPException(401, "Invalid email or password", headers={"WWW-Authenticate": "Bearer"})
    _fails.pop(email, None)
    return _issue(db, settings, user)


@router.get("/me", response_model=UserOut, summary="The logged-in user")
def me(user: CurrentUser) -> UserOut:
    return _user_out(user)


@router.patch("/me", response_model=UserOut, summary="Update your name or experience level")
def update_me(req: UpdateProfileRequest, db: Db, user: CurrentUser) -> UserOut:
    if req.name is not None:
        user.name = req.name.strip()
    if req.level is not None:
        user.level = req.level
    db.commit()
    return _user_out(user)


@router.post("/logout", status_code=204, summary="End this login")
def logout(db: Db, user: CurrentUser, authorization: Annotated[str | None, Header()] = None) -> Response:
    token = (authorization or "").split(" ", 1)[-1]
    db.execute(delete(AuthSession).where(AuthSession.token_hash == hash_token(token), AuthSession.user_id == user.id))
    db.commit()
    return Response(status_code=204)


@router.post("/change-password", status_code=204, summary="Change your password (other logins are ended)")
def change_password(
    req: ChangePasswordRequest, db: Db, user: CurrentUser, authorization: Annotated[str | None, Header()] = None
) -> Response:
    if not verify_password(req.current_password, user.password_hash):
        raise HTTPException(400, "Current password is incorrect")
    user.password_hash = hash_password(req.new_password)
    keep = hash_token((authorization or "").split(" ", 1)[-1])
    db.execute(delete(AuthSession).where(AuthSession.user_id == user.id, AuthSession.token_hash != keep))
    db.commit()
    return Response(status_code=204)

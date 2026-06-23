"""
Authentication & invitation endpoints.

Registration is invite-only (no open self-registration). Two sign-in methods:
password (email/username) and Google OAuth. Sessions are an HTTP-only JWT cookie.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import EmailVerification, InviteCode, PasswordReset, User
from ..schemas import (
    AuthOut,
    ForgotPasswordRequest,
    InviteCreateRequest,
    InviteOut,
    LoginRequest,
    RegisterRequest,
    ResetPasswordRequest,
    UserOut,
)
from ..auth.security import (
    clear_session_cookie,
    create_access_token,
    get_current_admin,
    get_current_user,
    hash_password,
    new_token,
    set_session_cookie,
    verify_password,
)
from ..auth.emails import send_password_reset_email, send_verification_email

router = APIRouter(prefix="/api/auth", tags=["auth"])


# ── Helpers ──────────────────────────────────────────────────────────────────

def _consume_invite(code: str, email: str, db: Session) -> InviteCode:
    """Validate an invite for *email* and mark it used. Raises 400 if invalid."""
    invite = db.query(InviteCode).filter(InviteCode.code == code).first()
    if not invite or invite.used_at is not None:
        raise HTTPException(status_code=400, detail="Código de invitación inválido o ya usado.")
    if invite.expires_at and invite.expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="El código de invitación expiró.")
    if invite.email and invite.email.lower() != email.lower():
        raise HTTPException(status_code=400, detail="La invitación es para otro email.")
    return invite


def _unique_username(base: str, db: Session) -> str:
    candidate = base or "user"
    candidate = "".join(c for c in candidate if c.isalnum() or c in "_.-")[:72] or "user"
    if not db.query(User).filter(User.username == candidate).first():
        return candidate
    i = 1
    while db.query(User).filter(User.username == f"{candidate}{i}").first():
        i += 1
    return f"{candidate}{i}"


# ── Registration / verification ──────────────────────────────────────────────

@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status_code=409, detail="Ese email ya está registrado.")
    if db.query(User).filter(User.username == payload.username).first():
        raise HTTPException(status_code=409, detail="Ese nombre de usuario ya existe.")

    invite = _consume_invite(payload.invite_code, payload.email, db)

    user = User(
        email=payload.email,
        username=payload.username,
        password_hash=hash_password(payload.password),
        is_verified=False,
        is_active=True,
        is_admin=False,
    )
    db.add(user)
    db.flush()  # assign user.id

    invite.used_at = datetime.utcnow()
    invite.used_by = user.id

    token = new_token()
    db.add(EmailVerification(
        token=token,
        user_id=user.id,
        expires_at=datetime.utcnow() + timedelta(hours=48),
    ))
    db.commit()
    db.refresh(user)

    await send_verification_email(user.email, token)
    return user


@router.get("/verify")
def verify_email(token: str, db: Session = Depends(get_db)):
    rec = db.query(EmailVerification).filter(EmailVerification.token == token).first()
    if not rec or rec.expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Enlace de verificación inválido o expirado.")
    user = db.query(User).filter(User.id == rec.user_id).first()
    if not user:
        raise HTTPException(status_code=400, detail="Usuario no encontrado.")
    user.is_verified = True
    db.delete(rec)
    db.commit()
    return {"status": "verified"}


# ── Password login / logout ──────────────────────────────────────────────────

@router.post("/login", response_model=AuthOut)
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)):
    ident = payload.identifier.strip()
    user = (
        db.query(User)
        .filter(or_(User.email == ident, User.username == ident))
        .first()
    )
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Credenciales inválidas.")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Cuenta deshabilitada.")
    if not user.is_verified:
        raise HTTPException(status_code=403, detail="Verificá tu email antes de ingresar.")
    token = create_access_token(user.id)
    set_session_cookie(response, token)  # web: cookie
    out = AuthOut.model_validate(user)   # native: bearer
    out.access_token = token
    return out


# ── Password reset ────────────────────────────────────────────────────────────

@router.post("/forgot-password")
async def forgot_password(payload: ForgotPasswordRequest, db: Session = Depends(get_db)):
    """
    Start a password reset. Always returns the same response whether or not the
    email exists, so it can't be used to probe which addresses are registered.
    """
    user = db.query(User).filter(User.email == payload.email).first()
    if user and user.is_active:
        # Invalidate any outstanding tokens for this user, then issue a fresh one.
        db.query(PasswordReset).filter(PasswordReset.user_id == user.id).delete()
        token = new_token()
        db.add(PasswordReset(
            token=token,
            user_id=user.id,
            expires_at=datetime.utcnow() + timedelta(hours=2),
        ))
        db.commit()
        await send_password_reset_email(user.email, token)

    return {"status": "ok"}


@router.post("/reset-password")
def reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)):
    rec = db.query(PasswordReset).filter(PasswordReset.token == payload.token).first()
    if not rec or rec.expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Enlace de restablecimiento inválido o expirado.")
    user = db.query(User).filter(User.id == rec.user_id).first()
    if not user:
        raise HTTPException(status_code=400, detail="Usuario no encontrado.")

    user.password_hash = hash_password(payload.password)
    # Reaching this link proves control of the email, so the account is verified.
    user.is_verified = True
    # Burn this token and any siblings.
    db.query(PasswordReset).filter(PasswordReset.user_id == user.id).delete()
    db.commit()
    return {"status": "reset"}


@router.post("/logout")
def logout(response: Response):
    clear_session_cookie(response)
    return {"status": "logged_out"}


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


# ── Invitations (admin only) ─────────────────────────────────────────────────

@router.post("/invites", response_model=InviteOut, status_code=status.HTTP_201_CREATED)
def create_invite(
    payload: InviteCreateRequest,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    code = new_token(18)
    invite = InviteCode(
        code=code,
        email=payload.email,
        created_by=admin.id,
        expires_at=datetime.utcnow() + timedelta(days=payload.expires_days),
    )
    db.add(invite)
    db.commit()
    return InviteOut(
        code=code,
        email=payload.email,
        expires_at=invite.expires_at,
        url=f"{settings.app_base_url.rstrip('/')}/register?invite={code}",
    )


# ── Google OAuth ─────────────────────────────────────────────────────────────

def _oauth():
    from ..auth.oauth import oauth
    if oauth is None:
        raise HTTPException(status_code=503, detail="Google login no está configurado.")
    return oauth


@router.get("/google/login")
async def google_login(request: Request):
    client = _oauth()
    redirect_uri = f"{settings.oauth_redirect_base.rstrip('/')}/api/auth/google/callback"
    return await client.google.authorize_redirect(request, redirect_uri)


@router.get("/google/callback")
async def google_callback(request: Request, db: Session = Depends(get_db)):
    client = _oauth()
    try:
        token = await client.google.authorize_access_token(request)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"OAuth falló: {exc}")

    userinfo = token.get("userinfo") or {}
    sub = userinfo.get("sub")
    email = userinfo.get("email")
    if not sub or not email:
        raise HTTPException(status_code=400, detail="Google no devolvió email.")

    user = db.query(User).filter(User.google_sub == sub).first()
    if not user:
        # Link to an existing password account with the same email, if any.
        user = db.query(User).filter(User.email == email).first()
        if user:
            user.google_sub = sub
            user.is_verified = True
        else:
            # New account — requires a valid invitation for this email.
            invite = _consume_invite_google(email, db)
            user = User(
                email=email,
                username=_unique_username((email.split("@")[0]), db),
                google_sub=sub,
                is_verified=True,
                is_active=True,
                is_admin=False,
            )
            db.add(user)
            db.flush()
            invite.used_at = datetime.utcnow()
            invite.used_by = user.id

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Cuenta deshabilitada.")
    db.commit()
    db.refresh(user)

    # Redirect back into the SPA with the session cookie set.
    from fastapi.responses import RedirectResponse
    resp = RedirectResponse(url="/", status_code=302)
    set_session_cookie(resp, create_access_token(user.id))
    return resp


def _consume_invite_google(email: str, db: Session) -> InviteCode:
    """Find a usable invite for a brand-new Google user (email-bound or open)."""
    now = datetime.utcnow()
    invite = (
        db.query(InviteCode)
        .filter(
            InviteCode.used_at.is_(None),
            or_(InviteCode.email == email, InviteCode.email.is_(None)),
            or_(InviteCode.expires_at.is_(None), InviteCode.expires_at >= now),
        )
        .order_by(InviteCode.email.isnot(None).desc())  # prefer email-bound
        .first()
    )
    if not invite:
        raise HTTPException(
            status_code=403,
            detail="No tenés una invitación válida para registrarte con Google.",
        )
    return invite

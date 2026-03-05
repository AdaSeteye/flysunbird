import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.schemas.auth import LoginRequest, TokenPair, RefreshRequest, ChangePasswordRequest
from app.models.user import User
from app.core.security import verify_password, create_access_token, create_refresh_token
from app.api.deps import get_current_user

router = APIRouter(tags=["auth"])

@router.post("/auth/login", response_model=TokenPair)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email.lower()).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    must_change = getattr(user, "must_change_password", False)
    return TokenPair(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
        mustChangePassword=must_change,
    )


@router.post("/auth/refresh", response_model=TokenPair)
def refresh(body: RefreshRequest, db: Session = Depends(get_db)):
    """Accept refresh_token in POST body to avoid leaking it in URL/logs."""
    from app.core.security import decode_token
    try:
        payload = decode_token(body.refresh_token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    user_id = payload.get("sub")
    user = db.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")
    must_change = getattr(user, "must_change_password", False)
    return TokenPair(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
        mustChangePassword=must_change,
    )

@router.get("/auth/me")
def me(me: User = Depends(get_current_user)):
    """Return current user info including role and whether password must be changed."""
    return {
        "id": me.id,
        "email": me.email,
        "fullName": me.full_name or "",
        "role": me.role,
        "mustChangePassword": getattr(me, "must_change_password", False),
    }


@router.post("/auth/change-password")
def change_password(body: ChangePasswordRequest,
                    db: Session = Depends(get_db),
                    me: User = Depends(get_current_user)):
    from app.core.security import hash_password
    if not verify_password(body.oldPassword, me.password_hash):
        raise HTTPException(status_code=400, detail="Old password incorrect")
    if len(body.newPassword) < 8:
        raise HTTPException(status_code=400, detail="Password too short")
    me.password_hash = hash_password(body.newPassword)
    me.must_change_password = False
    db.commit()
    return {"ok": True}

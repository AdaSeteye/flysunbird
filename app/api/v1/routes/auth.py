import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.schemas.auth import LoginRequest, TokenPair
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
    return TokenPair(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
    )


@router.post("/auth/refresh", response_model=TokenPair)
def refresh(refresh_token: str, db: Session = Depends(get_db)):
    from app.core.security import decode_token
    try:
        payload = decode_token(refresh_token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    user_id = payload.get("sub")
    user = db.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")
    return TokenPair(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
    )

@router.get("/auth/me")
def me(me: User = Depends(get_current_user)):
    """Return current user info including role."""
    return {
        "id": me.id,
        "email": me.email,
        "fullName": me.full_name or "",
        "role": me.role,
    }


@router.post("/auth/change-password")
def change_password(oldPassword: str, newPassword: str,
                    db: Session = Depends(get_db),
                    me: User = Depends(get_current_user)):
    from app.core.security import hash_password
    if not verify_password(oldPassword, me.password_hash):
        raise HTTPException(status_code=400, detail="Old password incorrect")
    if len(newPassword) < 8:
        raise HTTPException(status_code=400, detail="Password too short")
    me.password_hash = hash_password(newPassword)
    db.commit()
    return {"ok": True}

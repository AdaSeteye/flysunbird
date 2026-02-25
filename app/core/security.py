from datetime import datetime, timedelta, timezone

from jose import jwt
from passlib.context import CryptContext

from app.core.config import settings

# PBKDF2 avoids bcrypt backend/version issues and the 72-byte bcrypt input limit.
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
ALGO = "HS256"


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def create_access_token(subject: str, expires_minutes: int | None = None) -> str:
    if expires_minutes is None:
        expires_minutes = settings.ACCESS_TOKEN_EXPIRE_MINUTES
    exp = datetime.now(timezone.utc) + timedelta(minutes=expires_minutes)
    payload = {"sub": subject, "type": "access", "exp": exp}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGO)


def create_refresh_token(subject: str, expires_days: int | None = None) -> str:
    if expires_days is None:
        expires_days = settings.REFRESH_TOKEN_EXPIRE_DAYS
    exp = datetime.now(timezone.utc) + timedelta(days=expires_days)
    payload = {"sub": subject, "type": "refresh", "exp": exp}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGO)


def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGO])

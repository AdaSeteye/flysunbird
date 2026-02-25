import json
from sqlalchemy.orm import Session
from app.models.setting import Setting

DEFAULT_USD_TO_TZS = 2450
DEFAULT_TERMS = {"version": "2025", "docSha256": "edfe624c7f9b2dac0ced3b189039f693c0683123f12881d3702b0fcf4d19631d", "url": "fly/terms-and-conditions.html"}

def get_usd_to_tzs_rate(db: Session) -> int:
    s = db.get(Setting, "USD_TO_TZS")
    if s and s.int_value:
        return int(s.int_value)
    return DEFAULT_USD_TO_TZS

def set_usd_to_tzs_rate(db: Session, rate: int) -> int:
    if rate <= 0:
        raise ValueError("rate must be > 0")
    s = db.get(Setting, "USD_TO_TZS")
    if not s:
        s = Setting(key="USD_TO_TZS", int_value=int(rate), str_value=None)
        db.add(s)
    else:
        s.int_value = int(rate)
    db.commit()
    return int(rate)

def get_terms(db: Session) -> dict:
    s = db.get(Setting, "TERMS")
    if s and s.str_value:
        try:
            return json.loads(s.str_value)
        except (json.JSONDecodeError, TypeError):
            pass
    return DEFAULT_TERMS.copy()

def set_terms(db: Session, version: str, doc_sha256: str, url: str) -> dict:
    data = {"version": version or "2025", "docSha256": doc_sha256 or "", "url": url or "fly/terms-and-conditions.html"}
    s = db.get(Setting, "TERMS")
    if not s:
        s = Setting(key="TERMS", int_value=None, str_value=json.dumps(data))
        db.add(s)
    else:
        s.str_value = json.dumps(data)
    db.commit()
    return data

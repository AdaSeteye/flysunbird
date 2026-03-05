"""Resolve partner referral code via the PHP partners app API."""
import requests
from typing import Any

def get_partner_by_code(base_url: str, code: str, timeout: float = 5.0) -> dict[str, Any] | None:
    """
    Call PHP app GET api/partner-by-code.php?code=... .
    Returns partner dict (e.g. name, contact, asset_code) or None if not found or on error.
    """
    if not (base_url or "").strip() or not (code or "").strip():
        return None
    url_base = (base_url or "").strip().rstrip("/")
    url = f"{url_base}/api/partner-by-code.php"
    try:
        r = requests.get(url, params={"code": code.strip()}, timeout=timeout)
        if r.status_code != 200:
            return None
        data = r.json()
        if not data or not data.get("found"):
            return None
        return data.get("partner") or None
    except Exception:
        return None

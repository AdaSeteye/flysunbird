import base64
import hashlib
import hmac
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import format_datetime
from urllib.parse import urlparse
import json
import requests

@dataclass
class CybersourceConfig:
    host: str               # apitest.cybersource.com OR api.cybersource.com
    merchant_id: str        # v-c-merchant-id header
    key_id: str             # keyid in Signature header
    secret_key_b64: str     # shared secret key (base64-encoded string from Business Center)
    timeout: int = 25

class CybersourceError(RuntimeError):
    pass

def _sha256_digest_b64(body_bytes: bytes) -> str:
    digest = hashlib.sha256(body_bytes).digest()
    return base64.b64encode(digest).decode("utf-8")

def _hmac_sha256_b64(secret_key: bytes, msg: str) -> str: 
    sig = hmac.new(secret_key, msg.encode("utf-8"), hashlib.sha256).digest()
    return base64.b64encode(sig).decode("utf-8")

def _validation_string(method: str, resource: str, host: str, date_str: str, digest_header: str, merchant_id: str) -> str:
    # IMPORTANT: newline separated, no trailing newline
    lines = [
        f"host: {host}",
        f"date: {date_str}",
        f"(request-target): {method.lower()} {resource}",
        f"digest: {digest_header}",
        f"v-c-merchant-id: {merchant_id}",
    ]
    return "\n".join(lines)

class CybersourceClient:
    def __init__(self, cfg: CybersourceConfig):
        self.cfg = cfg
        # Strip whitespace/newlines (e.g. if PEM wrapper was pasted); use only the base64 line(s)
        b64 = (cfg.secret_key_b64 or "").strip().replace("\r", "").replace("\n", "").replace(" ", "")
        self._secret = base64.b64decode(b64)

    def _headers(self, method: str, resource: str, body_bytes: bytes) -> dict:
        # Date must be RFC1123
        date_str = format_datetime(datetime.now(timezone.utc), usegmt=True)
        digest_b64 = _sha256_digest_b64(body_bytes)
        digest_header = f"SHA-256={digest_b64}"

        vs = _validation_string(method, resource, self.cfg.host, date_str, digest_header, self.cfg.merchant_id)
        signature_b64 = _hmac_sha256_b64(self._secret, vs)

        signature_header = (
            f'keyid="{self.cfg.key_id}", '
            f'algorithm="HmacSHA256", '
            f'headers="host date (request-target) digest v-c-merchant-id", '
            f'signature="{signature_b64}"'
        )

        return {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Host": self.cfg.host,
            "Date": date_str,
            "Digest": digest_header,
            "v-c-merchant-id": self.cfg.merchant_id,
            "Signature": signature_header,
        }

    def request(self, method: str, path: str, payload: dict | None = None) -> dict:
        payload = payload or {}
        body_bytes = json.dumps(payload, separators=(",",":")).encode("utf-8")
        headers = self._headers(method, path, body_bytes)
        url = f"https://{self.cfg.host}{path}"
        r = requests.request(method=method.upper(), url=url, data=body_bytes, headers=headers, timeout=self.cfg.timeout)
        try:
            data = r.json() if r.text else {}
        except Exception:
            data = {"raw": r.text}
        if r.status_code >= 400:
            msg = f"Cybersource {r.status_code}: {data}"
            if r.status_code == 404:
                msg += (
                    f" (URL: {url}). "
                    "For 404: ensure your merchant has REST Payments API enabled in Cybersource Business Center "
                    "(Payment Configuration / Transaction Processing), and that credentials are for REST API (HTTP Signature), not Flex only."
                )
            raise CybersourceError(msg)
        return data

    def sale_card(self, *, client_ref: str, amount: str, currency: str, bill_to: dict, card: dict) -> dict:
        payload = {
            "clientReferenceInformation": {"code": client_ref},
            "processingInformation": {"capture": True},
            "paymentInformation": {"card": card},
            "orderInformation": {"amountDetails": {"totalAmount": str(amount), "currency": currency}, "billTo": bill_to},
        }
        return self.request("POST", "/pts/v2/payments", payload)

    def capture(self, *, payment_id: str, client_ref: str, amount: str, currency: str) -> dict:
        payload = {
            "clientReferenceInformation": {"code": client_ref},
            "orderInformation": {"amountDetails": {"totalAmount": str(amount), "currency": currency}},
        }
        return self.request("POST", f"/pts/v2/payments/{payment_id}/captures", payload)

    def refund_payment(self, *, payment_id: str, client_ref: str, amount: str, currency: str) -> dict:
        payload = {
            "clientReferenceInformation": {"code": client_ref},
            "orderInformation": {"amountDetails": {"totalAmount": str(amount), "currency": currency}},
        }
        return self.request("POST", f"/pts/v2/payments/{payment_id}/refunds", payload)

    def capture_context_microform(self, *, target_origins: list[str], client_version: str, allowed_card_networks: list[str], allowed_payment_types: list[str] | None = None) -> dict:
        payload = {
            "targetOrigins": target_origins,
            "clientVersion": client_version,
            "allowedCardNetworks": allowed_card_networks,
            "allowedPaymentTypes": allowed_payment_types or ["CARD"],
        }
        # Microform v2 sessions endpoint
        return self.request("POST", "/microform/v2/sessions", payload)

    def capture_context_up(self, *, target_origins: list[str], client_version: str, country: str, locale: str, currency: str, total_amount: str, allowed_card_networks: list[str], allowed_payment_types: list[str]) -> dict:
        payload = {
            "targetOrigins": target_origins,
            "clientVersion": client_version,
            "country": country,
            "locale": locale,
            "allowedCardNetworks": allowed_card_networks,
            "allowedPaymentTypes": allowed_payment_types,
            "data": {
                "orderInformation": {
                    "amountDetails": {"currency": currency, "totalAmount": total_amount}
                }
            }
        }
        return self.request("POST", "/up/v1/capture-contexts", payload)

    def sale_transient_token(self, *, client_ref: str, amount: str, currency: str, transient_token_jwt: str, bill_to: dict | None = None, capture: bool = True) -> dict:
        payload = {
            "clientReferenceInformation": {"code": client_ref},
            "processingInformation": {"capture": bool(capture)},
            "tokenInformation": {"transientTokenJwt": transient_token_jwt},
            "orderInformation": {"amountDetails": {"totalAmount": str(amount), "currency": currency}},
        }
        if bill_to:
            payload["orderInformation"]["billTo"] = bill_to
        return self.request("POST", "/pts/v2/payments", payload)

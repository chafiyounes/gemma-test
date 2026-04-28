import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Dict, Optional


class AuthManager:
    """Signed-cookie authentication — shared user/admin passwords."""

    def __init__(
        self,
        *,
        secret_key: str,
        user_password: str,
        admin_password: str,
        cookie_name: str,
        session_ttl_seconds: int,
    ):
        self._secret = secret_key.encode("utf-8")
        self._user_pw = user_password
        self._admin_pw = admin_password
        self.cookie_name = cookie_name
        self.session_ttl = session_ttl_seconds

    # ── Password auth ──────────────────────────────────────────────────────

    def authenticate(self, password: str) -> Optional[str]:
        """Return 'admin', 'user', or None."""
        if secrets.compare_digest(password, self._admin_pw):
            return "admin"
        if secrets.compare_digest(password, self._user_pw):
            return "user"
        return None

    @staticmethod
    def role_satisfies(role: str, required: str) -> bool:
        order = {"user": 1, "admin": 2}
        return order.get(role, 0) >= order.get(required, 99)

    # ── Cookie mechanics ───────────────────────────────────────────────────

    @staticmethod
    def _b64_encode(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")

    @staticmethod
    def _b64_decode(s: str) -> bytes:
        padding = 4 - len(s) % 4
        return base64.urlsafe_b64decode(s + "=" * padding)

    def create_session_cookie(self, role: str) -> tuple[str, int]:
        expires_at = int(time.time()) + self.session_ttl
        payload = json.dumps({"role": role, "exp": expires_at}, separators=(",", ":")).encode()
        payload_b64 = self._b64_encode(payload)
        sig = hmac.new(self._secret, payload_b64.encode(), hashlib.sha256).digest()
        return f"{payload_b64}.{self._b64_encode(sig)}", expires_at

    def read_session_cookie(self, cookie_value: Optional[str]) -> Optional[Dict]:
        if not cookie_value or "." not in cookie_value:
            return None
        try:
            payload_b64, sig_b64 = cookie_value.rsplit(".", 1)
            expected_sig = hmac.new(self._secret, payload_b64.encode(), hashlib.sha256).digest()
            actual_sig = self._b64_decode(sig_b64)
            if not hmac.compare_digest(expected_sig, actual_sig):
                return None
            payload = json.loads(self._b64_decode(payload_b64))
            if payload.get("exp", 0) < int(time.time()):
                return None
            return payload
        except Exception:
            return None

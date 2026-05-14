import base64
import hashlib
import hmac
import json
import time
from typing import Any, Dict, Optional

# Application roles (SQLite users.role). "admin" is a legacy alias for administrator.
ROLE_ORDER = {"user": 1, "manager": 2, "administrator": 3}
ROLE_ALIASES = {"admin": "administrator"}


class AuthManager:
    """Signed-session cookies (payload includes uid, username, role)."""

    def __init__(
        self,
        *,
        secret_key: str,
        cookie_name: str,
        session_ttl_seconds: int,
    ):
        self._secret = secret_key.encode("utf-8")
        self.cookie_name = cookie_name
        self.session_ttl = session_ttl_seconds

    @staticmethod
    def normalize_role(role: Optional[str]) -> str:
        if not role:
            return "user"
        key = str(role).strip().lower()
        return ROLE_ALIASES.get(key, key)

    @staticmethod
    def role_satisfies(role: str, minimum: str) -> bool:
        """True if *role* is at least *minimum* in the hierarchy (user < manager < administrator)."""
        r = AuthManager.normalize_role(role)
        m = AuthManager.normalize_role(minimum)
        return ROLE_ORDER.get(r, 0) >= ROLE_ORDER.get(m, 99)

    # ── Cookie mechanics ───────────────────────────────────────────────────

    @staticmethod
    def _b64_encode(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")

    @staticmethod
    def _b64_decode(s: str) -> bytes:
        padding = 4 - len(s) % 4
        return base64.urlsafe_b64decode(s + "=" * padding)

    def create_session_cookie(self, payload: Dict[str, Any]) -> tuple[str, int]:
        """Payload keys: uid (int), username (str), role (str). Adds exp."""
        expires_at = int(time.time()) + self.session_ttl
        body = {**payload, "exp": expires_at}
        for k in ("uid", "username", "role"):
            if k not in body:
                raise ValueError(f"session payload missing {k}")
        payload_json = json.dumps(
            {
                "uid": int(body["uid"]),
                "username": str(body["username"]),
                "role": AuthManager.normalize_role(body.get("role")),
                "exp": expires_at,
            },
            separators=(",", ":"),
        ).encode()
        payload_b64 = self._b64_encode(payload_json)
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
            if "role" in payload:
                payload["role"] = AuthManager.normalize_role(payload.get("role"))
            return payload
        except Exception:
            return None

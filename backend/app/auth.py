from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any


class AuthenticationError(ValueError):
    """Raised when an access token cannot be trusted."""


def _base64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _base64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    try:
        return base64.urlsafe_b64decode(value + padding)
    except (ValueError, UnicodeEncodeError) as exc:
        raise AuthenticationError("访问令牌编码无效") from exc


def create_access_token(
    user_id: str,
    secret: str,
    *,
    ttl_seconds: int = 3600,
    now: int | None = None,
) -> str:
    issued_at = int(time.time()) if now is None else now
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": user_id,
        "iat": issued_at,
        "exp": issued_at + ttl_seconds,
    }
    encoded_header = _base64url_encode(
        json.dumps(header, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    encoded_payload = _base64url_encode(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    signing_input = f"{encoded_header}.{encoded_payload}".encode("ascii")
    signature = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    return f"{encoded_header}.{encoded_payload}.{_base64url_encode(signature)}"


def verify_access_token(
    token: str,
    secret: str,
    *,
    now: int | None = None,
) -> dict[str, Any]:
    parts = token.split(".")
    if len(parts) != 3:
        raise AuthenticationError("访问令牌格式无效")
    encoded_header, encoded_payload, encoded_signature = parts
    try:
        header = json.loads(_base64url_decode(encoded_header))
        payload = json.loads(_base64url_decode(encoded_payload))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise AuthenticationError("访问令牌内容无效") from exc
    if header != {"alg": "HS256", "typ": "JWT"}:
        raise AuthenticationError("不支持的访问令牌算法")
    signing_input = f"{encoded_header}.{encoded_payload}".encode("ascii")
    expected = hmac.new(
        secret.encode("utf-8"), signing_input, hashlib.sha256
    ).digest()
    supplied = _base64url_decode(encoded_signature)
    if not hmac.compare_digest(expected, supplied):
        raise AuthenticationError("访问令牌签名无效")
    subject = payload.get("sub")
    expires_at = payload.get("exp")
    issued_at = payload.get("iat")
    if not isinstance(subject, str) or not subject.strip():
        raise AuthenticationError("访问令牌缺少用户标识")
    if not isinstance(expires_at, int) or not isinstance(issued_at, int):
        raise AuthenticationError("访问令牌时间声明无效")
    current_time = int(time.time()) if now is None else now
    if issued_at > current_time + 60:
        raise AuthenticationError("访问令牌尚未生效")
    if expires_at <= current_time:
        raise AuthenticationError("访问令牌已过期")
    return payload

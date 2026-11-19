"""Contexto por solicitud, aislado entre tareas y firmado al cruzar el Gateway."""
import hashlib
import hmac
import ipaddress
import json
import time
import uuid
from contextvars import ContextVar
from typing import Any

from starlette.datastructures import Headers

from backend.shared.config import settings

audit_context: ContextVar[dict[str, Any]] = ContextVar("audit_context", default={})
GATEWAY_HEADER = "x-maxiconecta-audit"
SIGNATURE_HEADER = "x-maxiconecta-audit-signature"


def trusted_role(claims: dict) -> str:
    role = (claims.get("app_metadata") or {}).get("role") or claims.get("role")
    return role if role in {"administrador", "gerente_comercial", "cajero", "cliente"} else "cliente"


def _ip(value: Any) -> str | None:
    try:
        return str(ipaddress.ip_address(str(value)))
    except ValueError:
        return None


def signed_gateway_headers() -> dict[str, str]:
    value = json.dumps({**audit_context.get(), "issued_at": int(time.time())}, ensure_ascii=True, separators=(",", ":"))
    signature = hmac.new(settings.JWT_SECRET.encode(), value.encode(), hashlib.sha256).hexdigest()
    return {GATEWAY_HEADER: value, SIGNATURE_HEADER: signature}


def _gateway_context(headers: Headers) -> dict:
    value = headers.get(GATEWAY_HEADER, "")
    signature = headers.get(SIGNATURE_HEADER, "")
    if not value or len(value) > 8192:
        return {}
    expected = hmac.new(settings.JWT_SECRET.encode(), value.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return {}
    try:
        data = json.loads(value)
        if abs(time.time() - int(data["issued_at"])) > 120:
            return {}
        uuid.UUID(data["request_id"])
        return data
    except (ValueError, TypeError, KeyError):
        return {}


class AuditContextMiddleware:
    def __init__(self, app, gateway: bool = False):
        self.app, self.gateway = app, gateway

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        from backend.shared.security import decode_access_token
        headers = Headers(scope=scope)
        forwarded = {} if self.gateway else _gateway_context(headers)
        authorization = headers.get("authorization", "")
        scheme, _, token = authorization.partition(" ")
        claims = decode_access_token(token) if scheme.lower() == "bearer" and token else None
        claims = claims or {}
        context = {
            "actor_id": claims.get("sub") or "anonimo",
            "role": trusted_role(claims) if claims.get("sub") else "anonimo",
            "ip_address": _ip(forwarded.get("ip_address") or (scope.get("client") or [None])[0]),
            "request_id": forwarded.get("request_id") or str(uuid.uuid4()),
            "request_method": scope["method"],
            "request_path": scope["path"],
            "user_agent": str(forwarded.get("user_agent") or headers.get("user-agent", ""))[:500],
        }
        state = scope.setdefault("state", {})
        state["audit_context"] = context
        reset = audit_context.set(context)
        async def send_with_id(message):
            if message["type"] == "http.response.start":
                message.setdefault("headers", []).append((b"x-request-id", context["request_id"].encode()))
            await send(message)
        try:
            await self.app(scope, receive, send_with_id)
        finally:
            audit_context.reset(reset)

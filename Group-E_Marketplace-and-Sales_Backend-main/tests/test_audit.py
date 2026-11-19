from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from backend.shared.audit import AUDIT_LOGS_EN_MEMORIA, registrar_auditoria, settings


class FakeQuery:
    def __init__(self, client, table):
        self.client = client
        self.table = table
        self.payload = None

    def insert(self, payload):
        self.payload = payload
        return self

    def execute(self):
        self.client.rows.append((self.table, self.payload))
        return SimpleNamespace(data=[])


class FakeClient:
    def __init__(self):
        self.rows = []

    def table(self, name):
        return FakeQuery(self, name)


def _request():
    return Request({
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "PATCH",
        "scheme": "https",
        "path": "/api/v1/catalogo/productos/123",
        "raw_path": b"/api/v1/catalogo/productos/123",
        "query_string": b"",
        "root_path": "",
        "headers": [(b"user-agent", b"audit-test")],
        "client": ("192.0.2.15", 4321),
        "server": ("api.example", 443),
        "state": {},
    })


def test_auditoria_guarda_actor_accion_origen_y_snapshots_redactados():
    client = FakeClient()
    user_id = "12345678-1234-1234-1234-123456789012"

    row = registrar_auditoria(
        client,
        current_user={"sub": user_id, "role": "administrador", "email": "admin@example.test"},
        accion="PRODUCTO_ACTUALIZADO",
        entidad="productos",
        entidad_id=user_id,
        antes={"estado": "borrador", "token": "dont-store"},
        despues={"estado": "publicado", "service_role_key": "dont-store"},
        request=_request(),
    )

    assert row["user_id"] == user_id
    assert row["user_role"] == "administrador"
    assert row["ip_address"] == "192.0.2.15"
    assert row["action"] == "PRODUCTO_ACTUALIZADO"
    assert row["payload_before"]["estado"] == "borrador"
    assert row["payload_before"]["token"] == "[REDACTED]"
    assert row["payload_after"]["service_role_key"] == "[REDACTED]"
    assert client.rows[0][0] == "audit_logs"


def test_auditoria_en_desarrollo_queda_en_log_estructurado(monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "testing")
    row = registrar_auditoria(
        None,
        current_user={"sub": "actor-test", "role": "cajero"},
        accion="VENTA_POS_CREADA",
        entidad="pos_ventas",
        despues={"estado": "completada"},
    )

    assert row in AUDIT_LOGS_EN_MEMORIA
    assert row["actor_id"] == "actor-test"
    assert row["timestamp"].endswith("Z")


def test_auditoria_en_produccion_conserva_evento_pendiente_sin_supabase(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "AUDIT_SPOOL_PATH", str(tmp_path / "audit.sqlite3"))
    row = registrar_auditoria(None, current_user={"sub": "actor-test", "role": "administrador"},
        accion="ELIMINAR_PRODUCTO", entidad="productos")
    from backend.shared.audit_spool import summary
    assert row["persistencia"] == "pendiente"
    assert summary()["pendientes"] == 1

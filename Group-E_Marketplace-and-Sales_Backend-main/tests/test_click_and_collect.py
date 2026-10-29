import sys
import os
import uuid
from decimal import Decimal
from types import SimpleNamespace
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from fastapi.testclient import TestClient
from backend.services.pos.app.main import app as pos_app
from backend.services.pos.app import routers as pos_routers
from backend.shared.security import create_access_token

client = TestClient(pos_app)
admin_token = create_access_token({"sub": "admin-001", "role": "administrador"})
admin_headers = {"Authorization": f"Bearer {admin_token}"}
cajero_token = create_access_token({"sub": "cajero-001", "role": "cajero", "sucursal_id": "SUC-01"})
cajero_headers = {"Authorization": f"Bearer {cajero_token}"}

def test_listar_pedidos_click_and_collect():
    """KAN-324: Listar pedidos Click & Collect para mostrador."""
    resp = client.get("/api/v1/pos/click-and-collect/pedidos", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 2
    codigos = [p["codigo_retiro"] for p in data]
    assert "RET-789214" in codigos


def test_validar_codigo_retiro_exitoso():
    """KAN-324 / KAN-108: Validar código de retiro y estado entregable."""
    resp = client.post("/api/v1/pos/click-and-collect/validar", json={
        "codigo": "RET-789214",
        "sucursal_id": "SUC-01"
    }, headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["codigo_retiro"] == "RET-789214"
    assert data["codigo_orden"] == "ORD-2026-CC101"
    assert data["estado"] == "confirmada"
    assert data["es_entregable"] is True
    assert data["cliente_nombre"] == "Carlos Mendoza Patzi"
    assert len(data["items"]) >= 2
    assert float(data["total"]) == 15766.00


def test_validar_qr_click_and_collect():
    """KAN-324: Validar lectura de código QR compuesto."""
    payload_qr = "MAXI-CC|ORD-2026-CC101|RET-789214|SUC-01"
    resp = client.post("/api/v1/pos/click-and-collect/validar", json={
        "codigo": payload_qr
    }, headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["codigo_retiro"] == "RET-789214"
    assert data["es_entregable"] is True


def test_validar_codigo_ya_entregado():
    """KAN-108: Validación de pedido ya entregado con auditoría previa."""
    resp = client.post("/api/v1/pos/click-and-collect/validar", json={
        "codigo": "RET-345091"
    }, headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["estado"] == "entregada"
    assert data["es_entregable"] is False
    assert "YA FUE ENTREGADO" in (data["motivo_rechazo"] or "")
    assert data["despacho"] is not None
    assert data["despacho"]["receptor_nombre"] == "Roberto Doria Medina"


def test_validar_codigo_cancelado():
    """KAN-108: Validación de pedido cancelado."""
    resp = client.post("/api/v1/pos/click-and-collect/validar", json={
        "codigo": "RET-992381"
    }, headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["estado"] == "cancelada"
    assert data["es_entregable"] is False
    assert "CANCELADO" in (data["motivo_rechazo"] or "")


def test_validar_codigo_inexistente():
    """KAN-324: Código no encontrado retorna 404."""
    resp = client.post("/api/v1/pos/click-and-collect/validar", json={
        "codigo": "RET-INVALIDO-999"
    }, headers=admin_headers)
    assert resp.status_code == 404


def test_confirmar_entrega_click_and_collect():
    """KAN-325: Actualización a 'entregada' y registro de auditoría de despacho."""
    headers = cajero_headers

    payload = {
        "orden_id": "3b749d44-0db0-4e36-9694-84c1724490f1",
        "codigo_retiro": "RET-789214",
        "receptor_nombre": "Carlos Mendoza Patzi",
        "receptor_documento": "4829102",
        "receptor_tipo": "titular",
        "receptor_telefono": "+591 71234567",
        "observaciones": "Mercadería entregada en perfectas condiciones con caja sellada.",
        "cajero_id": "cajero-001",
        "cajero_nombre": "Oscar Menacho",
        "sucursal_id": "SUC-01",
        "sucursal_nombre": "Sucursal Central - La Paz"
    }

    resp = client.post("/api/v1/pos/click-and-collect/confirmar-entrega", json=payload, headers=headers)
    assert resp.status_code == 200
    res_data = resp.json()
    assert res_data["success"] is True
    assert res_data["nuevo_estado"] == "entregada"
    assert res_data["receptor_nombre"] == "Carlos Mendoza Patzi"
    assert "comprobante_entrega" in res_data
    assert res_data["comprobante_entrega"]["codigo_orden"] == "ORD-2026-CC101"

    # Segunda validación: ahora debe reflejar que ya fue entregado
    resp_val = client.post("/api/v1/pos/click-and-collect/validar", json={"codigo": "RET-789214"}, headers=admin_headers)
    assert resp_val.status_code == 200
    val_data = resp_val.json()
    assert val_data["estado"] == "entregada"
    assert val_data["es_entregable"] is False


def test_confirmar_entrega_rechazada_si_ya_entregada():
    """KAN-325: No se puede confirmar una entrega ya realizada."""
    headers = cajero_headers

    payload = {
        "orden_id": "c56b06e9-bfe9-4e7a-9a99-8ee3ad192305",
        "codigo_retiro": "RET-345091",
        "receptor_nombre": "Otro Receptor",
        "receptor_documento": "998877",
        "receptor_tipo": "tercero_autorizado"
    }

    resp = client.post("/api/v1/pos/click-and-collect/confirmar-entrega", json=payload, headers=headers)
    assert resp.status_code == 400
    assert "ya fue entregado" in resp.json()["detail"].lower()


def test_listado_requiere_sesion_de_cajero_o_administrador():
    assert client.get("/api/v1/pos/click-and-collect/pedidos").status_code == 401


def test_cajero_no_puede_consultar_otra_sucursal():
    token = create_access_token({"sub": "cajero-002", "role": "cajero", "sucursal_id": "SUC-02"})
    response = client.get(
        "/api/v1/pos/click-and-collect/pedidos?sucursal_id=SUC-01",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


class FakeQuery:
    def __init__(self, database, table):
        self.database = database
        self.table = table
        self.filters = []
        self.operation = "select"
        self.payload = None

    def select(self, *_args):
        return self

    def update(self, payload):
        self.operation = "update"
        self.payload = payload
        return self

    def insert(self, payload):
        self.operation = "insert"
        self.payload = payload
        return self

    def eq(self, field, value):
        self.filters.append((field, {str(value)}))
        return self

    def in_(self, field, values):
        self.filters.append((field, {str(value) for value in values}))
        return self

    def order(self, *_args, **_kwargs):
        return self

    def limit(self, *_args):
        return self

    def execute(self):
        rows = self.database.tables.get(self.table, [])
        matched = [
            row for row in rows
            if all(str(row.get(field)) in values for field, values in self.filters)
        ]
        if self.operation == "insert":
            rows.append(self.payload)
            return SimpleNamespace(data=[self.payload])
        if self.operation == "update":
            for row in matched:
                row.update(self.payload)
            return SimpleNamespace(data=matched)
        return SimpleNamespace(data=matched)


class FakeSupabase:
    def __init__(self, tables):
        self.tables = tables

    def table(self, name):
        return FakeQuery(self, name)


def test_listado_incluye_orden_de_retiro_pagada_en_supabase(monkeypatch):
    order_id = str(uuid.uuid4())
    branch_id = "b0000000-0000-0000-0000-000000000001"
    database = FakeSupabase({
        "ordenes": [{
            "id": order_id,
            "codigo_orden": "ORD-CC-PERSISTIDA",
            "cliente_id": str(uuid.uuid4()),
            "sucursal_id": branch_id,
            "canal": "web",
            "tipo_despacho": "retiro_sucursal",
            "estado": "confirmada",
            "created_at": "2026-10-22T12:00:00Z",
            "subtotal": "100",
            "descuento": "0",
            "total": "100",
            "perfiles_clientes": {"nombre_completo": "Cliente de prueba", "nit_ci": "1234567"},
            "orden_items": [{
                "sku": "SKU-CC-1",
                "nombre_producto": "Producto Click Collect",
                "cantidad": 1,
                "precio_unitario": "100",
                "total_linea": "100",
            }],
        }],
        "pagos": [{"orden_id": order_id, "metodo": "qr", "estado": "aprobado"}],
        "audit_logs": [],
    })
    monkeypatch.setattr(pos_routers, "_get_supabase_safe", lambda: database)
    token = create_access_token({"sub": "cajero-001", "role": "cajero", "sucursal_id": branch_id})

    response = client.get(
        "/api/v1/pos/click-and-collect/pedidos",
        params={"sucursal_id": branch_id, "filtro_estado": "pendientes"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200, response.text
    order = next(item for item in response.json() if item["codigo_orden"] == "ORD-CC-PERSISTIDA")
    assert order["orden_id"] == order_id
    assert order["es_entregable"] is True
    assert order["codigo_retiro"].startswith("RET-")
    assert order["cliente_nombre"] == "Cliente de prueba"


def test_confirmar_entrega_persistida_actualiza_estado_y_auditoria(monkeypatch):
    order_id = str(uuid.uuid4())
    branch_id = "b0000000-0000-0000-0000-000000000001"
    database = FakeSupabase({
        "ordenes": [{
            "id": order_id,
            "codigo_orden": "ORD-CC-PERSISTIDA-ENTREGA",
            "sucursal_id": branch_id,
            "tipo_despacho": "retiro_sucursal",
            "estado": "confirmada",
            "created_at": "2026-10-22T12:00:00Z",
            "subtotal": "100",
            "descuento": "0",
            "total": "100",
            "perfiles_clientes": {"nombre_completo": "Cliente de prueba", "nit_ci": "1234567"},
            "orden_items": [{
                "sku": "SKU-CC-2",
                "nombre_producto": "Producto Click Collect",
                "cantidad": 1,
                "precio_unitario": "100",
                "total_linea": "100",
            }],
        }],
        "pagos": [{"orden_id": order_id, "metodo": "qr", "estado": "aprobado"}],
        "audit_logs": [],
    })
    monkeypatch.setattr(pos_routers, "_get_supabase_safe", lambda: database)
    token = create_access_token({"sub": "cajero-003", "role": "cajero", "sucursal_id": branch_id})
    headers = {"Authorization": f"Bearer {token}"}
    codigo_retiro = pos_routers._codigo_retiro_orden(order_id)

    response = client.post(
        "/api/v1/pos/click-and-collect/confirmar-entrega",
        headers=headers,
        json={
            "orden_id": order_id,
            "codigo_retiro": codigo_retiro,
            "receptor_nombre": "Cliente de prueba",
            "receptor_documento": "1234567",
            "receptor_tipo": "titular",
            "sucursal_id": branch_id,
            "sucursal_nombre": "Sucursal Central - La Paz",
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["nuevo_estado"] == "entregada"
    assert database.tables["ordenes"][0]["estado"] == "entregada"
    assert database.tables["audit_logs"][0]["action"] == "DESPACHO_CLICK_AND_COLLECT"

    duplicate = client.post(
        "/api/v1/pos/click-and-collect/confirmar-entrega",
        headers=headers,
        json={
            "orden_id": order_id,
            "codigo_retiro": codigo_retiro,
            "receptor_nombre": "Cliente de prueba",
            "receptor_documento": "1234567",
            "receptor_tipo": "titular",
            "sucursal_id": branch_id,
        },
    )
    assert duplicate.status_code == 400

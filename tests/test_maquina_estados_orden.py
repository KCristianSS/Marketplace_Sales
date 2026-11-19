"""Máquina de estados de la orden (RF-28) y su relación con la cancelación con saga (RF-31/RF-33)."""
import uuid

import pytest
from fastapi.testclient import TestClient

from backend.services.ordenes.app import routers as ordenes_routers
from backend.services.ordenes.app.main import app as ordenes_app
from backend.shared.security import create_access_token

client = TestClient(ordenes_app)


def _headers(role: str) -> dict:
    return {"Authorization": f"Bearer {create_access_token({'sub': str(uuid.uuid4()), 'role': role})}"}


@pytest.fixture
def orden_confirmada():
    cliente_id = str(uuid.uuid4())
    resp = client.post("/api/v1/ordenes/", json={
        "cliente_id": cliente_id,
        "canal": "web",
        "tipo_despacho": "domicilio",
        "subtotal": 300.0,
        "total": 300.0,
        "metodo_pago": "tarjeta",
        "items": [{
            "variante_id": str(uuid.uuid4()),
            "sku": "SKU-ESTADOS",
            "nombre_producto": "Producto de estados",
            "cantidad": 1,
            "precio_unitario": 300.0,
        }],
    }, headers=_headers("cliente"))
    assert resp.status_code == 201, resp.text
    return resp.json()


def _transicion(orden_id: str, nuevo_estado: str, role: str = "administrador"):
    return client.patch(
        f"/api/v1/ordenes/{orden_id}/estado",
        json={"nuevo_estado": nuevo_estado},
        headers=_headers(role),
    )


def test_recorre_el_ciclo_de_vida_completo_y_audita_cada_transicion(orden_confirmada):
    orden_id = orden_confirmada["id"]
    for estado in ("en_preparacion", "despachada", "entregada"):
        resp = _transicion(orden_id, estado)
        assert resp.status_code == 200, resp.text
        assert resp.json()["estado"] == estado

    historial = resp.json()["historial_estados"]
    assert [h["estado_nuevo"] for h in historial] == ["en_preparacion", "despachada", "entregada"]
    assert all(h["usuario_id"] and h["cambiado_en"] for h in historial)


def test_rechaza_saltar_estados(orden_confirmada):
    resp = _transicion(orden_confirmada["id"], "entregada")
    assert resp.status_code == 422
    assert "no permitida" in resp.json()["detail"]


def test_no_permite_cancelar_sin_la_saga_de_reversion(orden_confirmada):
    resp = _transicion(orden_confirmada["id"], "cancelada")
    assert resp.status_code == 422
    assert "/cancelar" in resp.json()["detail"]


def test_cliente_no_puede_cambiar_estados(orden_confirmada):
    resp = _transicion(orden_confirmada["id"], "en_preparacion", role="cliente")
    assert resp.status_code == 403


def test_carga_la_orden_persistida_si_no_esta_en_memoria(orden_confirmada, monkeypatch):
    orden_id = orden_confirmada["id"]
    orden = ordenes_routers._ORDENES_DB.pop(orden_id)

    async def obtener_desde_base(id):
        return orden

    monkeypatch.setattr(ordenes_routers, "obtener_orden", obtener_desde_base)
    resp = _transicion(orden_id, "en_preparacion")
    assert resp.status_code == 200, resp.text
    assert resp.json()["estado"] == "en_preparacion"

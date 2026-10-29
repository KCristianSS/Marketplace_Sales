import sys
import os
import uuid
import asyncio
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from backend.services.ordenes.app.main import app as ordenes_app
from backend.shared.erp_clients.pagos import PagosClient

client = TestClient(ordenes_app)


def test_emision_factura_fallback_no_inventa_datos_fiscales(monkeypatch):
    async def devolver_fallback(self, path, json_data):
        return {"status": "fallback", "error": "ERP no disponible"}

    monkeypatch.setattr(PagosClient, "post", devolver_fallback)
    resultado = asyncio.run(PagosClient().emitir_factura({"monto_total": 100}))

    assert resultado["estado"] == "pendiente"
    assert resultado["numero_factura"] is None
    assert resultado["cuf"] is None
    assert resultado["modo"] == "fallback"

def test_iniciar_pago_qr_rio_pag_01():
    """US-16 · RIO-PAG-01: Generación de token y QR dinámico para pago con QR Simple."""
    resp = client.post("/api/v1/pagos/iniciar", json={
        "monto": 250.50,
        "moneda": "BOB",
        "metodo_pago": "qr",
        "cliente_id": "cliente-test-01",
        "descripcion": "Orden de prueba QR"
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["transaccion_id"].startswith("TX-PAG-")
    assert data["token_pago"].startswith("TOK-PAG-")
    assert data["estado"] == "pendiente"
    assert data["monto"] == 250.50
    assert data["moneda"] == "BOB"
    assert data["qr_payload"] is not None
    assert "MAXI-QR" in data["qr_payload"]
    assert data["expira_en_segundos"] == 900

def test_iniciar_pago_tarjeta():
    """US-16: Procesamiento de pago directo con tarjeta de crédito/débito."""
    resp = client.post("/api/v1/pagos/iniciar", json={
        "monto": 120.00,
        "moneda": "BOB",
        "metodo_pago": "tarjeta",
        "cliente_id": "cliente-test-02",
        "datos_tarjeta": {
            "numero_tarjeta": "4532 8812 3456 7890",
            "nombre_titular": "CARLOS MENDOZA",
            "fecha_vencimiento": "12/28",
            "cvv": "321"
        }
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["transaccion_id"].startswith("TX-PAG-")
    assert data["token_pago"].startswith("TOK-PAG-")
    assert data["estado"] == "aprobado"
    assert data["codigo_autorizacion"] is not None

def test_iniciar_pago_tarjeta_invalida():
    """Validación de tarjeta rechaza número incompleto."""
    resp = client.post("/api/v1/pagos/iniciar", json={
        "monto": 100.00,
        "metodo_pago": "tarjeta",
        "datos_tarjeta": {
            "numero_tarjeta": "123", # Demasiado corto
            "nombre_titular": "TEST",
            "fecha_vencimiento": "05/25",
            "cvv": "111"
        }
    })
    assert resp.status_code == 422

def test_iniciar_pago_pasarela():
    """US-16: Redirección a pasarela externa con token seguro."""
    resp = client.post("/api/v1/pagos/iniciar", json={
        "monto": 450.00,
        "metodo_pago": "pasarela",
        "cliente_id": "cliente-test-03"
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["estado"] == "pendiente"
    assert data["redirect_url"] is not None
    assert "pasarela.maxiconecta.bo" in data["redirect_url"]

def test_consultar_estado_transaccion():
    """US-16: Consulta en tiempo real del estado de pago para polling del frontend."""
    # Iniciar pago
    resp_init = client.post("/api/v1/pagos/iniciar", json={
        "monto": 300.00,
        "metodo_pago": "qr"
    })
    tx_id = resp_init.json()["transaccion_id"]

    # Consultar
    resp_get = client.get(f"/api/v1/pagos/transacciones/{tx_id}")
    assert resp_get.status_code == 200
    data = resp_get.json()
    assert data["transaccion_id"] == tx_id
    assert data["estado"] == "pendiente"

def test_webhook_pago_aprobado():
    """US-16: Webhook receptor de notificación bancaria de aprobación."""
    resp_init = client.post("/api/v1/pagos/iniciar", json={
        "monto": 180.00,
        "metodo_pago": "qr"
    })
    tx_id = resp_init.json()["transaccion_id"]

    # Simular llamada del banco al webhook
    resp_wh = client.post("/api/v1/pagos/webhook", json={
        "transaccion_id": tx_id,
        "evento": "pago.aprobado",
        "codigo_autorizacion": "AUTH-BANCO-9988"
    })
    assert resp_wh.status_code == 200
    wh_data = resp_wh.json()
    assert wh_data["recibido"] is True
    assert wh_data["nuevo_estado"] == "aprobado"

    # Verificar estado actualizado
    resp_check = client.get(f"/api/v1/pagos/transacciones/{tx_id}")
    assert resp_check.json()["estado"] == "aprobado"
    assert resp_check.json()["codigo_autorizacion"] == "AUTH-BANCO-9988"

def test_webhook_pago_rechazado_y_compensacion():
    """US-16: Webhook receptor de rechazo bancario."""
    resp_init = client.post("/api/v1/pagos/iniciar", json={
        "monto": 500.00,
        "metodo_pago": "qr",
        "reserva_id": "RES-TEST-ROLLBACK"
    })
    tx_id = resp_init.json()["transaccion_id"]

    resp_wh = client.post("/api/v1/pagos/webhook", json={
        "transaccion_id": tx_id,
        "evento": "pago.rechazado",
        "motivo_rechazo": "Fondos insuficientes en cuenta"
    })
    assert resp_wh.status_code == 200
    assert resp_wh.json()["nuevo_estado"] == "rechazado"

    resp_check = client.get(f"/api/v1/pagos/transacciones/{tx_id}")
    assert resp_check.json()["estado"] == "rechazado"
    assert resp_check.json()["motivo_rechazo"] == "Fondos insuficientes en cuenta"

def test_simular_webhook_qa():
    """US-16: Endpoint de simulación para QA / pruebas interactivas del frontend."""
    resp_init = client.post("/api/v1/pagos/iniciar", json={
        "monto": 75.00,
        "metodo_pago": "qr"
    })
    tx_id = resp_init.json()["transaccion_id"]

    resp_sim = client.post("/api/v1/pagos/simular-webhook", json={
        "transaccion_id": tx_id,
        "resultado": "aprobado"
    })
    assert resp_sim.status_code == 200
    assert resp_sim.json()["nuevo_estado"] == "aprobado"

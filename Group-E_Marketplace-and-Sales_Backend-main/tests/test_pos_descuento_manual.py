"""
Pruebas automatizadas de la Historia de Usuario KAN-10 / KAN-345 (RF-10):
Autorización de Descuento Manual por Ítem o Total del Ticket por Supervisor.

Criterios de Aceptación evaluados:
1. Sin autorización de supervisor, el descuento manual no se aplica a la venta.
2. PIN incorrecto tres veces seguidas bloquea al supervisor por 5 minutos.
3. Descuento mayor al tope configurado (30%) es rechazado con mensaje claro.
4. Descuento autorizado se refleja en el ticket (monto, motivo, supervisor) y en audit_logs.
5. La autorización es de un solo uso y vence a los 2 minutos.
"""

import sys
import os
import uuid
from decimal import Decimal
from datetime import datetime, timedelta, timezone

# Asegurar path de importación del backend
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

import pytest
from fastapi.testclient import TestClient
from backend.services.pos.app.main import app as pos_app
from backend.services.pos.app.services import (
    abrir_turno,
    DescuentoManualService,
    _SUPERVISOR_PINS_MEMORIA,
    _AUTORIZACIONES_DESCUENTO_MEMORIA,
    _AUDIT_LOGS_MEMORIA,
)
from backend.shared.security import create_access_token

client = TestClient(pos_app)


def _cajero_headers(cajero_id: str = None, sucursal_id: str = None):
    cid = cajero_id or str(uuid.uuid4())
    sid = sucursal_id or str(uuid.uuid4())
    token = create_access_token({
        "sub": cid,
        "role": "cajero",
        "sucursal_id": sid,
        "email": "cajero@maxiconecta.bo",
        "nombre_completo": "Oscar Menacho",
    })
    return {"Authorization": f"Bearer {token}"}, cid, sid


# ---------------------------------------------------------------------------
# Test 1: Descuento sin autorización es rechazado (Criterio 1)
# ---------------------------------------------------------------------------
def test_descuento_manual_rechazado_sin_autorizacion():
    headers, cid, sid = _cajero_headers()

    # Abrir caja para la prueba
    res_open = client.post("/api/v1/pos/caja/abrir", json={
        "sucursal_id": sid,
        "cajero_id": cid,
        "fondo_inicial": 200.0,
    }, headers=headers)
    assert res_open.status_code == 201
    caja_id = res_open.json()["id"]

    # Intentar vender aplicando descuento manual sin enviar autorizacion_descuento_id
    payload_sin_auth = {
        "caja_id": caja_id,
        "sucursal_id": sid,
        "cliente_nit_ci": "0",
        "cliente_razon_social": "Consumidor Final",
        "modalidad": "sin_factura",
        "items": [
            {
                "variante_id": str(uuid.uuid4()),
                "sku": "LAP-DELL-XPS15",
                "nombre": "Laptop Dell XPS 15",
                "cantidad": 1,
                "precio_unitario": 6000.0,
                "descuento_unitario": 600.0, # 10% sin autorizar
                "autorizacion_descuento_id": None,
            }
        ],
        "metodo_pago": "efectivo",
    }

    res_venta = client.post("/api/v1/pos/ventas/cobrar", json=payload_sin_auth, headers=headers)
    assert res_venta.status_code == 422
    assert "requiere autorización de supervisor" in res_venta.json()["detail"]


# ---------------------------------------------------------------------------
# Test 2: Descuento que supera el tope del 30% es rechazado (Criterio 3)
# ---------------------------------------------------------------------------
def test_descuento_manual_rechazado_si_supera_tope_30():
    headers, cid, sid = _cajero_headers()

    # Solicitar autorización con 35% de descuento
    payload_excesivo = {
        "supervisor_username": "supervisor",
        "pin": "1234",
        "tipo": "item",
        "porcentaje": 35.0, # Supera el tope de 30%
        "monto_base": 1000.0,
        "motivo": "Empaque roto y rayón",
        "item_sku": "MOU-LOG-MX3S",
    }

    res = client.post("/api/v1/pos/descuentos/autorizar", json=payload_excesivo, headers=headers)
    assert res.status_code == 422
    assert "supera el tope máximo permitido de 30" in res.json()["detail"]


# ---------------------------------------------------------------------------
# Test 3: Tres PINs erróneos consecutivos bloquean 5 minutos al supervisor (Criterio 2)
# ---------------------------------------------------------------------------
def test_bloqueo_supervisor_por_3_intentos_fallidos():
    headers, cid, sid = _cajero_headers()

    # Resetear supervisor de prueba
    _SUPERVISOR_PINS_MEMORIA["supervisor"]["intentos_fallidos"] = 0
    _SUPERVISOR_PINS_MEMORIA["supervisor"]["bloqueado_hasta"] = None

    payload_fallo = {
        "supervisor_username": "supervisor",
        "pin": "9999", # PIN incorrecto
        "tipo": "item",
        "porcentaje": 15.0,
        "monto_base": 500.0,
        "motivo": "Promoción",
    }

    # Intento 1 fallido
    res1 = client.post("/api/v1/pos/descuentos/autorizar", json=payload_fallo, headers=headers)
    assert res1.status_code == 401
    assert "2 intento(s) antes del bloqueo" in res1.json()["detail"]

    # Intento 2 fallido
    res2 = client.post("/api/v1/pos/descuentos/autorizar", json=payload_fallo, headers=headers)
    assert res2.status_code == 401
    assert "1 intento(s) antes del bloqueo" in res2.json()["detail"]

    # Intento 3 fallido: debe bloquear al supervisor por 5 minutos
    res3 = client.post("/api/v1/pos/descuentos/autorizar", json=payload_fallo, headers=headers)
    assert res3.status_code in (401, 423)
    assert "bloqueado por 5 minutos" in res3.json()["detail"]

    # Intento 4 inmediato con PIN correcto debe ser rechazado por bloqueo activo
    payload_correcto = {**payload_fallo, "pin": "1234"}
    res4 = client.post("/api/v1/pos/descuentos/autorizar", json=payload_correcto, headers=headers)
    assert res4.status_code == 423
    assert "bloqueado" in res4.json()["detail"]

    # Limpiar bloqueo para siguientes pruebas
    _SUPERVISOR_PINS_MEMORIA["supervisor"]["intentos_fallidos"] = 0
    _SUPERVISOR_PINS_MEMORIA["supervisor"]["bloqueado_hasta"] = None


# ---------------------------------------------------------------------------
# Test 4: Autorización exitosa, aplicación en venta y reflejo en ticket y audit (Criterios 4 y 5)
# ---------------------------------------------------------------------------
def test_autorizacion_exitosa_y_aplicacion_en_venta_pos():
    headers, cid, sid = _cajero_headers()

    # Abrir caja si no hay una activa
    caja_id = str(uuid.uuid4())
    _SUPERVISOR_PINS_MEMORIA["supervisor"]["intentos_fallidos"] = 0
    _SUPERVISOR_PINS_MEMORIA["supervisor"]["bloqueado_hasta"] = None

    # 1. Autorizar descuento del 20% en ítem
    res_auth = client.post("/api/v1/pos/descuentos/autorizar", json={
        "supervisor_username": "supervisor",
        "pin": "1234",
        "tipo": "item",
        "porcentaje": 20.0,
        "monto_base": 1000.0,
        "motivo": "Empaque dañado en transporte",
        "item_sku": "KEY-RGB-01",
    }, headers=headers)

    assert res_auth.status_code == 200
    auth_data = res_auth.json()
    auth_id = auth_data["autorizacion_id"]
    assert auth_id.startswith("AUTH-DESC-")
    assert float(auth_data["monto_descuento"]) == 200.0
    assert auth_data["supervisor_nombre"] == "Carlos Ramos (Supervisor de Turno)"

    # Asegurar caja abierta para el cobro
    res_caja = client.post("/api/v1/pos/caja/abrir", json={
        "sucursal_id": sid,
        "cajero_id": cid,
        "fondo_inicial": 300.0,
    }, headers=headers)
    caja_id = res_caja.json()["id"] if res_caja.status_code == 201 else client.get("/api/v1/pos/caja/activa", headers=headers).json()["id"]

    # 2. Procesar venta POS aplicando la autorización
    res_venta = client.post("/api/v1/pos/ventas/cobrar", json={
        "caja_id": caja_id,
        "sucursal_id": sid,
        "cliente_nit_ci": "0",
        "cliente_razon_social": "Consumidor Final",
        "modalidad": "sin_factura",
        "items": [
            {
                "variante_id": str(uuid.uuid4()),
                "sku": "KEY-RGB-01",
                "nombre": "Teclado Mecánico RGB",
                "cantidad": 1,
                "precio_unitario": 1000.0,
                "descuento_unitario": 200.0,
                "autorizacion_descuento_id": auth_id,
            }
        ],
        "metodo_pago": "efectivo",
    }, headers=headers)

    assert res_venta.status_code == 201
    venta_data = res_venta.json()

    # Total debe ser 800.00 (1000 - 200)
    assert float(venta_data["total"]) == 800.0
    assert float(venta_data["descuento_total"]) == 200.0

    # Criterio 4: El ticket impreso debe reflejar monto descontado, motivo y supervisor
    ticket_txt = venta_data["ticket_impresion"]
    assert "DESCUENTOS MANUALES AUTORIZADOS:" in ticket_txt
    assert "Empaque dañado en transporte" in ticket_txt
    assert "Carlos Ramos (Supervisor de Turno)" in ticket_txt
    assert "BOB 200.00" in ticket_txt or "200.00" in ticket_txt

    # Validar que se registró en audit_logs
    audits = [a for a in _AUDIT_LOGS_MEMORIA if a.get("action") == "DESCUENTO_MANUAL_APLICADO_TICKET"]
    assert len(audits) >= 1
    ultimo_audit = audits[-1]
    assert ultimo_audit["payload_after"]["autorizacion_token"] == "[REDACTED]"
    assert ultimo_audit["payload_after"]["motivo"] == "Empaque dañado en transporte"


# ---------------------------------------------------------------------------
# Test 5: La autorización es de UN SOLO USO (Criterio 5)
# ---------------------------------------------------------------------------
def test_autorizacion_es_de_un_solo_uso():
    headers, cid, sid = _cajero_headers()

    # 1. Autorizar descuento
    res_auth = client.post("/api/v1/pos/descuentos/autorizar", json={
        "supervisor_username": "supervisor",
        "pin": "1234",
        "tipo": "item",
        "porcentaje": 10.0,
        "monto_base": 500.0,
        "motivo": "Promoción especial",
        "item_sku": "MOU-01",
    }, headers=headers)
    auth_id = res_auth.json()["autorizacion_id"]

    res_caja = client.post("/api/v1/pos/caja/abrir", headers=headers, json={
        "sucursal_id": sid, "cajero_id": cid, "fondo_inicial": 0,
    })
    assert res_caja.status_code == 201, res_caja.text
    caja_id = res_caja.json()["id"]

    # 2. Primer uso exitoso
    res_primera = client.post("/api/v1/pos/ventas/cobrar", json={
        "caja_id": caja_id,
        "sucursal_id": sid,
        "items": [
            {
                "variante_id": str(uuid.uuid4()),
                "sku": "MOU-01",
                "nombre": "Mouse Óptico",
                "cantidad": 1,
                "precio_unitario": 500.0,
                "descuento_unitario": 50.0,
                "autorizacion_descuento_id": auth_id,
            }
        ],
        "metodo_pago": "efectivo",
    }, headers=headers)
    assert res_primera.status_code == 201

    # 3. Segundo intento de uso con el mismo token: debe ser rechazado
    res_segunda = client.post("/api/v1/pos/ventas/cobrar", json={
        "caja_id": caja_id,
        "sucursal_id": sid,
        "items": [
            {
                "variante_id": str(uuid.uuid4()),
                "sku": "MOU-01",
                "nombre": "Mouse Óptico",
                "cantidad": 1,
                "precio_unitario": 500.0,
                "descuento_unitario": 50.0,
                "autorizacion_descuento_id": auth_id,
            }
        ],
        "metodo_pago": "efectivo",
    }, headers=headers)
    assert res_segunda.status_code == 422
    assert "ya fue utilizada previamente" in res_segunda.json()["detail"]


# ---------------------------------------------------------------------------
# Test 6: Descuento manual sobre el total del ticket autorizado por supervisor
# ---------------------------------------------------------------------------
def test_descuento_manual_sobre_total_del_ticket():
    headers, cid, sid = _cajero_headers()

    res_auth = client.post("/api/v1/pos/descuentos/autorizar", json={
        "supervisor_username": "gerente",
        "pin": "8888",
        "tipo": "total",
        "porcentaje": 15.0,
        "monto_base": 2000.0,
        "motivo": "Cortesía gerencia comercial a cliente VIP",
    }, headers=headers)
    assert res_auth.status_code == 200
    auth_total_id = res_auth.json()["autorizacion_id"]
    assert float(res_auth.json()["monto_descuento"]) == 300.0

    res_caja = client.post("/api/v1/pos/caja/abrir", headers=headers, json={
        "sucursal_id": sid, "cajero_id": cid, "fondo_inicial": 0,
    })
    assert res_caja.status_code == 201, res_caja.text
    caja_id = res_caja.json()["id"]

    res_venta = client.post("/api/v1/pos/ventas/cobrar", json={
        "caja_id": caja_id,
        "sucursal_id": sid,
        "items": [
            {
                "variante_id": str(uuid.uuid4()),
                "sku": "PROD-VIP",
                "nombre": "Pack Premium",
                "cantidad": 1,
                "precio_unitario": 2000.0,
            }
        ],
        "autorizacion_descuento_total_id": auth_total_id,
        "metodo_pago": "efectivo",
    }, headers=headers)

    assert res_venta.status_code == 201
    data = res_venta.json()
    assert float(data["total"]) == 1700.0
    assert float(data["descuento_total"]) == 300.0
    assert "Cortesía gerencia comercial a cliente VIP" in data["ticket_impresion"]
    assert "Mariana López (Gerente Comercial)" in data["ticket_impresion"]

import sys
import os
import uuid

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from fastapi.testclient import TestClient
from backend.services.pos.app import routers as pos_routers
from backend.services.pos.app import services as pos_services
from backend.services.pos.app.main import app as pos_app
from backend.shared.security import create_access_token


client = TestClient(pos_app)


def test_cajero_anula_venta_con_autorizacion_supervisor(monkeypatch):
    caja_id = str(uuid.uuid4())
    orden_id = str(uuid.uuid4())
    cajero_id = str(uuid.uuid4())
    sucursal_id = str(uuid.uuid4())
    events = []
    monkeypatch.setattr(pos_services, "get_supabase_client", lambda: None)
    ticket = {
        "orden_id": orden_id,
        "codigo_orden": "POS-ANULAR-01",
        "total": 120,
        "metodo_pago": "tarjeta",
        "desglose_pagos": [{
            "metodo": "tarjeta",
            "monto": 120,
            "transaccion_id": "TX-POS-ANULAR-01",
            "estado": "aprobado",
            "referencia": "9912",
            "cambio": 0,
        }],
        "items": [{"sku": "SKU-ANULAR-1", "nombre": "Producto de prueba", "cantidad": 1}],
        "factura_estado": "autorizada",
        "cuf": "CUF-ANULAR-1",
        "numero_factura": 123,
        "estado_venta": "completada",
    }
    venta = {
        "orden_id": orden_id,
        "codigo_orden": "POS-ANULAR-01",
        "caja_turno_id": caja_id,
        "cajero_id": cajero_id,
        "sucursal_id": sucursal_id,
        "total": 120,
        "ticket": ticket,
        "_persistido": False,
    }
    pos_routers._VENTAS_POS_EN_MEMORIA[orden_id] = venta

    async def caja_abierta(_caja_id):
        return {"id": caja_id, "estado": "abierta", "cajero_id": cajero_id, "sucursal_id": sucursal_id}

    async def reintegrar_stock(order, items, **kwargs):
        events.append(("stock", order, items, kwargs))
        return {"status": "REINGRESADO"}

    async def descontar_stock(items, orden_id, **kwargs):
        events.append(("stock_compensation", orden_id))
        return {"status": "DESCONTADO"}

    async def reembolsar(tx, amount):
        events.append(("payment_reversal", tx, amount))
        return {"reembolso_estado": "procesado", "nota_credito": "NC-ANULAR-01"}

    async def registrar_reversion(payload):
        events.append(("accounting_reversal", payload["orden_id"]))
        return {"estado": "revertido"}

    async def acumular(caja, method, amount):
        events.append(("cash_total", caja, method, str(amount)))

    def movement(caja, tipo, amount, description):
        events.append(("cash_movement", caja, tipo, str(amount), description))
        return {"id": "movement-1"}

    monkeypatch.setattr(pos_routers, "get_supabase_admin_client", lambda: None)
    monkeypatch.setattr(pos_routers, "obtener_caja", caja_abierta)
    monkeypatch.setattr(pos_routers.inventarios_client, "reingreso_por_devolucion", reintegrar_stock)
    monkeypatch.setattr(pos_routers.inventarios_client, "descuento_directo", descontar_stock)
    monkeypatch.setattr(pos_routers.pagos_client, "reversar_cobro", reembolsar)
    monkeypatch.setattr(pos_routers.contabilidad_client, "registrar_reversion", registrar_reversion)
    monkeypatch.setattr(pos_routers, "acumular_venta", acumular)
    monkeypatch.setattr(pos_routers, "registrar_movimiento", movement)

    cashier_token = create_access_token({"sub": cajero_id, "role": "cajero"})
    headers = {
        "Authorization": f"Bearer {cashier_token}",
    }
    payload = {"caja_id": caja_id, "motivo": "Cobro duplicado por error", "supervisor_username": "gerente", "pin": "8888"}

    response = client.post(f"/api/v1/pos/ventas/{orden_id}/anular", headers=headers, json=payload)

    assert response.status_code == 200, response.text
    result = response.json()
    assert result["success"] is True
    assert result["estado_venta"] == "anulada"
    assert result["autorizada_por"] == "Mariana López (Gerente Comercial)"
    assert result["notas_credito"] == ["NC-ANULAR-01"]
    assert venta["ticket"]["estado_venta"] == "anulada"
    assert any(event[0] == "stock" for event in events)
    assert any(event[0] == "payment_reversal" for event in events)
    assert any(event[0] == "accounting_reversal" for event in events)
    assert any(event[0] == "cash_total" and float(event[3]) == -120 for event in events)

    duplicate = client.post(f"/api/v1/pos/ventas/{orden_id}/anular", headers=headers, json=payload)
    assert duplicate.status_code == 409


def test_anulacion_requiere_pin_de_supervisor(monkeypatch):
    caja_id = str(uuid.uuid4())
    orden_id = str(uuid.uuid4())
    cajero_id = str(uuid.uuid4())
    pos_routers._VENTAS_POS_EN_MEMORIA[orden_id] = {
        "orden_id": orden_id,
        "codigo_orden": "POS-ANULAR-02",
        "caja_turno_id": caja_id,
        "cajero_id": cajero_id,
        "ticket": {"estado_venta": "completada", "total": 20},
        "_persistido": False,
    }

    async def caja_abierta(_caja_id):
        return {"id": caja_id, "estado": "abierta", "cajero_id": cajero_id}

    monkeypatch.setattr(pos_routers, "get_supabase_admin_client", lambda: None)
    monkeypatch.setattr(pos_routers, "obtener_caja", caja_abierta)
    cashier_token = create_access_token({"sub": cajero_id, "role": "cajero"})

    response = client.post(
        f"/api/v1/pos/ventas/{orden_id}/anular",
        headers={"Authorization": f"Bearer {cashier_token}"},
        json={"caja_id": caja_id, "motivo": "Error de cobro"},
    )

    assert response.status_code == 422


def test_fallo_de_reembolso_compensa_stock_y_no_anula_venta(monkeypatch):
    caja_id = str(uuid.uuid4())
    orden_id = str(uuid.uuid4())
    cajero_id = str(uuid.uuid4())
    events = []
    monkeypatch.setattr(pos_services, "get_supabase_client", lambda: None)
    venta = {
        "orden_id": orden_id,
        "codigo_orden": "POS-ANULAR-03",
        "caja_turno_id": caja_id,
        "cajero_id": cajero_id,
        "sucursal_id": str(uuid.uuid4()),
        "total": 50,
        "ticket": {
            "orden_id": orden_id,
            "codigo_orden": "POS-ANULAR-03",
            "total": 50,
            "metodo_pago": "tarjeta",
            "desglose_pagos": [{"metodo": "tarjeta", "monto": 50, "transaccion_id": "TX-FAIL"}],
            "items": [{"sku": "SKU-FAIL", "cantidad": 1}],
            "estado_venta": "completada",
        },
        "_persistido": False,
    }
    pos_routers._VENTAS_POS_EN_MEMORIA[orden_id] = venta

    async def caja_abierta(_caja_id):
        return {"id": caja_id, "estado": "abierta", "cajero_id": cajero_id, "sucursal_id": venta["sucursal_id"]}

    async def reintegrar_stock(*_args, **_kwargs):
        events.append("reintegrar")
        return {"status": "REINGRESADO"}

    async def descontar_stock(*_args, **_kwargs):
        events.append("compensar_stock")
        return {"status": "DESCONTADO"}

    async def rechazar_reembolso(*_args, **_kwargs):
        return {"estado": "rechazado", "mensaje": "Reembolso rechazado"}

    monkeypatch.setattr(pos_routers, "get_supabase_admin_client", lambda: None)
    monkeypatch.setattr(pos_routers, "obtener_caja", caja_abierta)
    monkeypatch.setattr(pos_routers.inventarios_client, "reingreso_por_devolucion", reintegrar_stock)
    monkeypatch.setattr(pos_routers.inventarios_client, "descuento_directo", descontar_stock)
    monkeypatch.setattr(pos_routers.pagos_client, "reversar_cobro", rechazar_reembolso)
    cashier_token = create_access_token({"sub": cajero_id, "role": "cajero"})

    response = client.post(
        f"/api/v1/pos/ventas/{orden_id}/anular",
        headers={
            "Authorization": f"Bearer {cashier_token}",
            },
        json={"caja_id": caja_id, "motivo": "Cobro erróneo", "supervisor_username": "admin", "pin": "4321"},
    )

    assert response.status_code == 502
    assert response.json()["detail"]["estado_venta"] == "completada"
    assert venta["ticket"]["estado_venta"] == "completada"
    assert events == ["reintegrar", "compensar_stock"]

def test_anulacion_rechaza_pin_incorrecto(monkeypatch):
    monkeypatch.setattr(pos_services, "get_supabase_client", lambda: None)
    monkeypatch.setitem(pos_services._SUPERVISOR_PINS_MEMORIA, "supervisor", dict(pos_services._SUPERVISOR_PINS_DEFAULT["supervisor"]))
    token = create_access_token({"sub": str(uuid.uuid4()), "role": "cajero"})
    response = client.post(f"/api/v1/pos/ventas/{uuid.uuid4()}/anular", headers={"Authorization": f"Bearer {token}"}, json={"caja_id": str(uuid.uuid4()), "motivo": "Error de cobro", "supervisor_username": "supervisor", "pin": "0000"})
    assert response.status_code == 401
    assert pos_services._SUPERVISOR_PINS_MEMORIA["supervisor"]["intentos_fallidos"] == 1

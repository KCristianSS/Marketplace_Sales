"""
Pruebas automatizadas del Pago Dividido (efectivo + tarjeta + QR en una misma venta).

Cubre el cobro POS, la emisión de factura POS, la creación de órdenes web, la
integridad ante rechazos (saga compensatoria) y el OrderPaidEvent con desglose
hacia Contabilidad.
Ejecutar con: python -m pytest backend/tests/test_pago_dividido.py
"""
import asyncio
import os
import sys
import uuid
from decimal import Decimal

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from fastapi.testclient import TestClient

from backend.services.ordenes.app.main import app as ordenes_app
from backend.services.pos.app.main import app as pos_app
from backend.shared import stock_ledger
from backend.shared.erp_clients.contabilidad import contabilidad_client
from backend.shared.erp_clients.pagos import pagos_client
from backend.shared.pagos_divididos import PagoInvalidoError, PagoParcial, normalizar_pagos
from backend.shared.security import create_access_token

pos_client = TestClient(pos_app)
ordenes_client = TestClient(ordenes_app)


# ------------------------------------------------------------------------------
# Fixtures y utilidades
# ------------------------------------------------------------------------------
@pytest.fixture
def eventos_contables(monkeypatch):
    """Captura los OrderPaidEvent enviados a Contabilidad."""
    eventos = []

    async def registrar(evento):
        eventos.append(evento)
        return {"estado": "registrado", "asiento_id": "ASI-TEST"}

    monkeypatch.setattr(contabilidad_client, "registrar_asiento_venta", registrar)
    return eventos


@pytest.fixture
def pasarela(monkeypatch):
    """Pasarela de pagos simulada: aprueba todo salvo los métodos indicados en `rechazar`."""
    estado = {"rechazar": set(), "cobros": [], "reversos": []}

    async def procesar_cobro(monto, metodo, moneda="BOB", *args, **kwargs):
        estado["cobros"].append((metodo, monto))
        if metodo in estado["rechazar"]:
            return {"estado": "rechazado", "mensaje": "Fondos insuficientes en la tarjeta"}
        return {"transaccion_id": f"TX-OK-{metodo}-{len(estado['cobros'])}", "estado": "aprobado"}

    async def reversar_cobro(transaccion_id, monto=None, *args, **kwargs):
        estado["reversos"].append(transaccion_id)
        return {"reembolso_estado": "procesado"}

    monkeypatch.setattr(pagos_client, "procesar_cobro", procesar_cobro)
    monkeypatch.setattr(pagos_client, "reversar_cobro", reversar_cobro)
    return estado


def _stock(sku: str, base: int = 10) -> None:
    asyncio.run(stock_ledger.register_base_stock(sku, base))


def _disponible(sku: str) -> int:
    return asyncio.run(stock_ledger.available_stock(sku))


def _abrir_caja(fondo: float = 200.0):
    token = create_access_token({"sub": str(uuid.uuid4()), "role": "cajero"})
    headers = {"Authorization": f"Bearer {token}"}
    sucursal_id = str(uuid.uuid4())
    resp = pos_client.post("/api/v1/pos/caja/abrir", json={
        "sucursal_id": sucursal_id, "cajero_id": str(uuid.uuid4()), "fondo_inicial": fondo,
    }, headers=headers)
    assert resp.status_code == 201
    return resp.json()["id"], sucursal_id, headers


def _venta(caja_id, sucursal_id, sku, cantidad, precio, **extra):
    return {
        "caja_id": caja_id, "sucursal_id": sucursal_id,
        "items": [{"variante_id": str(uuid.uuid4()), "sku": sku, "nombre": "Artículo de prueba",
                   "cantidad": cantidad, "precio_unitario": precio}],
        **extra,
    }


# ------------------------------------------------------------------------------
# Validación (función pura)
# ------------------------------------------------------------------------------
def test_normalizar_sin_pagos_usa_metodo_unico():
    pagos = normalizar_pagos(None, "tarjeta", Decimal("120"))
    assert len(pagos) == 1 and pagos[0].metodo == "tarjeta" and pagos[0].monto == Decimal("120.00")


def test_normalizar_exige_que_la_suma_iguale_el_total():
    legs = [PagoParcial(metodo="efectivo", monto=100), PagoParcial(metodo="qr", monto=50)]
    assert len(normalizar_pagos(legs, "efectivo", Decimal("150"))) == 2
    with pytest.raises(PagoInvalidoError, match="faltan Bs. 10.00"):
        normalizar_pagos(legs, "efectivo", Decimal("160"))
    with pytest.raises(PagoInvalidoError, match="sobran Bs. 20.00"):
        normalizar_pagos(legs, "efectivo", Decimal("130"))


def test_normalizar_rechaza_efectivo_recibido_menor_al_monto():
    legs = [PagoParcial(metodo="efectivo", monto=100, monto_recibido=80)]
    with pytest.raises(PagoInvalidoError, match="efectivo recibido"):
        normalizar_pagos(legs, "efectivo", Decimal("100"))


# ------------------------------------------------------------------------------
# POS: cobro en caja con pago dividido
# ------------------------------------------------------------------------------
def test_pos_pago_dividido_efectivo_tarjeta_qr(eventos_contables, pasarela):
    sku = f"SPLIT-{uuid.uuid4().hex[:6]}"
    _stock(sku, 10)
    caja_id, sucursal_id, headers = _abrir_caja(fondo=200)

    resp = pos_client.post("/api/v1/pos/ventas/cobrar", headers=headers, json=_venta(
        caja_id, sucursal_id, sku, cantidad=4, precio=100.0,  # total Bs. 400
        pagos=[
            {"metodo": "efectivo", "monto": 100, "monto_recibido": 150},
            {"metodo": "tarjeta", "monto": 200, "referencia": "4242"},
            {"metodo": "qr", "monto": 100},
        ],
    ))
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert float(data["total"]) == 400.00
    assert data["metodo_pago"] == "mixto"
    assert [p["metodo"] for p in data["desglose_pagos"]] == ["tarjeta", "qr", "efectivo"]  # digitales primero
    assert float(data["cambio_total"]) == 50.00
    assert "TARJETA" in data["ticket_impresion"] and "QR" in data["ticket_impresion"]

    # Inventario descontado una sola vez y caja distribuida por método.
    assert _disponible(sku) == 6
    cierre = pos_client.post(f"/api/v1/pos/caja/{caja_id}/cerrar", json={"monto_cierre_real": 300}).json()
    assert float(cierre["total_efectivo"]) == 100.00
    assert float(cierre["total_tarjeta"]) == 200.00
    assert float(cierre["total_qr"]) == 100.00
    assert float(cierre["diferencia"]) == 0.00  # fondo 200 + efectivo 100

    # OrderPaidEvent con el desglose por forma de pago.
    assert len(eventos_contables) == 1
    evento = eventos_contables[0]
    assert evento["evento"] == "OrderPaidEvent" and evento["canal"] == "pos"
    assert evento["monto_total"] == 400.0 and evento["pago_mixto"] is True
    assert evento["totales_por_metodo"] == {"tarjeta": 200.0, "qr": 100.0, "efectivo": 100.0}
    assert {p["metodo"] for p in evento["desglose_pagos"]} == {"efectivo", "tarjeta", "qr"}
    assert all(p["transaccion_id"] for p in evento["desglose_pagos"])


def test_pos_metodo_unico_sigue_funcionando(eventos_contables, pasarela):
    sku = f"UNICO-{uuid.uuid4().hex[:6]}"
    _stock(sku)
    caja_id, sucursal_id, headers = _abrir_caja()
    resp = pos_client.post("/api/v1/pos/ventas/cobrar", headers=headers,
                           json=_venta(caja_id, sucursal_id, sku, 1, 80.0, metodo_pago="tarjeta"))
    assert resp.status_code == 201
    data = resp.json()
    assert data["metodo_pago"] == "tarjeta" and len(data["desglose_pagos"]) == 1
    assert eventos_contables[0]["pago_mixto"] is False


@pytest.mark.parametrize("pagos,fragmento", [
    ([{"metodo": "efectivo", "monto": 100}, {"metodo": "qr", "monto": 50}], "incompleto"),
    ([{"metodo": "efectivo", "monto": 100}, {"metodo": "qr", "monto": 150}], "exceden"),
])
def test_pos_rechaza_pagos_que_no_suman_el_total(eventos_contables, pasarela, pagos, fragmento):
    sku = f"SUMA-{uuid.uuid4().hex[:6]}"
    _stock(sku)
    caja_id, sucursal_id, headers = _abrir_caja()
    resp = pos_client.post("/api/v1/pos/ventas/cobrar", headers=headers,
                           json=_venta(caja_id, sucursal_id, sku, 2, 100.0, pagos=pagos))  # total 200
    assert resp.status_code == 422 and fragmento in resp.json()["detail"]
    assert _disponible(sku) == 10          # no se tocó el inventario
    assert pasarela["cobros"] == []        # ni se intentó cobrar
    assert eventos_contables == []


def test_pos_metodo_no_soportado_es_422(pasarela):
    sku = f"BONO-{uuid.uuid4().hex[:6]}"
    _stock(sku)
    caja_id, sucursal_id, headers = _abrir_caja()
    resp = pos_client.post("/api/v1/pos/ventas/cobrar", headers=headers, json=_venta(
        caja_id, sucursal_id, sku, 1, 100.0, pagos=[{"metodo": "bitcoin", "monto": 100}]))
    assert resp.status_code == 422


def test_pos_tramo_rechazado_reversa_cobros_y_repone_stock(eventos_contables, pasarela):
    sku = f"RECH-{uuid.uuid4().hex[:6]}"
    _stock(sku, 10)
    caja_id, sucursal_id, headers = _abrir_caja(fondo=200)
    pasarela["rechazar"].add("tarjeta")

    resp = pos_client.post("/api/v1/pos/ventas/cobrar", headers=headers, json=_venta(
        caja_id, sucursal_id, sku, 3, 100.0,  # total 300: QR 100 aprobado, tarjeta 200 rechazada
        pagos=[{"metodo": "qr", "monto": 100}, {"metodo": "tarjeta", "monto": 200}, ],
    ))
    assert resp.status_code == 402
    detalle = resp.json()["detail"]
    assert "Fondos insuficientes" in detalle and "Se revirtieron" in detalle

    assert pasarela["reversos"] == ["TX-OK-qr-1"]     # el tramo QR ya aprobado se reversó
    assert _disponible(sku) == 10                     # el stock descontado se repuso
    assert eventos_contables == []                    # no se contabilizó una venta que no ocurrió
    cierre = pos_client.post(f"/api/v1/pos/caja/{caja_id}/cerrar", json={"monto_cierre_real": 200}).json()
    assert float(cierre["total_qr"]) == 0 and float(cierre["total_tarjeta"]) == 0 and float(cierre["diferencia"]) == 0


def test_pos_sin_stock_no_intenta_cobrar(eventos_contables, pasarela):
    sku = f"POCO-{uuid.uuid4().hex[:6]}"
    _stock(sku, 2)
    caja_id, sucursal_id, headers = _abrir_caja()
    resp = pos_client.post("/api/v1/pos/ventas/cobrar", headers=headers, json=_venta(
        caja_id, sucursal_id, sku, 5, 10.0,
        pagos=[{"metodo": "tarjeta", "monto": 30}, {"metodo": "efectivo", "monto": 20}]))
    assert resp.status_code == 409 and "Stock insuficiente" in resp.json()["detail"]
    assert pasarela["cobros"] == [] and eventos_contables == []


# ------------------------------------------------------------------------------
# Facturación POS (/facturacion/emitir): lo que usa la pantalla de caja
# ------------------------------------------------------------------------------
def _emitir(sku, pagos=None, metodo_pago="efectivo", cantidad=2, precio=250.0):
    body = {
        "modalidad": "con_factura", "tipo_documento": "NIT", "nit_ci": "1020304050",
        "razon_social": "EMPRESA DE PRUEBA S.A.", "sucursal": "Sucursal Central", "punto_venta": 1,
        "metodo_pago": metodo_pago,
        "items": [{"sku": sku, "nombre": "Teclado", "cantidad": cantidad, "precio_unitario": precio}],
        "descuento": 0,
    }
    if pagos is not None:
        body["pagos"] = pagos
    return ordenes_client.post("/api/v1/facturacion/emitir", json=body)


def test_emitir_factura_con_pago_dividido(eventos_contables, pasarela):
    sku = f"FAC-{uuid.uuid4().hex[:6]}"
    _stock(sku)
    resp = _emitir(sku, pagos=[{"metodo": "tarjeta", "monto": 300}, {"metodo": "qr", "monto": 200}])  # total 500
    assert resp.status_code == 201, resp.text
    factura = resp.json()["factura"]
    assert factura["total"] == 500.00 and factura["metodo_pago"] == "mixto"
    assert [p["metodo"] for p in factura["pagos"]] == ["tarjeta", "qr"]
    assert _disponible(sku) == 8
    assert eventos_contables[0]["totales_por_metodo"] == {"tarjeta": 300.0, "qr": 200.0}


def test_emitir_factura_rechaza_pagos_que_no_suman(eventos_contables, pasarela):
    sku = f"FACX-{uuid.uuid4().hex[:6]}"
    _stock(sku)
    resp = _emitir(sku, pagos=[{"metodo": "tarjeta", "monto": 300}, {"metodo": "qr", "monto": 100}])
    assert resp.status_code == 422 and "faltan Bs. 100.00" in resp.json()["detail"]
    assert _disponible(sku) == 10 and pasarela["cobros"] == []


def test_emitir_factura_tarjeta_rechazada_repone_stock(eventos_contables, pasarela):
    sku = f"FACR-{uuid.uuid4().hex[:6]}"
    _stock(sku)
    pasarela["rechazar"].add("tarjeta")
    resp = _emitir(sku, pagos=[{"metodo": "qr", "monto": 200}, {"metodo": "tarjeta", "monto": 300}])
    assert resp.status_code == 402 and "Fondos insuficientes" in resp.json()["detail"]
    assert _disponible(sku) == 10 and pasarela["reversos"] == ["TX-OK-qr-1"] and eventos_contables == []


def test_emitir_factura_metodo_unico_compatible(eventos_contables, pasarela):
    sku = f"FACU-{uuid.uuid4().hex[:6]}"
    _stock(sku)
    resp = _emitir(sku, metodo_pago="qr")
    assert resp.status_code == 201
    assert resp.json()["factura"]["metodo_pago"] == "qr" and len(resp.json()["factura"]["pagos"]) == 1


# ------------------------------------------------------------------------------
# Orden web con lista de transacciones de pago
# ------------------------------------------------------------------------------
def _orden_web(pagos=None, total=615.0):
    token = create_access_token({"sub": str(uuid.uuid4()), "role": "cliente"})
    body = {
        "cliente_id": "cliente-demo", "canal": "web", "tipo_despacho": "retiro_sucursal",
        "subtotal": total, "descuento": 0.0, "costo_envio": 0.0, "total": total,
        "metodo_pago": "tarjeta",
        "items": [{"variante_id": str(uuid.uuid4()), "sku": "MOUSE-SPLIT", "nombre_producto": "Mouse",
                   "cantidad": 1, "precio_unitario": total}],
    }
    if pagos is not None:
        body["pagos"] = pagos
    return ordenes_client.post("/api/v1/ordenes/", json=body, headers={"Authorization": f"Bearer {token}"})


def test_orden_web_con_pago_dividido(eventos_contables):
    resp = _orden_web(pagos=[{"metodo": "tarjeta", "monto": 400}, {"metodo": "qr", "monto": 215}])
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert len(data["pagos"]) == 2 and sum(float(p["monto"]) for p in data["pagos"]) == 615.00
    assert all(p["transaccion_id"] for p in data["pagos"])
    assert eventos_contables[0]["canal"] == "web" and eventos_contables[0]["pago_mixto"] is True
    assert eventos_contables[0]["totales_por_metodo"] == {"tarjeta": 400.0, "qr": 215.0}


def test_orden_web_rechaza_pagos_que_no_suman(eventos_contables):
    resp = _orden_web(pagos=[{"metodo": "tarjeta", "monto": 400}, {"metodo": "qr", "monto": 100}])
    assert resp.status_code == 422 and "incompleto" in resp.json()["detail"]
    assert eventos_contables == []


def test_orden_web_metodo_unico_registra_un_pago(eventos_contables):
    resp = _orden_web()
    assert resp.status_code == 201 and len(resp.json()["pagos"]) == 1
    assert eventos_contables[0]["pago_mixto"] is False

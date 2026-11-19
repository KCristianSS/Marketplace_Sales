"""
Pruebas funcionales de RF-33 — Reversión contable e inventario (actor: Sistema).

Verifica el orquestador de transacciones compensatorias (saga) y su uso en la
cancelación de órdenes: reingreso al almacén (RIO-INV-04), asiento contable de
reversión (RIO-CON-04) y reversión de cobros (RIO-PAG-03), incluyendo la
compensación cuando alguno de los sistemas externos falla.
Ejecutar con: python -m pytest backend/tests/test_reversion_contable_inventario.py
"""
import asyncio
import os
import sys
import uuid

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from fastapi.testclient import TestClient

from backend.services.ordenes.app.main import app as ordenes_app
from backend.shared import stock_ledger
from backend.shared.erp_clients.contabilidad import contabilidad_client
from backend.shared.erp_clients.pagos import pagos_client
from backend.shared.security import get_current_user
from backend.shared.saga import SagaOrchestrator

client = TestClient(ordenes_app)


@pytest.fixture(autouse=True)
def usuario_administrador_de_prueba():
    previous = ordenes_app.dependency_overrides.get(get_current_user)
    ordenes_app.dependency_overrides[get_current_user] = lambda: {"user_id": "admin-pruebas", "role": "administrador"}
    yield
    if previous is None:
        ordenes_app.dependency_overrides.pop(get_current_user, None)
    else:
        ordenes_app.dependency_overrides[get_current_user] = previous


# ------------------------------------------------------------------------------
# Orquestador (unitario, sin sistemas externos)
# ------------------------------------------------------------------------------
def _ejecutar(saga):
    return asyncio.run(saga.ejecutar())


def _paso_ok(bitacora, nombre, resultado=None):
    async def accion():
        bitacora.append(f"do:{nombre}")
        return resultado or {"estado": "ok", "id": nombre}

    async def compensacion(res):
        bitacora.append(f"undo:{nombre}")

    return accion, compensacion


def test_saga_exitosa_ejecuta_todos_los_pasos_sin_compensar():
    bitacora = []
    saga = SagaOrchestrator("prueba")
    for nombre in ("a", "b", "c"):
        saga.paso(nombre, *_paso_ok(bitacora, nombre))
    resultado = _ejecutar(saga)
    assert resultado.exitosa and resultado.compensados == [] and resultado.paso_fallido is None
    assert bitacora == ["do:a", "do:b", "do:c"]


def test_saga_compensa_en_orden_inverso_solo_los_pasos_completados():
    bitacora = []
    saga = SagaOrchestrator("prueba")
    saga.paso("a", *_paso_ok(bitacora, "a"))
    saga.paso("b", *_paso_ok(bitacora, "b"))

    async def falla():
        bitacora.append("do:c")
        raise ConnectionError("Contabilidad no responde")

    saga.paso("c", falla, lambda r: pytest.fail("no debe compensarse el paso que falló"))
    saga.paso("d", *_paso_ok(bitacora, "d"))

    resultado = _ejecutar(saga)
    assert not resultado.exitosa and resultado.paso_fallido == "c"
    assert "Contabilidad no responde" in resultado.error
    assert bitacora == ["do:a", "do:b", "do:c", "undo:b", "undo:a"]  # d nunca se ejecuta
    assert resultado.compensados == ["b", "a"] and not resultado.requiere_intervencion_manual


def test_saga_trata_un_rechazo_de_negocio_como_fallo():
    bitacora = []
    saga = SagaOrchestrator("prueba")
    saga.paso("a", *_paso_ok(bitacora, "a"))

    async def rechazado():
        return {"estado": "RECHAZADA", "mensaje": "Periodo contable cerrado"}

    saga.paso("b", rechazado)
    resultado = _ejecutar(saga)
    assert not resultado.exitosa and resultado.paso_fallido == "b"
    assert "Periodo contable cerrado" in resultado.error and bitacora == ["do:a", "undo:a"]


def test_saga_continua_compensando_y_alerta_si_una_compensacion_falla():
    bitacora = []
    saga = SagaOrchestrator("prueba")
    saga.paso("a", *_paso_ok(bitacora, "a"))

    async def accion_b():
        return {"estado": "ok"}

    async def compensacion_b(_):
        raise TimeoutError("sin respuesta")

    saga.paso("b", accion_b, compensacion_b)

    async def falla():
        raise RuntimeError("boom")

    saga.paso("c", falla)
    resultado = _ejecutar(saga)
    assert resultado.compensados == ["a"] and resultado.compensaciones_fallidas == ["b"]
    assert resultado.requiere_intervencion_manual and resultado.a_dict()["requiere_intervencion_manual"] is True


# ------------------------------------------------------------------------------
# Cancelación de órdenes con reversión (integración sobre el servicio de órdenes)
# ------------------------------------------------------------------------------
@pytest.fixture
def erp(monkeypatch):
    """Registra las llamadas a Contabilidad y Pagos; permite forzar fallos por prueba."""
    estado = {
        "reversiones": [], "asientos_venta": [], "reversos_pago": [], "cobros": [],
        "falla_reversion_contable": None, "falla_reversion_pago": False,
    }

    async def registrar_reversion(datos):
        estado["reversiones"].append(datos)
        falla = estado["falla_reversion_contable"]
        if falla == "excepcion":
            raise ConnectionError("Contabilidad fuera de servicio")
        if falla == "rechazo":
            return {"estado": "RECHAZADA", "mensaje": "Periodo contable cerrado"}
        return {"estado": "revertido", "asiento_reversion_id": "ASI-REV-1"}

    async def registrar_asiento_venta(evento):
        estado["asientos_venta"].append(evento)
        return {"estado": "registrado"}

    async def reversar_cobro(transaccion_id, monto=None, *a, **k):
        estado["reversos_pago"].append(transaccion_id)
        if estado["falla_reversion_pago"]:
            return {"estado": "ERROR", "mensaje": "La pasarela rechazó el reembolso"}
        return {"reembolso_estado": "procesado"}

    async def procesar_cobro(monto, metodo, moneda="BOB", *a, **k):
        estado["cobros"].append((metodo, monto))
        return {"transaccion_id": f"TX-RECOBRO-{len(estado['cobros'])}", "estado": "aprobado"}

    monkeypatch.setattr(contabilidad_client, "registrar_reversion", registrar_reversion)
    monkeypatch.setattr(contabilidad_client, "registrar_asiento_venta", registrar_asiento_venta)
    monkeypatch.setattr(pagos_client, "reversar_cobro", reversar_cobro)
    monkeypatch.setattr(pagos_client, "procesar_cobro", procesar_cobro)
    return estado


def _disponible(sku):
    return asyncio.run(stock_ledger.available_stock(sku))


def _crear_orden_vendida(sku, cantidad=3, pagos=None, cliente_id="cliente-demo"):
    """Deja stock base 10, vende `cantidad` (descuento) y crea la orden asociada."""
    asyncio.run(stock_ledger.register_base_stock(sku, 10))
    ok, _ = asyncio.run(stock_ledger.consume({sku: cantidad}))
    assert ok and _disponible(sku) == 10 - cantidad

    total = 100.0 * cantidad
    body = {
        "cliente_id": cliente_id, "canal": "web", "tipo_despacho": "retiro_sucursal",
        "subtotal": total, "total": total, "metodo_pago": "tarjeta",
        "items": [{"variante_id": str(uuid.uuid4()), "sku": sku, "nombre_producto": "Producto",
                   "cantidad": cantidad, "precio_unitario": 100.0}],
    }
    if pagos:
        body["pagos"] = pagos
    resp = client.post("/api/v1/ordenes/", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_cancelacion_exitosa_revierte_stock_contabilidad_y_pago(erp):
    sku = f"REV-{uuid.uuid4().hex[:6]}"
    orden = _crear_orden_vendida(sku, 3)

    resp = client.post(f"/api/v1/ordenes/{orden['id']}/cancelar", params={"motivo": "Cliente desistió"})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["estado"] == "cancelada"
    assert data["motivo_cancelacion"] == "Cliente desistió"
    assert data["reversion"]["exitosa"] is True and data["reversion"]["compensados"] == []

    assert _disponible(sku) == 10                                   # reingreso al almacén
    assert len(erp["reversiones"]) == 1
    asiento = erp["reversiones"][0]
    assert asiento["monto_revertido"] == 300.0 and asiento["motivo"] == "Cliente desistió"
    assert asiento["desglose_pagos"][0]["metodo"] == "tarjeta"      # asiento por forma de pago
    assert len(erp["reversos_pago"]) == 1                           # cobro reversado


def test_cancelacion_con_pago_dividido_revierte_cada_tramo_digital(erp):
    sku = f"REVS-{uuid.uuid4().hex[:6]}"
    orden = _crear_orden_vendida(sku, 2, pagos=[
        {"metodo": "tarjeta", "monto": 100}, {"metodo": "efectivo", "monto": 50}, {"metodo": "qr", "monto": 50},
    ])
    tx_digitales = {p["transaccion_id"] for p in orden["pagos"] if p["metodo"] != "efectivo"}

    resp = client.post(f"/api/v1/ordenes/{orden['id']}/cancelar", params={"motivo": "Error de precio"})
    assert resp.status_code == 200
    assert set(erp["reversos_pago"]) == tx_digitales and len(erp["reversos_pago"]) == 2  # el efectivo no va a la pasarela
    assert len(erp["reversiones"][0]["desglose_pagos"]) == 3


@pytest.mark.parametrize("modo_falla", ["excepcion", "rechazo"])
def test_fallo_contable_compensa_el_reingreso_y_conserva_el_estado(erp, modo_falla):
    sku = f"REVF-{uuid.uuid4().hex[:6]}"
    orden = _crear_orden_vendida(sku, 3)
    erp["falla_reversion_contable"] = modo_falla

    resp = client.post(f"/api/v1/ordenes/{orden['id']}/cancelar", params={"motivo": "Prueba de fallo"})
    assert resp.status_code == 502
    detalle = resp.json()["detail"]
    assert "NO fue cancelada" in detalle["mensaje"]
    assert detalle["orden_estado"] == orden["estado"]
    assert detalle["reversion"]["paso_fallido"] == "reversion_contable"
    assert detalle["reversion"]["compensados"] == ["reingreso_stock"]
    assert detalle["reversion"]["requiere_intervencion_manual"] is False

    # La compensación volvió a descontar el stock reingresado: queda como antes de intentar cancelar.
    assert _disponible(sku) == 7
    assert erp["reversos_pago"] == []                  # el paso de pago nunca se ejecutó


def test_fallo_de_pago_compensa_contabilidad_e_inventario_en_orden_inverso(erp):
    sku = f"REVP-{uuid.uuid4().hex[:6]}"
    orden = _crear_orden_vendida(sku, 3)
    erp["falla_reversion_pago"] = True
    ventas_antes = len(erp["asientos_venta"])

    resp = client.post(f"/api/v1/ordenes/{orden['id']}/cancelar", params={"motivo": "Pasarela caída"})
    assert resp.status_code == 502
    reversion = resp.json()["detail"]["reversion"]
    assert reversion["paso_fallido"].startswith("reversion_pago_")
    assert reversion["compensados"] == ["reversion_contable", "reingreso_stock"]  # orden inverso

    assert _disponible(sku) == 7                                           # stock vuelve a quedar descontado
    assert len(erp["asientos_venta"]) == ventas_antes + 1                  # se re-registró el asiento de venta original

    # La orden sigue sin cancelar y se puede reintentar cuando el sistema se recupere.
    erp["falla_reversion_pago"] = False
    reintento = client.post(f"/api/v1/ordenes/{orden['id']}/cancelar", params={"motivo": "Reintento"})
    assert reintento.status_code == 200 and reintento.json()["estado"] == "cancelada"
    assert _disponible(sku) == 10


def test_cancelar_dos_veces_no_duplica_el_reingreso(erp):
    sku = f"REV2-{uuid.uuid4().hex[:6]}"
    orden = _crear_orden_vendida(sku, 3)
    assert client.post(f"/api/v1/ordenes/{orden['id']}/cancelar", params={"motivo": "uno"}).status_code == 200
    segundo = client.post(f"/api/v1/ordenes/{orden['id']}/cancelar", params={"motivo": "dos"})
    assert segundo.status_code == 409 and "ya fue cancelada" in segundo.json()["detail"]
    assert len(erp["reversiones"]) == 1 and _disponible(sku) == 10


def test_no_se_puede_cancelar_una_orden_ya_despachada(erp):
    sku = f"REV3-{uuid.uuid4().hex[:6]}"
    orden = _crear_orden_vendida(sku, 1)
    from backend.services.ordenes.app.routers import _ORDENES_DB
    _ORDENES_DB[orden["id"]].estado = "despachada"
    resp = client.post(f"/api/v1/ordenes/{orden['id']}/cancelar", params={"motivo": "tarde"})
    assert resp.status_code == 400 and erp["reversiones"] == []


def test_cliente_solo_lista_y_cancela_sus_pedidos(erp):
    cliente_id = str(uuid.uuid4())
    sku = f"REVA-{uuid.uuid4().hex[:6]}"
    orden = _crear_orden_vendida(sku, 1, cliente_id=cliente_id)
    otro_cliente_id = str(uuid.uuid4())
    ordenes_app.dependency_overrides[get_current_user] = lambda: {"user_id": otro_cliente_id, "role": "cliente"}

    listado_ajeno = client.get(f"/api/v1/ordenes/cliente/{cliente_id}")
    cancelacion_ajena = client.post(f"/api/v1/ordenes/{orden['id']}/cancelar", params={"motivo": "No corresponde"})

    assert listado_ajeno.status_code == 403
    assert cancelacion_ajena.status_code == 403
    assert erp["reversiones"] == []

    ordenes_app.dependency_overrides[get_current_user] = lambda: {"user_id": cliente_id, "role": "cliente"}
    listado_propio = client.get(f"/api/v1/ordenes/cliente/{cliente_id}")
    assert listado_propio.status_code == 200
    assert [item["id"] for item in listado_propio.json()] == [orden["id"]]

    ordenes_app.dependency_overrides[get_current_user] = lambda: {"user_id": "admin-pruebas", "role": "administrador"}


def test_cancelacion_libera_reserva_confirmada(erp, monkeypatch):
    sku = f"REVL-{uuid.uuid4().hex[:6]}"
    orden = _crear_orden_vendida(sku, 1)
    from backend.services.ordenes.app import routers as ordenes_routers
    calls = []

    async def liberar(reserva_id):
        calls.append(reserva_id)
        return True

    monkeypatch.setattr(ordenes_routers, "liberar_reserva_stock", liberar)
    ordenes_routers._ORDENES_DB[orden["id"]].reserva_id = "RESERVA-TEST"
    response = client.post(f"/api/v1/ordenes/{orden['id']}/cancelar", params={"motivo": "Pedido duplicado"})

    assert response.status_code == 200, response.text
    assert calls == ["RESERVA-TEST"]


def test_cancelacion_requiere_un_motivo_descriptivo(erp):
    orden = _crear_orden_vendida(f"REVM-{uuid.uuid4().hex[:6]}", 1)
    response = client.post(f"/api/v1/ordenes/{orden['id']}/cancelar", params={"motivo": "no"})
    assert response.status_code == 422
    assert erp["reversiones"] == []

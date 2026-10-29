"""
Pruebas automatizadas de RF-17 — Promociones y Cupones.

Cubre el motor de validación (vigencia, monto mínimo, límite de canjes, tipos de
descuento), la API administrativa protegida por rol y la integración con el carrito.
Ejecutar con: python -m pytest backend/tests/test_cupones.py
"""
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from fastapi.testclient import TestClient

from backend.services.carrito.app import cupones_store
from backend.services.carrito.app.cupones_engine import evaluar_cupon
from backend.services.carrito.app.main import app as carrito_app
from backend.shared.security import create_access_token

client = TestClient(carrito_app)
AHORA = datetime.now(timezone.utc)


@pytest.fixture(autouse=True)
def cupones_semilla():
    cupones_store.reiniciar_memoria()
    yield
    cupones_store.reiniciar_memoria()


def _headers(rol: str) -> dict:
    token = create_access_token({"sub": str(uuid.uuid4()), "role": rol})
    return {"Authorization": f"Bearer {token}"}


def _cupon(**extra) -> dict:
    base = dict(
        codigo="PRUEBA", tipo_descuento="porcentaje", valor_descuento=10, monto_minimo=0,
        usos_maximos=10, usos_actuales=0, fecha_inicio=AHORA - timedelta(days=1), fecha_fin=None, activo=True,
    )
    base.update(extra)
    return base


# ------------------------------------------------------------------------------
# Motor de validación (función pura)
# ------------------------------------------------------------------------------
def test_motor_descuento_porcentual():
    r = evaluar_cupon(_cupon(valor_descuento=15), Decimal("200"), AHORA)
    assert r.valido and r.descuento == Decimal("30.00")


def test_motor_descuento_monto_fijo_nunca_supera_el_subtotal():
    r = evaluar_cupon(_cupon(tipo_descuento="monto_fijo", valor_descuento=50), Decimal("30"), AHORA)
    assert r.valido and r.descuento == Decimal("30.00")


def test_motor_rechaza_cupon_inexistente():
    r = evaluar_cupon(None, Decimal("100"), AHORA, codigo_solicitado="NOEXISTE")
    assert not r.valido and r.motivo == "NO_EXISTE"


def test_motor_rechaza_cupon_inactivo():
    r = evaluar_cupon(_cupon(activo=False), Decimal("100"), AHORA)
    assert not r.valido and r.motivo == "INACTIVO"


def test_motor_rechaza_cupon_vencido_y_no_vigente():
    vencido = evaluar_cupon(_cupon(fecha_fin=AHORA - timedelta(hours=1)), Decimal("100"), AHORA)
    assert not vencido.valido and vencido.motivo == "VENCIDO"
    futuro = evaluar_cupon(_cupon(fecha_inicio=AHORA + timedelta(days=2)), Decimal("100"), AHORA)
    assert not futuro.valido and futuro.motivo == "AUN_NO_VIGENTE"


def test_motor_exige_monto_minimo_e_informa_cuanto_falta():
    r = evaluar_cupon(_cupon(monto_minimo=100), Decimal("60"), AHORA)
    assert not r.valido and r.motivo == "MONTO_MINIMO"
    assert "40.00" in r.mensaje
    assert evaluar_cupon(_cupon(monto_minimo=100), Decimal("100"), AHORA).valido


def test_motor_respeta_limite_de_canjes_y_sin_limite():
    agotado = evaluar_cupon(_cupon(usos_maximos=5, usos_actuales=5), Decimal("100"), AHORA)
    assert not agotado.valido and agotado.motivo == "LIMITE_CANJES"
    assert evaluar_cupon(_cupon(usos_maximos=None, usos_actuales=9999), Decimal("100"), AHORA).valido


# ------------------------------------------------------------------------------
# Validación y canje para el cliente (feedback inmediato de ahorro)
# ------------------------------------------------------------------------------
def test_validar_cupon_devuelve_ahorro_y_total():
    r = client.post("/api/v1/carrito/validar-cupon", json={"codigo": "maxi10", "subtotal": 200})
    assert r.status_code == 200
    data = r.json()
    assert data["valido"] is True
    assert float(data["descuento"]) == 20.00
    assert float(data["total_con_descuento"]) == 180.00
    assert "Ahorras" in data["mensaje"]


def test_validar_cupon_bajo_monto_minimo():
    data = client.post("/api/v1/carrito/validar-cupon", json={"codigo": "BIENVENIDO", "subtotal": 50}).json()
    assert data["valido"] is False and data["motivo"] == "MONTO_MINIMO"
    ok = client.post("/api/v1/carrito/validar-cupon", json={"codigo": "BIENVENIDO", "subtotal": 100}).json()
    assert ok["valido"] is True and float(ok["descuento"]) == 20.00


def test_canje_respeta_limite_de_usos():
    h = _headers("administrador")
    assert client.post("/api/v1/carrito/cupones", headers=h, json={
        "codigo": "DOSUSOS", "tipo_descuento": "monto_fijo", "valor_descuento": 5, "usos_maximos": 2,
    }).status_code == 201

    body = {"codigo": "DOSUSOS", "subtotal": 100}
    assert client.post("/api/v1/carrito/canjear-cupon", json=body).status_code == 200
    assert client.post("/api/v1/carrito/canjear-cupon", json=body).status_code == 200
    tercero = client.post("/api/v1/carrito/canjear-cupon", json=body)
    assert tercero.status_code == 409
    assert "límite de canjes" in tercero.json()["detail"]

    validacion = client.post("/api/v1/carrito/validar-cupon", json=body).json()
    assert validacion["valido"] is False and validacion["motivo"] == "LIMITE_CANJES"


def test_validar_no_consume_el_cupon():
    for _ in range(3):
        client.post("/api/v1/carrito/validar-cupon", json={"codigo": "MAXI10", "subtotal": 100})
    cupon = client.get("/api/v1/carrito/cupones/MAXI10", headers=_headers("administrador")).json()
    assert cupon["usos_actuales"] == 0


# ------------------------------------------------------------------------------
# Panel administrativo: gestión y activación de promociones
# ------------------------------------------------------------------------------
def test_admin_requiere_autenticacion_y_rol():
    assert client.get("/api/v1/carrito/cupones").status_code in (401, 403)
    assert client.get("/api/v1/carrito/cupones", headers=_headers("cliente")).status_code == 403
    assert client.post("/api/v1/carrito/cupones", headers=_headers("cajero"), json={
        "codigo": "NOPE", "tipo_descuento": "porcentaje", "valor_descuento": 10,
    }).status_code == 403
    assert client.get("/api/v1/carrito/cupones", headers=_headers("gerente_comercial")).status_code == 200


def test_admin_crud_y_activacion():
    h = _headers("administrador")
    creado = client.post("/api/v1/carrito/cupones", headers=h, json={
        "codigo": "navidad25", "descripcion": "Promo navideña", "tipo_descuento": "porcentaje",
        "valor_descuento": 25, "monto_minimo": 300, "usos_maximos": 50,
    })
    assert creado.status_code == 201
    assert creado.json()["codigo"] == "NAVIDAD25" and creado.json()["estado_vigencia"] == "vigente"

    assert client.post("/api/v1/carrito/cupones", headers=h, json={
        "codigo": "NAVIDAD25", "tipo_descuento": "porcentaje", "valor_descuento": 5,
    }).status_code == 409

    desactivado = client.patch("/api/v1/carrito/cupones/NAVIDAD25", headers=h, json={"activo": False})
    assert desactivado.status_code == 200 and desactivado.json()["estado_vigencia"] == "inactivo"
    rechazo = client.post("/api/v1/carrito/validar-cupon", json={"codigo": "NAVIDAD25", "subtotal": 500}).json()
    assert rechazo["valido"] is False and rechazo["motivo"] == "INACTIVO"

    client.patch("/api/v1/carrito/cupones/NAVIDAD25", headers=h, json={"activo": True})
    assert client.post("/api/v1/carrito/validar-cupon", json={"codigo": "NAVIDAD25", "subtotal": 500}).json()["valido"]

    assert client.delete("/api/v1/carrito/cupones/NAVIDAD25", headers=h).status_code == 204
    assert client.get("/api/v1/carrito/cupones/NAVIDAD25", headers=h).status_code == 404


def test_admin_valida_datos_del_cupon():
    h = _headers("administrador")
    base = {"codigo": "MALO", "tipo_descuento": "porcentaje", "valor_descuento": 150}
    assert client.post("/api/v1/carrito/cupones", headers=h, json=base).status_code == 422
    assert client.post("/api/v1/carrito/cupones", headers=h, json={**base, "valor_descuento": 10, "tipo_descuento": "regalo"}).status_code == 422
    fechas = {**base, "valor_descuento": 10, "fecha_inicio": "2026-12-10T00:00:00Z", "fecha_fin": "2026-12-01T00:00:00Z"}
    assert client.post("/api/v1/carrito/cupones", headers=h, json=fechas).status_code == 422


def test_listado_marca_estado_de_vigencia():
    h = _headers("administrador")
    client.post("/api/v1/carrito/cupones", headers=h, json={
        "codigo": "CADUCADO", "tipo_descuento": "monto_fijo", "valor_descuento": 5,
        "fecha_inicio": (AHORA - timedelta(days=10)).isoformat(), "fecha_fin": (AHORA - timedelta(days=1)).isoformat(),
    })
    estados = {c["codigo"]: c["estado_vigencia"] for c in client.get("/api/v1/carrito/cupones", headers=h).json()}
    assert estados["CADUCADO"] == "vencido" and estados["MAXI10"] == "vigente"


# ------------------------------------------------------------------------------
# Integración con el carrito persistente
# ------------------------------------------------------------------------------
def _carrito_con_item(precio: float, cantidad: int = 1) -> str:
    cid = f"test-{uuid.uuid4()}"
    r = client.post(f"/api/v1/carrito/{cid}/items", json={
        "variante_id": str(uuid.uuid4()), "sku": "SKU-CUPON", "nombre": "Producto", "cantidad": cantidad, "precio_unitario": precio,
    })
    assert r.status_code == 200
    return cid


def test_carrito_aplica_y_quita_cupon():
    cid = _carrito_con_item(120)
    r = client.post(f"/api/v1/carrito/{cid}/cupon", json={"codigo": "bienvenido"})
    assert r.status_code == 200
    data = r.json()
    assert data["cupon_codigo"] == "BIENVENIDO" and float(data["descuento_cupon"]) == 20.00 and float(data["total"]) == 100.00

    quitado = client.delete(f"/api/v1/carrito/{cid}/cupon").json()
    assert quitado["cupon_codigo"] is None and float(quitado["descuento_cupon"]) == 0 and float(quitado["total"]) == 120.00


def test_carrito_rechaza_cupon_con_mensaje_claro():
    cid = _carrito_con_item(40)
    r = client.post(f"/api/v1/carrito/{cid}/cupon", json={"codigo": "BIENVENIDO"})
    assert r.status_code == 400 and "Compra mínima" in r.json()["detail"]
    assert client.post(f"/api/v1/carrito/{cid}/cupon", json={"codigo": "FANTASMA"}).status_code == 400


def test_carrito_recalcula_descuento_si_deja_de_cumplir_el_minimo():
    cid = _carrito_con_item(60, cantidad=2)  # subtotal 120 >= 100
    variante = client.get(f"/api/v1/carrito/{cid}").json()["items"][0]["variante_id"]
    assert float(client.post(f"/api/v1/carrito/{cid}/cupon", json={"codigo": "BIENVENIDO"}).json()["descuento_cupon"]) == 20.00

    # Al bajar a 1 unidad (subtotal 60 < mínimo 100) el descuento deja de aplicarse.
    r = client.put(f"/api/v1/carrito/{cid}/items/{variante}", json={"cantidad": 1}).json()
    assert float(r["subtotal"]) == 60.00 and float(r["descuento_cupon"]) == 0.00 and float(r["total"]) == 60.00


def test_ruta_cupones_no_se_confunde_con_identificador_de_carrito():
    # /cupones debe resolverse al router de promociones, no a GET /{identificador}.
    r = client.get("/api/v1/carrito/cupones", headers=_headers("administrador"))
    assert r.status_code == 200 and isinstance(r.json(), list)

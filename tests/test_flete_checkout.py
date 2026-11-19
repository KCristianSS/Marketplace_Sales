import asyncio
import time
import uuid
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
import httpx
from fastapi import HTTPException
from fastapi.testclient import TestClient
from jose import jwt

from backend.shared import redis_client, flete
from backend.shared.config import settings
from backend.services.ordenes.app import routers, routers_pagos
from backend.services.ordenes.app.main import app


@pytest.fixture
def checkout(monkeypatch):
    monkeypatch.setattr(redis_client, "_redis_unavailable", True)
    monkeypatch.setattr(redis_client, "_in_memory_store", {})
    monkeypatch.setattr(routers_pagos, "_get_supabase_safe", lambda: None)
    monkeypatch.setattr(routers, "_get_supabase_safe", lambda: None)
    monkeypatch.setattr(routers_pagos, "_transacciones_cache", {})
    monkeypatch.setattr(routers, "_ORDENES_DB", {})

    async def erp_stub(*args, **kwargs):
        return {"status": "OK", "guia_despacho": "TRK-TEST"}

    for client, method in [(routers.pagos_client, "procesar_cobro"),
                           (routers.pagos_client, "emitir_factura"),
                           (routers.inventarios_client, "descuento_definitivo"),
                           (routers.entregas_client, "solicitar_despacho")]:
        monkeypatch.setattr(client, method, erp_stub)
    cliente_id = "cliente-flete"
    reserva_id = "RES-FLETE"
    item = {"variante_id": str(uuid.uuid4()), "sku": "TEST", "nombre": "Producto",
            "cantidad": 4, "precio_unitario": 100}
    asyncio.run(redis_client.crear_reserva_stock(reserva_id, cliente_id, [item]))
    return TestClient(app), cliente_id, reserva_id, item


def cotizar(checkout, **kwargs):
    client, _, reserva_id, _ = checkout
    return client.post("/api/v1/ordenes/flete/calcular", json={
        "ciudad": "La Paz", "zona": "Centro", "direccion": "Av. Arce 123",
        "reserva_id": reserva_id, **kwargs,
    })


@pytest.mark.parametrize("ciudad,zona,costo", [
    ("La Paz", "Centro", "15.00"), ("El Alto", "Rio Seco", "28.00"),
    ("Oruro", "Centro", "30.00"), ("Sucre", "Rumi Rumi", "35.00"),
])
def test_tarifas_por_destino(checkout, ciudad, zona, costo):
    response = checkout[0].post("/api/v1/ordenes/flete/calcular", json={"ciudad": ciudad, "zona": zona})
    assert response.status_code == 200
    assert Decimal(response.json()["costo_flete"]) == Decimal(costo)


def test_reserva_determina_subtotal_peso_y_total(checkout):
    response = cotizar(checkout, subtotal_productos=99999, peso_estimado_kg=1, tipo_envio="express_mismo_dia")
    assert response.status_code == 200
    data = response.json()
    assert Decimal(data["costo_flete"]) == 35  # 15 zona + 5 sobrepeso + 15 express
    assert Decimal(data["total"]) == 435
    claims = flete.validar_cotizacion(data["cotizacion_flete"], checkout[2], checkout[1])
    assert claims["direccion"] == "Av. Arce 123"
    assert claims["subtotal"] == "400.00"


@pytest.mark.parametrize("datos", [
    {"ciudad": "Desconocida"}, {"zona": "Inexistente"}, {"tipo_envio": "otro"},
    {"peso_estimado_kg": -1}, {"subtotal_productos": -1}, {"direccion": ""},
])
def test_rechaza_destino_y_datos_invalidos(checkout, datos):
    assert cotizar(checkout, **datos).status_code == 422


def test_cupon_validado_en_servidor_y_umbral(monkeypatch, checkout):
    async def validar(self, url, **kwargs):
        return httpx.Response(200, json={"valido": True, "descuento": 40},
                              request=httpx.Request("POST", url))

    monkeypatch.setattr(flete.httpx.AsyncClient, "post", validar)
    data = cotizar(checkout, cupon="MAXI10", puntos_canjeados=10).json()
    assert Decimal(data["total"]) == Decimal("375.00")  # 400 - 40 - 5 + 20
    assert data["flete_gratis"] is False
    assert cotizar(checkout, subtotal_productos=500).json()["flete_gratis"] is False
    for subtotal, gratis in [(499.99, False), (500, True), (500.01, True)]:
        response = checkout[0].post("/api/v1/ordenes/flete/calcular", json={
            "ciudad": "La Paz", "zona": "Centro", "subtotal_productos": subtotal,
        })
        assert response.json()["flete_gratis"] is gratis


def test_pago_rechaza_total_token_vencido_y_reserva_ajena(checkout):
    client, cliente_id, reserva_id, _ = checkout
    token = cotizar(checkout).json()["cotizacion_flete"]
    pago = dict(monto=420, metodo_pago="qr", cliente_id=cliente_id, reserva_id=reserva_id, cotizacion_flete=token)
    assert client.post("/api/v1/pagos/iniciar", json={**pago, "monto": 400}).status_code == 409
    assert client.post("/api/v1/pagos/iniciar", json={**pago, "cliente_id": "otro"}).status_code == 409
    assert client.post("/api/v1/pagos/iniciar", json={**pago, "cotizacion_flete": "alterado"}).status_code == 409
    claims = flete.validar_cotizacion(token, reserva_id, cliente_id)
    claims["exp"] = time.time() - 10
    vencido = jwt.encode(claims, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    assert client.post("/api/v1/pagos/iniciar", json={**pago, "cotizacion_flete": vencido}).status_code == 409
    assert not routers_pagos._transacciones_cache


def test_pago_y_orden_conservan_cotizacion(checkout, monkeypatch):
    client, cliente_id, reserva_id, item = checkout
    # Expira después de iniciar el pago, sin invalidar el importe ya confirmado.
    claims = flete.validar_cotizacion(cotizar(checkout).json()["cotizacion_flete"], reserva_id, cliente_id)
    claims["exp"] = time.time() + 30
    token = jwt.encode(claims, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    pago = client.post("/api/v1/pagos/iniciar", json=dict(
        monto=420, metodo_pago="tarjeta", cliente_id=cliente_id, reserva_id=reserva_id, cotizacion_flete=token))
    assert pago.status_code == 201, pago.text
    class RelojAdelantado(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.now(tz) + timedelta(seconds=60)

        @classmethod
        def utcnow(cls):
            # python-jose 3.3 usa utcnow; versiones recientes usan now(UTC).
            return datetime.utcnow() + timedelta(seconds=60)

    monkeypatch.setattr(jwt, "datetime", RelojAdelantado)
    with pytest.raises(HTTPException) as exc:
        flete.validar_cotizacion(token, reserva_id, cliente_id)
    assert exc.value.status_code == 409
    orden = dict(cliente_id=cliente_id, reserva_id=reserva_id, subtotal=400, descuento=0,
                 costo_envio=20, total=420, cotizacion_flete=token,
                 transaccion_id=pago.json()["transaccion_id"],
                 items=[{**item, "nombre_producto": item["nombre"]}])
    assert client.post("/api/v1/ordenes/", json={**orden, "costo_envio": 0}).status_code == 409
    response = client.post("/api/v1/ordenes/", json=orden)
    assert response.status_code == 201, response.text
    data = response.json()
    assert Decimal(data["total"]) == Decimal(str(pago.json()["monto"]))
    assert data["entrega"]["direccion"] == "Av. Arce 123"
    assert data["entrega"]["tiempo_estimado"]
    loaded = client.get(f'/api/v1/ordenes/{data["id"]}')
    assert loaded.json()["entrega"] == data["entrega"]

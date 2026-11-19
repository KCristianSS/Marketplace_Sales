"""Recompra autenticada con catálogo/stock actuales y sin efectos de compra."""
from datetime import datetime
from decimal import Decimal
from uuid import uuid4
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.services.ordenes.app.main import app
from backend.services.ordenes.app import routers, recompra
from backend.services.ordenes.app.schemas import OrdenResponse, ItemOrdenResponse
from backend.shared.security import create_access_token


@pytest.fixture
def escenario(monkeypatch):
    cliente_id, orden_id, producto_id, variante_id = (str(uuid4()) for _ in range(4))
    item = ItemOrdenResponse(id=uuid4(), variante_id=variante_id, sku="HABITUAL", nombre_producto="Habitual",
                             cantidad=3, precio_unitario=Decimal("10"), total_linea=Decimal("30"))
    orden = OrdenResponse(id=orden_id, cliente_id=cliente_id, codigo_orden="ORD-RECOMPRA", canal="web",
                          tipo_despacho="domicilio", subtotal=30, total=30, estado="entregada",
                          created_at=datetime.utcnow(), items=[item])
    monkeypatch.setattr(routers, "_ORDENES_DB", {orden_id: orden})
    monkeypatch.setattr(routers, "_get_supabase_safe", lambda: None)
    producto = {"id": producto_id, "sku": "HABITUAL", "nombre": "Nombre actual", "estado": "publicado", "variantes": [
        {"id": variante_id, "sku": "HABITUAL-BASE", "precio": "15.00"},
    ]}
    tarifa = {"precio": "12.50", "lista_precio_id": "PROMO", "moneda": "BOB"}
    catalogo = {"productos": [producto], "tarifa": tarifa, "fallar": False}
    peticiones = []

    def responder(request):
        peticiones.append(request)
        if catalogo["fallar"]:
            return httpx.Response(503)
        if request.url.path.endswith("/productos"):
            return httpx.Response(200, json=catalogo["productos"])
        assert request.url.params["canal"] == "web"
        return httpx.Response(200, json={variante_id: catalogo["tarifa"]})

    cliente_http = httpx.AsyncClient
    monkeypatch.setattr(recompra.httpx, "AsyncClient", lambda **kwargs: cliente_http(transport=httpx.MockTransport(responder), **kwargs))
    stock = AsyncMock(return_value={"stock_disponible": 2})
    monkeypatch.setattr(recompra.inventarios_client, "consultar_disponibilidad", stock)
    token = create_access_token({"sub": cliente_id, "role": "cliente"})
    return {"client": TestClient(app), "orden": orden, "producto": producto, "catalogo": catalogo,
            "headers": {"Authorization": f"Bearer {token}"}, "stock": stock, "peticiones": peticiones}


def repetir(e, headers=None):
    return e["client"].post(f"/api/v1/ordenes/{e['orden'].id}/repetir", headers=e["headers"] if headers is None else headers)


def test_recompra_precios_vigentes_y_variante_original(escenario):
    e = escenario
    respuesta = repetir(e)
    assert respuesta.status_code == 200, respuesta.text
    data = respuesta.json()
    assert data["items"][0]["precio_unitario"] == "12.50"
    assert data["items"][0]["cantidad"] == 3  # La fusión limita según el carrito actual.
    assert data["items"][0]["stock_disponible"] == 2
    assert data["items"][0]["variante_id"] == str(e["orden"].items[0].variante_id)
    assert data["items"][0]["nombre"] == "Nombre actual"
    assert any("precio actual" in aviso for aviso in data["avisos"])
    e["stock"].assert_awaited_once_with("HABITUAL")
    assert e["peticiones"][0].url.params["estado"] == "publicado"


def test_recompra_sin_lista_usa_precio_de_variante(escenario):
    escenario["catalogo"]["tarifa"] = {"lista_precio_id": None, "precio": "15.00", "moneda": "BOB"}
    assert repetir(escenario).json()["items"][0]["precio_unitario"] == "15.00"


def test_compatibilidad_id_producto(escenario):
    e = escenario
    e["orden"].items[0].variante_id = e["producto"]["id"]
    item = repetir(e).json()["items"][0]
    assert item["variante_original_id"] == e["producto"]["id"]
    assert item["variante_id"] == e["producto"]["variantes"][0]["id"]


@pytest.mark.parametrize("estado", ["agotado", "despublicado", "eliminado", "sin_stock_verificable"])
def test_productos_no_disponibles_se_informan(escenario, estado):
    e = escenario
    if estado == "agotado":
        e["stock"].return_value = {"stock_disponible": 0}
    elif estado == "despublicado":
        e["producto"]["estado"] = "borrador"
    elif estado == "eliminado":
        e["catalogo"]["productos"] = []
    else:
        e["stock"].side_effect = RuntimeError("Inventario no disponible")
    respuesta = repetir(e)
    assert respuesta.status_code == 200
    assert respuesta.json()["items"] == []
    assert respuesta.json()["avisos"]


def test_no_sustituye_variante_eliminada(escenario):
    e = escenario
    e["producto"]["variantes"][0]["id"] = str(uuid4())
    assert repetir(e).json()["items"] == []
    e["stock"].assert_not_awaited()


@pytest.mark.parametrize("headers,estado", [({}, 401), ({"Authorization": "Bearer invalido"}, 401)])
def test_requiere_autenticacion(escenario, headers, estado):
    assert repetir(escenario, headers).status_code == estado


@pytest.mark.parametrize("role", ["cliente", "administrador", "cajero"])
def test_rechaza_pedido_ajeno_y_roles_no_cliente(escenario, role):
    token = create_access_token({"sub": str(uuid4()), "role": role})
    assert repetir(escenario, {"Authorization": f"Bearer {token}"}).status_code == 403
    escenario["stock"].assert_not_awaited()


def test_catalogo_caido_no_usa_precios_historicos(escenario):
    escenario["catalogo"]["fallar"] = True
    assert repetir(escenario).status_code == 503
    escenario["stock"].assert_not_awaited()


def test_reintentos_no_modifican_pedido_ni_crean_compra(escenario):
    e = escenario
    original = e["orden"].model_dump()
    assert repetir(e).json() == repetir(e).json()
    assert e["orden"].model_dump() == original
    assert len(routers._ORDENES_DB) == 1


def test_pedido_inexistente(escenario):
    e = escenario
    assert e["client"].post(f"/api/v1/ordenes/{uuid4()}/repetir", headers=e["headers"]).status_code == 404


def test_legacy_con_variantes_ambiguas_no_sustituye_producto(escenario):
    e = escenario
    e["orden"].items[0].variante_id = e["producto"]["id"]
    e["producto"]["variantes"].append({"id": str(uuid4()), "sku": "OTRA-OPCION", "precio": "20"})
    assert repetir(e).json()["items"] == []


def test_stock_compartido_se_consulta_una_vez(escenario):
    e = escenario
    e["orden"].items.append(e["orden"].items[0].model_copy(update={"id": uuid4()}))
    assert len(repetir(e).json()["items"]) == 2
    e["stock"].assert_awaited_once_with("HABITUAL")


def test_resolver_precio_no_toma_tarifa_de_otra_variante(monkeypatch):
    from backend.services.catalogo.app import routers as catalogo
    from backend.services.catalogo.app.schemas import ProductoResponse
    p_id, primera, elegida, lista = (str(uuid4()) for _ in range(4))
    producto = ProductoResponse(id=p_id, sku="BASE", nombre="Producto", categoria_id=uuid4(), precio=10, variantes=[
        {"id": primera, "producto_id": p_id, "sku": "BASE-A", "nombre_variante": "A", "precio": 10},
        {"id": elegida, "producto_id": p_id, "sku": "BASE-B", "nombre_variante": "B", "precio": 25},
    ])
    monkeypatch.setattr(catalogo, "_get_supabase_client_safe", lambda: None)
    monkeypatch.setattr(catalogo, "_fetch_all_products", lambda _: [producto])
    monkeypatch.setattr(catalogo, "_obtener_listas_precios", lambda _: [
        {"id": lista, "nombre": "Web", "activo": True, "canal": "web", "tipo_cliente": "retail"},
    ])
    monkeypatch.setattr(catalogo, "_obtener_items_precios", lambda _: [
        {"lista_precio_id": lista, "variante_id": primera, "precio": 7},
    ])
    precios = catalogo._resolver_precios([primera, elegida], "web", "retail", None)
    assert precios[primera].precio == Decimal("7")
    assert precios[elegida].precio == Decimal("25")

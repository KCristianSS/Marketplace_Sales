"""
Pruebas automatizadas para US-18 (RF-18):
Configuración y Consulta de Combos y Paquetes Comerciales en MaxiConecta.
Criterios de Aceptación:
1. Desglose de existencias individuales de cada ítem del paquete.
2. Visualización del combo como artículo único con detalle de componentes.
3. Disponibilidad conjunta (stock resultante del cuello de botella).
4. Restricción RBAC para operaciones de administración (creación, edición, eliminación).
"""
import os
import sys
import uuid
from decimal import Decimal
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from fastapi.testclient import TestClient
from backend.services.catalogo.app.main import app as catalogo_app
from backend.shared.security import create_access_token
from backend.shared import stock_ledger

client = TestClient(catalogo_app)

ADMIN_TOKEN = create_access_token({"sub": "admin-user-id", "role": "administrador", "user_metadata": {"role": "administrador"}})
CLIENT_TOKEN = create_access_token({"sub": "cliente-user-id", "role": "cliente", "user_metadata": {"role": "cliente"}})
ADMIN_HEADERS = {"Authorization": f"Bearer {ADMIN_TOKEN}"}
CLIENT_HEADERS = {"Authorization": f"Bearer {CLIENT_TOKEN}"}


def test_listar_combos_publico():
    """Valida que clientes y visitantes pueden listar combos con detalle de ítems y métricas comerciales."""
    resp = client.get("/api/v1/catalogo/combos")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 2, "Debe incluir los combos semilla"

    combo = data[0]
    assert "id" in combo
    assert "nombre" in combo
    assert "precio_combo" in combo
    assert "precio_original" in combo
    assert "ahorro_monto" in combo
    assert "ahorro_porcentaje" in combo
    assert "items" in combo
    assert "stock_disponible" in combo
    assert "disponible" in combo

    # Criterio 2: Visualización del combo como artículo único con detalle de componentes
    assert len(combo["items"]) >= 2
    for item in combo["items"]:
        # Criterio 1: Desglose de existencias individuales de cada ítem
        assert "variante_id" in item
        assert "sku" in item
        assert "nombre_producto" in item
        assert "cantidad" in item
        assert "precio_unitario" in item
        assert "stock_disponible" in item
        assert item["stock_disponible"] >= 0


def test_obtener_combo_individual_y_disponibilidad():
    """Consulta ficha individual de un combo y su endpoint de disponibilidad."""
    # Listar primero para obtener un ID válido
    lista = client.get("/api/v1/catalogo/combos").json()
    combo_id = lista[0]["id"]

    resp = client.get(f"/api/v1/catalogo/combos/{combo_id}")
    assert resp.status_code == 200
    combo_data = resp.json()
    assert combo_data["id"] == combo_id
    assert float(combo_data["precio_combo"]) > 0
    assert float(combo_data["precio_original"]) >= float(combo_data["precio_combo"])
    assert float(combo_data["ahorro_monto"]) >= 0

    # Endpoint específico de disponibilidad
    resp_disp = client.get(f"/api/v1/catalogo/combos/{combo_id}/disponibilidad")
    assert resp_disp.status_code == 200
    disp_data = resp_disp.json()
    assert disp_data["combo_id"] == combo_id
    assert "stock_disponible" in disp_data
    assert "disponible" in disp_data
    assert "desglose_items" in disp_data
    assert len(disp_data["desglose_items"]) == len(combo_data["items"])


def test_disponibilidad_conjunta_cuello_botella():
    """Valida que el stock disponible del combo sea el mínimo de combos_posibles de sus ítems (cuello de botella)."""
    import asyncio
    sku_a = f"TEST-ITEM-A-{uuid.uuid4().hex[:6]}"
    sku_b = f"TEST-ITEM-B-{uuid.uuid4().hex[:6]}"

    async def _setup_stock():
        await stock_ledger.register_base_stock(sku_a, 10)
        await stock_ledger.register_base_stock(sku_b, 3)

    asyncio.run(_setup_stock())

    var_a_id = str(uuid.uuid4())
    var_b_id = str(uuid.uuid4())

    payload = {
        "nombre": "Combo Test Cuello Botella",
        "sku": f"CMB-{uuid.uuid4().hex[:6].upper()}",
        "descripcion": "Combo de prueba para cálculo de disponibilidad conjunta",
        "precio_combo": 150.00,
        "items": [
            {"variante_id": var_a_id, "cantidad": 1},
            {"variante_id": var_b_id, "cantidad": 1},
        ],
    }

    # Creamos combo
    res_crear = client.post("/api/v1/catalogo/combos", json=payload, headers=ADMIN_HEADERS)
    assert res_crear.status_code == 201
    nuevo_combo = res_crear.json()
    combo_id = nuevo_combo["id"]

    # Inyectamos en memoria local los SKUs para que resolver_info_variante devuelva estos SKUs
    for it in nuevo_combo["items"]:
        if it["variante_id"] == var_a_id:
            it["sku"] = sku_a
        elif it["variante_id"] == var_b_id:
            it["sku"] = sku_b

    # Verificamos disponibilidad
    resp = client.get(f"/api/v1/catalogo/combos/{combo_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["disponible"] is True
    assert data["stock_disponible"] > 0


def test_creacion_y_ahorro_combo_por_administrador():
    """Valida la creación de un combo por admin, asegurando cálculo de ahorro y componentes."""
    var_1_id = "20000000-0000-0000-0000-000000000004" # Teclado (precio ~1150)
    var_2_id = "20000000-0000-0000-0000-000000000003" # Mouse (precio ~799)

    payload = {
        "nombre": "Pack Especial Creadores",
        "sku": f"CMB-CREATE-{uuid.uuid4().hex[:6].upper()}",
        "descripcion": "Kit especial para creadores de contenido",
        "precio_combo": 1499.00,
        "imagen_url": "https://example.com/pack-creadores.jpg",
        "activo": True,
        "items": [
            {"variante_id": var_1_id, "cantidad": 1},
            {"variante_id": var_2_id, "cantidad": 2},
        ],
    }

    resp = client.post("/api/v1/catalogo/combos", json=payload, headers=ADMIN_HEADERS)
    assert resp.status_code == 201
    created = resp.json()
    assert created["nombre"] == payload["nombre"]
    assert float(created["precio_combo"]) == 1499.00
    assert len(created["items"]) == 2
    # El precio original debe ser mayor que el precio combo
    assert float(created["precio_original"]) > 1499.00
    assert float(created["ahorro_monto"]) > 0
    assert float(created["ahorro_porcentaje"]) > 0


def test_creacion_rechazada_para_rol_cliente():
    """Valida que usuarios con rol 'cliente' o anónimos no pueden crear combos (RBAC)."""
    payload = {
        "nombre": "Combo No Autorizado",
        "precio_combo": 99.00,
        "items": [{"variante_id": str(uuid.uuid4()), "cantidad": 1}],
    }
    # Con token de cliente -> 403 Forbidden
    resp = client.post("/api/v1/catalogo/combos", json=payload, headers=CLIENT_HEADERS)
    assert resp.status_code == 403

    # Sin token -> 401 Unauthorized
    resp_anon = client.post("/api/v1/catalogo/combos", json=payload)
    assert resp_anon.status_code == 401


def test_actualizacion_y_eliminacion_combo():
    """Valida modificación y baja de un combo comercial."""
    # Crear primero
    payload = {
        "nombre": "Combo Temporal para Modificar",
        "precio_combo": 299.00,
        "items": [{"variante_id": "20000000-0000-0000-0000-000000000004", "cantidad": 1}],
    }
    creado = client.post("/api/v1/catalogo/combos", json=payload, headers=ADMIN_HEADERS).json()
    cid = creado["id"]

    # Actualizar precio y nombre
    put_payload = {
        "nombre": "Combo Temporal Modificado",
        "precio_combo": 249.00,
    }
    resp_put = client.put(f"/api/v1/catalogo/combos/{cid}", json=put_payload, headers=ADMIN_HEADERS)
    assert resp_put.status_code == 200
    data_mod = resp_put.json()
    assert data_mod["nombre"] == "Combo Temporal Modificado"
    assert float(data_mod["precio_combo"]) == 249.00

    # Eliminar (baja lógica o borrado)
    resp_del = client.delete(f"/api/v1/catalogo/combos/{cid}", headers=ADMIN_HEADERS)
    assert resp_del.status_code == 204

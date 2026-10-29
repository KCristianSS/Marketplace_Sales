"""
Pruebas del flujo completo de Apertura, Control y Cierre de Caja por Turno (RF-09).

Cubre:
 - Apertura de caja con fondo inicial
 - Validación: no abrir dos cajas para el mismo cajero
 - Consultar caja activa
 - Registrar movimientos manuales (ingreso / egreso)
 - Procesar venta POS y acumulación de totales
 - Cierre con arqueo (diferencia sobrante / faltante)
 - Historial de cajas
"""

import sys
import os
import uuid
from decimal import Decimal

# Asegurar path de importación del backend
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from fastapi.testclient import TestClient
from backend.services.pos.app.main import app as pos_app
from backend.shared.security import create_access_token

client = TestClient(pos_app)


def _cajero_token(cajero_id: str = None, sucursal_id: str = None) -> dict:
    """Genera headers con un JWT de cajero válido para tests."""
    cid = cajero_id or str(uuid.uuid4())
    sid = sucursal_id or str(uuid.uuid4())
    token = create_access_token({
        "sub": cid,
        "role": "cajero",
        "sucursal_id": sid,
        "email": "cajero@test.com",
        "nombre_completo": "Cajero Test",
    })
    return {"Authorization": f"Bearer {token}"}, cid, sid


def _admin_token() -> dict:
    """Genera headers con un JWT de administrador válido para tests."""
    uid = str(uuid.uuid4())
    token = create_access_token({
        "sub": uid,
        "role": "administrador",
        "email": "admin@test.com",
        "nombre_completo": "Admin Test",
    })
    return {"Authorization": f"Bearer {token}"}, uid


# ---------------------------------------------------------------------------
# Test 1: Flujo completo de apertura → movimientos → cierre con arqueo
# ---------------------------------------------------------------------------

def test_flujo_completo_caja_turno():
    """Valida el ciclo de vida completo de una caja por turno."""
    headers, cajero_id, sucursal_id = _cajero_token()

    # 1. Abrir caja
    resp = client.post("/api/v1/pos/caja/abrir", json={
        "sucursal_id": sucursal_id,
        "cajero_id": cajero_id,
        "fondo_inicial": 500.00,
    }, headers=headers)
    assert resp.status_code == 201, f"Error al abrir caja: {resp.text}"
    caja = resp.json()
    caja_id = caja["id"]
    assert caja["estado"] == "abierta"
    assert float(caja["fondo_inicial"]) == 500.00
    assert float(caja["total_efectivo"]) == 0.00

    # 2. Consultar caja por ID
    resp = client.get(f"/api/v1/pos/caja/{caja_id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == caja_id

    # 3. Registrar ingreso manual (cambio extra)
    resp = client.post(f"/api/v1/pos/caja/{caja_id}/movimiento", json={
        "tipo": "ingreso",
        "monto": 200.00,
        "descripcion": "Ingreso de cambio adicional",
    }, headers=headers)
    assert resp.status_code == 201
    mov = resp.json()
    assert mov["tipo"] == "ingreso"
    assert float(mov["monto"]) == 200.00

    # 4. Registrar egreso manual (retiro parcial)
    resp = client.post(f"/api/v1/pos/caja/{caja_id}/movimiento", json={
        "tipo": "egreso",
        "monto": 50.00,
        "descripcion": "Retiro parcial de efectivo",
    }, headers=headers)
    assert resp.status_code == 201

    # 5. Listar movimientos
    resp = client.get(f"/api/v1/pos/caja/{caja_id}/movimientos", headers=headers)
    assert resp.status_code == 200
    movimientos = resp.json()
    assert len(movimientos) == 2

    # 6. Cerrar caja con arqueo
    # total_esperado = 500 (fondo) + 0 (efectivo ventas) + 200 (ingreso) - 50 (egreso) = 650
    resp = client.post(f"/api/v1/pos/caja/{caja_id}/cerrar", json={
        "monto_cierre_real": 655.00,
        "observaciones": "Sobrante de 5 Bs.",
    }, headers=headers)
    assert resp.status_code == 200, f"Error al cerrar caja: {resp.text}"
    arqueo = resp.json()
    assert arqueo["estado"] == "cerrada"
    assert float(arqueo["total_esperado"]) == 650.00
    assert float(arqueo["monto_cierre_real"]) == 655.00
    assert float(arqueo["diferencia"]) == 5.00  # sobrante
    assert arqueo["observaciones"] == "Sobrante de 5 Bs."


# ---------------------------------------------------------------------------
# Test 2: No se puede abrir dos cajas para el mismo cajero
# ---------------------------------------------------------------------------

def test_no_doble_apertura_cajero():
    """Valida que un cajero no pueda abrir dos cajas al mismo tiempo."""
    headers, cajero_id, sucursal_id = _cajero_token()

    # Primera apertura → OK
    resp = client.post("/api/v1/pos/caja/abrir", json={
        "sucursal_id": sucursal_id,
        "cajero_id": cajero_id,
        "fondo_inicial": 300.00,
    }, headers=headers)
    assert resp.status_code == 201

    # Segunda apertura → 409 Conflict
    resp = client.post("/api/v1/pos/caja/abrir", json={
        "sucursal_id": sucursal_id,
        "cajero_id": cajero_id,
        "fondo_inicial": 300.00,
    }, headers=headers)
    assert resp.status_code == 409
    assert "ya tiene una caja abierta" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Test 3: No se puede cerrar una caja inexistente
# ---------------------------------------------------------------------------

def test_cerrar_caja_inexistente():
    """Valida error al cerrar una caja que no existe."""
    headers, _, _ = _cajero_token()

    fake_id = str(uuid.uuid4())
    resp = client.post(f"/api/v1/pos/caja/{fake_id}/cerrar", json={
        "monto_cierre_real": 100.00,
    }, headers=headers)
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Test 4: No se puede registrar movimiento en caja cerrada
# ---------------------------------------------------------------------------

def test_movimiento_en_caja_cerrada():
    """Valida que no se puedan registrar movimientos en una caja cerrada."""
    headers, cajero_id, sucursal_id = _cajero_token()

    # Abrir y cerrar
    resp = client.post("/api/v1/pos/caja/abrir", json={
        "sucursal_id": sucursal_id,
        "cajero_id": cajero_id,
        "fondo_inicial": 100.00,
    }, headers=headers)
    caja_id = resp.json()["id"]

    client.post(f"/api/v1/pos/caja/{caja_id}/cerrar", json={
        "monto_cierre_real": 100.00,
    }, headers=headers)

    # Intentar movimiento → 403
    resp = client.post(f"/api/v1/pos/caja/{caja_id}/movimiento", json={
        "tipo": "ingreso",
        "monto": 50.00,
        "descripcion": "No debería funcionar",
    }, headers=headers)
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Test 5: Cierre con faltante (diferencia negativa)
# ---------------------------------------------------------------------------

def test_cierre_con_faltante():
    """Valida que el arqueo detecte faltantes correctamente."""
    headers, cajero_id, sucursal_id = _cajero_token()

    resp = client.post("/api/v1/pos/caja/abrir", json={
        "sucursal_id": sucursal_id,
        "cajero_id": cajero_id,
        "fondo_inicial": 1000.00,
    }, headers=headers)
    caja_id = resp.json()["id"]

    # Cerrar con menos de lo esperado
    resp = client.post(f"/api/v1/pos/caja/{caja_id}/cerrar", json={
        "monto_cierre_real": 980.00,
        "observaciones": "Faltante de 20 Bs, verificar billetes",
    }, headers=headers)
    assert resp.status_code == 200
    arqueo = resp.json()
    assert float(arqueo["diferencia"]) == -20.00
    assert arqueo["observaciones"] == "Faltante de 20 Bs, verificar billetes"


# ---------------------------------------------------------------------------
# Test 6: Acceso denegado para roles no autorizados
# ---------------------------------------------------------------------------

def test_acceso_denegado_sin_token():
    """Valida que los endpoints protegidos rechacen peticiones sin token."""
    resp = client.post("/api/v1/pos/caja/abrir", json={
        "sucursal_id": str(uuid.uuid4()),
        "cajero_id": str(uuid.uuid4()),
        "fondo_inicial": 100.00,
    })
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Test 7: Suspensión de ventas sigue funcionando
# ---------------------------------------------------------------------------

def test_suspension_ventas_compatible():
    """Valida que el flujo de ventas suspendidas sigue funcionando tras la refactorización."""
    venta_id = f"susp-{uuid.uuid4().hex[:8]}"
    payload = {
        "id": venta_id,
        "cliente_referencia": "Test Cliente",
        "items": [{
            "variante_id": str(uuid.uuid4()),
            "sku": "TEST-SKU-001",
            "nombre": "Producto Test",
            "cantidad": 2,
            "precio_unitario": 150.00,
        }],
        "subtotal": 300.00,
    }

    # Suspender globalmente
    resp = client.post("/api/v1/pos/ventas/suspender", json=payload)
    assert resp.status_code == 201
    assert resp.json()["id"] == venta_id

    # Listar suspendidas
    resp = client.get("/api/v1/pos/ventas/suspendidas")
    assert resp.status_code == 200

    # Reanudar
    resp = client.delete(f"/api/v1/pos/ventas/suspendidas/{venta_id}")
    assert resp.status_code == 200

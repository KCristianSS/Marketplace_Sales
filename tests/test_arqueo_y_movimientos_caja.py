"""KAN-341 (arqueo ciego) y KAN-342 (movimientos de efectivo con motivo, límite y supervisor)."""
import uuid
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from backend.services.pos.app.main import app as pos_app
from backend.shared.audit import AUDIT_LOGS_EN_MEMORIA
from backend.shared.caja_store import CAJAS_EN_MEMORIA
from backend.shared.erp_clients.contabilidad import ContabilidadClient
from backend.shared.security import create_access_token

client = TestClient(pos_app)


def _token(role: str = "cajero", uid: str | None = None) -> tuple[dict, str]:
    uid = uid or str(uuid.uuid4())
    tok = create_access_token({"sub": uid, "role": role, "email": f"{role}@test.com"})
    return {"Authorization": f"Bearer {tok}"}, uid


def _abrir(fondo: float = 500.0):
    headers, uid = _token("cajero")
    r = client.post("/api/v1/pos/caja/abrir", json={"sucursal_id": str(uuid.uuid4()), "fondo_inicial": fondo}, headers=headers)
    assert r.status_code == 201, r.text
    return headers, uid, r.json()["id"]


def _desglose(**cantidades):
    """_desglose(b200=1, m050=2) -> [{'denominacion': 200, 'cantidad': 1}, ...]"""
    mapa = {"b200": 200, "b100": 100, "b50": 50, "b20": 20, "b10": 10, "m5": 5, "m2": 2, "m1": 1, "m050": 0.5, "m020": 0.2, "m010": 0.1}
    return [{"denominacion": mapa[k], "cantidad": v} for k, v in cantidades.items()]


# =============================== KAN-342 ===============================
def test_movimiento_sin_motivo_no_se_registra():
    headers, _, caja_id = _abrir()
    for body in ({"tipo": "entrada", "monto": 50}, {"tipo": "entrada", "monto": 50, "motivo": "   "}):
        r = client.post(f"/api/v1/pos/caja/{caja_id}/movimientos", json=body, headers=headers)
        assert r.status_code == 422
    assert client.get(f"/api/v1/pos/caja/{caja_id}/movimientos", headers=headers).json() == []


def test_entrada_y_retiro_generan_comprobante_y_audit_log():
    headers, _, caja_id = _abrir(500)
    antes = len(AUDIT_LOGS_EN_MEMORIA)
    r = client.post(f"/api/v1/pos/caja/{caja_id}/movimientos", json={"tipo": "entrada", "monto": 200, "motivo": "Cambio adicional"}, headers=headers)
    assert r.status_code == 201, r.text
    mov = r.json()
    assert mov["numero_comprobante"].startswith("MOV-")
    assert mov["comprobante"]["motivo"] == "Cambio adicional" and mov["requiere_supervisor"] is False
    r = client.post(f"/api/v1/pos/caja/{caja_id}/movimientos", json={"tipo": "retiro", "monto": 100, "motivo": "Retiro a bóveda"}, headers=headers)
    assert r.status_code == 201
    acciones = [a["action"] for a in AUDIT_LOGS_EN_MEMORIA[antes:]]
    assert acciones == ["MOVIMIENTO_EFECTIVO_ENTRADA", "MOVIMIENTO_EFECTIVO_RETIRO"]

    neto = client.get(f"/api/v1/pos/caja/{caja_id}/movimientos/neto", headers=headers).json()
    assert (Decimal(neto["entradas"]), Decimal(neto["retiros"]), Decimal(neto["neto"])) == (Decimal(200), Decimal(100), Decimal(100))
    assert Decimal(neto["limite_seguridad"]) == Decimal("2000.00")
    assert len(client.get(f"/api/v1/pos/caja/{caja_id}/movimientos", headers=headers).json()) == 2


def test_retiro_mayor_al_efectivo_disponible_se_rechaza():
    headers, _, caja_id = _abrir(500)
    r = client.post(f"/api/v1/pos/caja/{caja_id}/movimientos", json={"tipo": "retiro", "monto": 500.01, "motivo": "Exceso"}, headers=headers)
    assert r.status_code == 422
    assert client.get(f"/api/v1/pos/caja/{caja_id}/movimientos", headers=headers).json() == []


def test_retiro_sobre_limite_requiere_supervisor():
    headers, cajero_id, caja_id = _abrir(5000)
    body = {"tipo": "retiro", "monto": 2500, "motivo": "Exceso de efectivo en gaveta"}
    r = client.post(f"/api/v1/pos/caja/{caja_id}/movimientos", json=body, headers=headers)
    assert r.status_code == 428
    assert r.json()["detail"]["codigo"] == "SUPERVISOR_REQUERIDO"

    # Token de un cajero NO es válido como supervisor.
    otro_cajero, _ = _token("cajero")
    r = client.post(f"/api/v1/pos/caja/{caja_id}/movimientos", json={**body, "supervisor_token": otro_cajero["Authorization"].split()[1]}, headers=headers)
    assert r.status_code == 403
    # Token vacío/inválido.
    r = client.post(f"/api/v1/pos/caja/{caja_id}/movimientos", json={**body, "supervisor_token": "basura"}, headers=headers)
    assert r.status_code == 401

    admin, admin_id = _token("administrador")
    sup_token = admin["Authorization"].split()[1]
    r = client.post(f"/api/v1/pos/caja/{caja_id}/movimientos", json={**body, "supervisor_token": sup_token}, headers=headers)
    assert r.status_code == 201, r.text
    assert r.json()["requiere_supervisor"] is True and r.json()["supervisor_id"] == admin_id
    assert r.json()["comprobante"]["supervisor_id"] == admin_id


def test_retiro_en_el_limite_no_requiere_supervisor():
    headers, _, caja_id = _abrir(5000)
    r = client.post(f"/api/v1/pos/caja/{caja_id}/movimientos", json={"tipo": "retiro", "monto": 2000, "motivo": "Límite exacto"}, headers=headers)
    assert r.status_code == 201


def test_supervisor_no_puede_ser_el_mismo_cajero_del_turno():
    admin, admin_id = _token("administrador")
    r = client.post("/api/v1/pos/caja/abrir", json={"sucursal_id": str(uuid.uuid4()), "fondo_inicial": 6000}, headers=admin)
    caja_id = r.json()["id"]
    r = client.post(f"/api/v1/pos/caja/{caja_id}/movimientos", json={"tipo": "retiro", "monto": 3000, "motivo": "Autoconfirmado"}, headers=admin)
    assert r.status_code == 403


def test_movimiento_en_caja_cerrada_y_de_otro_cajero():
    headers, _, caja_id = _abrir()
    otro, _ = _token("cajero")
    assert client.post(f"/api/v1/pos/caja/{caja_id}/movimientos", json={"tipo": "entrada", "monto": 10, "motivo": "Intruso"}, headers=otro).status_code == 403
    client.post(f"/api/v1/pos/caja/{caja_id}/arqueo-ciego", json={"desglose": _desglose(b200=2, b100=1)}, headers=headers)
    assert client.post(f"/api/v1/pos/caja/{caja_id}/movimientos", json={"tipo": "entrada", "monto": 10, "motivo": "Tarde"}, headers=headers).status_code == 403


def test_rutas_heredadas_siguen_funcionando_con_alias():
    headers, _, caja_id = _abrir(500)
    r = client.post(f"/api/v1/pos/caja/{caja_id}/movimiento", json={"tipo": "ingreso", "monto": 40, "descripcion": "Heredado"}, headers=headers)
    assert r.status_code == 201 and r.json()["tipo"] == "ingreso"
    assert client.get(f"/api/v1/pos/caja/{caja_id}/movimientos/neto", headers=headers).json()["neto"] in ("40.00", "40", 40, 40.0)


# =============================== KAN-341 ===============================
def test_arqueo_cuadrado_calcula_esperado_con_movimientos_y_ventas():
    headers, _, caja_id = _abrir(500)
    CAJAS_EN_MEMORIA[caja_id]["total_efectivo"] = 300.0  # ventas en efectivo del turno
    client.post(f"/api/v1/pos/caja/{caja_id}/movimientos", json={"tipo": "entrada", "monto": 200, "motivo": "Cambio"}, headers=headers)
    client.post(f"/api/v1/pos/caja/{caja_id}/movimientos", json={"tipo": "retiro", "monto": 100, "motivo": "Bóveda"}, headers=headers)
    # esperado = 500 + 300 + 200 - 100 = 900
    antes = len(AUDIT_LOGS_EN_MEMORIA)
    r = client.post(f"/api/v1/pos/caja/{caja_id}/arqueo-ciego", json={"desglose": _desglose(b200=4, b100=1)}, headers=headers)
    assert r.status_code == 201, r.text
    rep = r.json()
    assert Decimal(rep["total_esperado"]) == 900 and Decimal(rep["total_declarado"]) == 900 and Decimal(rep["diferencia"]) == 0
    assert rep["resultado"] == "cuadrado" and rep["con_diferencia"] is False
    assert rep["estado_turno"] == "cerrada" and rep["notificacion_contabilidad"] is None
    assert Decimal(rep["entradas_extraordinarias"]) == 200 and Decimal(rep["retiros_boveda"]) == 100
    assert [d["tipo"] for d in rep["desglose"]] == ["billete", "billete"]
    assert any(a["action"] == "ARQUEO_CIEGO_CIERRE" for a in AUDIT_LOGS_EN_MEMORIA[antes:])
    assert client.get(f"/api/v1/pos/caja/{caja_id}", headers=headers).json()["estado"] == "cerrada"


def test_arqueo_con_faltante_marca_turno_y_notifica_contabilidad(monkeypatch):
    llamadas = []

    async def falso(self, data):
        llamadas.append(data)
        return {"notificacion_id": "N-1", "estado": "recibida"}

    monkeypatch.setattr(ContabilidadClient, "notificar_arqueo_con_diferencia", falso)
    headers, _, caja_id = _abrir(500)
    r = client.post(f"/api/v1/pos/caja/{caja_id}/arqueo-ciego", json={"desglose": _desglose(b100=4, m5=1, m050=1)}, headers=headers)
    rep = r.json()
    assert Decimal(rep["total_declarado"]) == Decimal("405.50") and Decimal(rep["diferencia"]) == Decimal("-94.50")
    assert rep["resultado"] == "faltante" and rep["con_diferencia"] is True
    assert rep["notificacion_contabilidad"]["estado"] == "recibida"
    assert llamadas and llamadas[0]["resultado"] == "faltante"
    assert CAJAS_EN_MEMORIA[caja_id]["con_diferencia"] is True


def test_arqueo_con_sobrante_usa_respuesta_simulada_si_erp_no_responde():
    headers, _, caja_id = _abrir(500)
    r = client.post(f"/api/v1/pos/caja/{caja_id}/arqueo-ciego", json={"desglose": _desglose(b200=2, b100=1, b50=1, m1=1)}, headers=headers)
    rep = r.json()
    assert rep["resultado"] == "sobrante" and Decimal(rep["diferencia"]) == Decimal("51.00")
    assert rep["notificacion_contabilidad"]["modo"] == "mock_fallback"


def test_turno_cerrado_no_puede_arquearse_de_nuevo_409():
    headers, _, caja_id = _abrir(500)
    assert client.post(f"/api/v1/pos/caja/{caja_id}/arqueo-ciego", json={"desglose": _desglose(b200=2, b100=1)}, headers=headers).status_code == 201
    r = client.post(f"/api/v1/pos/caja/{caja_id}/arqueo-ciego", json={"desglose": _desglose(b200=9)}, headers=headers)
    assert r.status_code == 409


def test_dos_cierres_simultaneos_solo_uno_gana():
    headers, _, caja_id = _abrir(500)
    body = {"desglose": _desglose(b200=2, b100=1)}
    with ThreadPoolExecutor(2) as pool:
        codigos = sorted(f.result().status_code for f in [pool.submit(lambda: client.post(f"/api/v1/pos/caja/{caja_id}/arqueo-ciego", json=body, headers=headers)) for _ in range(2)])
    assert codigos == [201, 409]


def test_reporte_solo_existe_tras_confirmar_y_no_filtra_totales_antes():
    headers, _, caja_id = _abrir(500)
    r = client.get(f"/api/v1/pos/caja/{caja_id}/arqueo", headers=headers)
    assert r.status_code == 404 and "total" not in r.text.lower().replace("aún no tiene arqueo", "")
    client.post(f"/api/v1/pos/caja/{caja_id}/arqueo-ciego", json={"desglose": _desglose(b200=2, b100=1), "observaciones": "Todo en orden"}, headers=headers)
    rep = client.get(f"/api/v1/pos/caja/{caja_id}/arqueo", headers=headers).json()
    assert rep["numero_reporte"].startswith("ARQ-") and rep["observaciones"] == "Todo en orden"
    otro, _ = _token("cajero")
    assert client.get(f"/api/v1/pos/caja/{caja_id}/arqueo", headers=otro).status_code == 403


@pytest.mark.parametrize(
    "desglose",
    [
        [{"denominacion": 7, "cantidad": 1}],
        [{"denominacion": 100, "cantidad": 1}, {"denominacion": 100, "cantidad": 2}],
        [{"denominacion": 100, "cantidad": -1}],
        [],
    ],
)
def test_desglose_invalido_422_y_turno_sigue_abierto(desglose):
    headers, _, caja_id = _abrir()
    assert client.post(f"/api/v1/pos/caja/{caja_id}/arqueo-ciego", json={"desglose": desglose}, headers=headers).status_code == 422
    assert client.get(f"/api/v1/pos/caja/{caja_id}", headers=headers).json()["estado"] == "abierta"


def test_arqueo_solo_del_dueno_y_roles_autorizados():
    headers, _, caja_id = _abrir()
    otro, _ = _token("cajero")
    assert client.post(f"/api/v1/pos/caja/{caja_id}/arqueo-ciego", json={"desglose": _desglose(b100=1)}, headers=otro).status_code == 403
    cliente, _ = _token("cliente")
    assert client.post(f"/api/v1/pos/caja/{caja_id}/arqueo-ciego", json={"desglose": _desglose(b100=1)}, headers=cliente).status_code == 403
    assert client.post(f"/api/v1/pos/caja/{caja_id}/arqueo-ciego", json={"desglose": _desglose(b100=1)}).status_code == 401
    assert client.post(f"/api/v1/pos/caja/{uuid.uuid4()}/arqueo-ciego", json={"desglose": _desglose(b100=1)}, headers=headers).status_code == 404


def test_denominaciones_decimales_se_suman_sin_error_de_punto_flotante():
    headers, _, caja_id = _abrir(0)
    r = client.post(f"/api/v1/pos/caja/{caja_id}/arqueo-ciego", json={"desglose": _desglose(m050=3, m020=3, m010=3)}, headers=headers)
    assert Decimal(r.json()["total_declarado"]) == Decimal("2.40")

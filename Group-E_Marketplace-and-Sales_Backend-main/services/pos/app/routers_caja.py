"""KAN-341 (arqueo ciego) y KAN-342 (movimientos de efectivo) — endpoints del POS."""
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, status

try:
    from app.schemas import (
        ArqueoCiegoRequest,
        ArqueoReporteResponse,
        MovimientoEfectivoRequest,
        MovimientoEfectivoResponse,
        MovimientosNetosResponse,
    )
    from app.services import movimientos_netos, obtener_caja
    from app.arqueo import ejecutar_arqueo_ciego, obtener_reporte_arqueo
    from app.movimientos import limite_seguridad, listar_movimientos_efectivo, registrar_movimiento_efectivo
except (ModuleNotFoundError, ImportError):
    from backend.services.pos.app.schemas import (
        ArqueoCiegoRequest,
        ArqueoReporteResponse,
        MovimientoEfectivoRequest,
        MovimientoEfectivoResponse,
        MovimientosNetosResponse,
    )
    from backend.services.pos.app.services import movimientos_netos, obtener_caja
    from backend.services.pos.app.arqueo import ejecutar_arqueo_ciego, obtener_reporte_arqueo
    from backend.services.pos.app.movimientos import (
        limite_seguridad,
        listar_movimientos_efectivo,
        registrar_movimiento_efectivo,
    )

from backend.shared.security import get_current_user, require_jwt_claims

router = APIRouter(prefix="/api/v1/pos", tags=["Caja: arqueo ciego y movimientos de efectivo"])


async def _caja_o_404(caja_id: str, current_user: Dict[str, Any]) -> Dict[str, Any]:
    caja = await obtener_caja(caja_id)
    if not caja:
        raise HTTPException(status_code=404, detail="Caja no encontrada.")
    es_admin = str(current_user.get("role", "")).lower() == "administrador"
    if not es_admin and str(caja["cajero_id"]) != str(current_user.get("user_id")):
        raise HTTPException(status_code=403, detail="La caja pertenece a otro cajero.")
    return caja


# ---------------------------------------------------------------- KAN-342
@router.post(
    "/caja/{caja_id}/movimientos",
    response_model=MovimientoEfectivoResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar entrada extraordinaria o retiro parcial a bóveda",
)
@require_jwt_claims("sub", allowed_roles={"cajero", "administrador"})
async def crear_movimiento_efectivo(
    caja_id: str,
    payload: MovimientoEfectivoRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    caja = await _caja_o_404(caja_id, current_user)
    mov = await registrar_movimiento_efectivo(
        caja, payload.tipo, payload.monto, payload.motivo, current_user, payload.supervisor_token
    )
    return MovimientoEfectivoResponse(**mov)


@router.get(
    "/caja/{caja_id}/movimientos",
    response_model=List[MovimientoEfectivoResponse],
    summary="Listar movimientos de efectivo del turno",
)
@require_jwt_claims("sub", allowed_roles={"cajero", "administrador"})
async def listar_movimientos_de_caja(caja_id: str, current_user: Dict[str, Any] = Depends(get_current_user)):
    caja = await _caja_o_404(caja_id, current_user)
    return [MovimientoEfectivoResponse(**m) for m in await listar_movimientos_efectivo(caja)]


@router.get(
    "/caja/{caja_id}/movimientos/neto",
    response_model=MovimientosNetosResponse,
    summary="Movimientos netos del turno (entradas − retiros)",
)
@require_jwt_claims("sub", allowed_roles={"cajero", "administrador"})
async def movimientos_netos_de_caja(caja_id: str, current_user: Dict[str, Any] = Depends(get_current_user)):
    await _caja_o_404(caja_id, current_user)
    netos = await movimientos_netos(caja_id)
    return MovimientosNetosResponse(caja_turno_id=caja_id, limite_seguridad=limite_seguridad(), **netos)


# ---------------------------------------------------------------- KAN-341
@router.post(
    "/caja/{caja_id}/arqueo-ciego",
    response_model=ArqueoReporteResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Cierre del turno con arqueo ciego (desglose de billetes y monedas)",
)
@require_jwt_claims("sub", allowed_roles={"cajero", "administrador"})
async def arqueo_ciego(
    caja_id: str,
    payload: ArqueoCiegoRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    arqueo = await ejecutar_arqueo_ciego(caja_id, payload.desglose, payload.observaciones, current_user)
    return ArqueoReporteResponse(**arqueo)


@router.get(
    "/caja/{caja_id}/arqueo",
    response_model=ArqueoReporteResponse,
    summary="Reporte imprimible del arqueo confirmado",
)
@require_jwt_claims("sub", allowed_roles={"cajero", "administrador"})
async def reporte_arqueo(caja_id: str, current_user: Dict[str, Any] = Depends(get_current_user)):
    return ArqueoReporteResponse(**await obtener_reporte_arqueo(caja_id, current_user))
